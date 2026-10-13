"""カルーセルの5枚から、ナレーション付きのリール動画（1080x1920・縦）を作る。

使い方:
  python make_reel.py                         （posts/ の全投稿）
  python make_reel.py posts/carousel_001.json （1本だけ）
  python make_reel.py --dry                   （声なしの試し作成。料金はかからない）

出力:
  reels/<id>.mp4          … 完成したリール（BGM/ の mp3 をナレーションの下で流す）
  reels/<id>_script.txt   … 読み上げた原稿（確認用）

ナレーションはOpenAIの音声API（gpt-4o-mini-tts）で作る。
APIキーは環境変数ではなく secrets/openai_key.txt に1行で保存する。
（環境変数 OPENAI_API_KEY に入れると、Codexの画像生成までAPI課金に切り替わるため）
各スライドに "narration": "..." を書くと、その文を優先して読み上げる。
readings.json に「漢字: よみがな」を書いておくと、読み上げ原稿の中だけ置き換える（画像の文字はそのまま）。
"""
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

import make_carousel as mc

FPS = 30
FADE = 0.5            # スライド同士のつなぎ（秒）
PAD = 0.4             # 読み終わってから次のスライドまでの間（秒）
END_PAD = 1.8         # 最後のスライドの余韻（秒）
VOICE = "onyx"        # 低く落ち着いた男性の声
TTS_MODEL = "gpt-4o-mini-tts"
TTS_STYLE = ("男性ナレーター。落ち着いた低い声で、自然なテンポで読む。"
             "静かに語りかけるように。感情を込めすぎず、重みと温かさを持たせる。")
EMPHASIS = "「」で囲まれた言葉は、少し力を込めて、はっきりと読む。"
# 投稿の JSON に "voice": "female" と書くと女性の声で読む（書いていなければ男性の声）
# （声の名前, 読み方の指示, 声の速さ）。速さは 1.0=そのまま。音の高さは変えずに速くする
VOICES = {
    "male": (VOICE, TTS_STYLE + EMPHASIS, 1.1),
    "female": ("sage", "落ち着いた低めの女性ナレーター。自然なテンポで、静かに語りかけるように。" + EMPHASIS, 1.2),
}
SAMPLE_RATE = 24000   # OpenAIの pcm 出力（24kHz・16bit・モノラル）

OUT = Path("reels")
KEY_FILE = Path("secrets/openai_key.txt")
BGM_DIR = Path("BGM")   # ここの mp3（名前順で最初の1曲）をナレーションの下で流す。なければBGMなし
BGM_VOLUME = 0.26
BGM_FADE_IN = 1.0
BGM_FADE_OUT = 2.0
READINGS_FILE = Path("readings.json")


# ---------- 画像（縦長版） ----------
def reel_footer(img_draw, idx, total):
    """リール用：ページ番号は出さず、アカウント名を画面下の操作ボタンより上に置く。"""
    small = mc.font("serif_light", 30)
    bw = img_draw.textlength(mc.BRAND, font=small)
    x, y = (mc.W - bw) / 2, mc.H - 430
    for dx, dy in ((2, 2), (1, 1), (-1, 1)):
        img_draw.text((x + dx, y + dy), mc.BRAND, font=small, fill=(0, 0, 0))
    img_draw.text((x, y), mc.BRAND, font=small, fill=(225, 225, 225))


def render_vertical_slides(spec, workdir):
    """make_carousel の描画をそのまま使い、サイズだけ縦長（1080x1920）にして描く。"""
    mc.W, mc.H = 1080, 1920
    original_footer = mc.draw_footer
    mc.draw_footer = lambda *a, **k: None
    paths = []
    try:
        slides = spec["slides"]
        for i, s in enumerate(slides, 1):
            img = mc.render(s, i, len(slides), seed=f"{spec['id']}-{i}")
            from PIL import ImageDraw
            reel_footer(ImageDraw.Draw(img), i, len(slides))
            p = workdir / f"v{i:02d}.png"
            img.save(p)
            paths.append(p)
    finally:
        mc.draw_footer = original_footer
        mc.W, mc.H = 1080, 1350
    return paths


# ---------- 原稿 ----------
def narration_for(slide):
    if slide.get("narration"):
        return slide["narration"]
    blocks = [slide["main"]] + ([slide["sub"]] if slide.get("sub") else [])
    out = []
    for block in blocks:
        lines = []
        for line in block.split("\n"):
            line = line.strip()
            if not line or re.fullmatch(r"（.*）", line):        # （引退会見の言葉を要約）などは読まない
                continue
            m = re.match(r"^[―ー—-]\s*(.+?)（(.+?)）$", line)    # ― 安藤百福（日清食品 創業者）
            if m:
                line = f"{m.group(2)}、{m.group(1)}。"
            elif re.match(r"^[―ー—-]\s*", line):
                line = re.sub(r"^[―ー—-]\s*", "", line) + "。"
            elif line.endswith("」") and lines == [] and block is not blocks[0]:
                line += "。"      # サブの引用のあとで一呼吸
            lines.append(line)
        if not lines:
            continue
        joined = []
        for k, line in enumerate(lines):
            if k and joined[-1][-1] == ".":
                line = " " + line                      # Stay hungry. Stay foolish.
            elif k and lines[0].startswith("「") and joined[-1][-1] not in "。、」！？":
                line = "、" + line                     # 2行にまたがる引用は、行の切れ目で一呼吸
            joined.append(line)
        text_block = "".join(joined)
        if text_block[-1] not in "。、！？!?.":
            text_block += "。"    # まとまりの終わりで一呼吸おく
        out.append(text_block)
    text = "".join(out)
    text = text.replace(" × ", "かける").replace("×", "かける").replace(" ＝", "は、").replace("＝", "は、")
    if slide["type"] == "finale":
        text += "フォローして、明日も一緒に前へ。"
    return text


def apply_readings(text):
    """readings.json の「漢字: よみがな」で置き換える。長い語から先に置き換える。"""
    if not READINGS_FILE.exists():
        return text
    readings = json.loads(READINGS_FILE.read_text(encoding="utf-8"))
    for word in sorted(readings, key=len, reverse=True):
        text = text.replace(word, readings[word])
    return text


# ---------- 音声 ----------
def tts_pcm(text, api_key, voice="male"):
    import urllib.request
    name, style, _ = VOICES[voice]
    body = json.dumps({"model": TTS_MODEL, "voice": name, "input": text,
                       "instructions": style, "response_format": "pcm"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return len(pcm) / (SAMPLE_RATE * 2)


def make_audio(texts, workdir, dry, voice="male"):
    api_key = None
    if not dry:
        if not KEY_FILE.exists():
            sys.exit(f"APIキーがありません。{KEY_FILE} にOpenAIのAPIキーを1行で保存してください。")
        api_key = KEY_FILE.read_text(encoding="utf-8").strip()
    paths, secs = [], []
    for i, t in enumerate(texts, 1):
        p = workdir / f"a{i:02d}.wav"
        if dry:
            pcm = b"\x00\x00" * int(SAMPLE_RATE * max(1.5, len(t) / 7))   # 1秒7文字の目安で無音
        else:
            pcm = tts_pcm(t, api_key, voice)
        secs.append(write_wav(p, pcm))
        paths.append(p)
    return paths, secs


# ---------- 動画 ----------
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def build_video(images, audios, secs, out_path, tempo):
    n = len(images)
    secs = [s / tempo for s in secs]
    durs = [s + (END_PAD if i == n - 1 else PAD) for i, s in enumerate(secs)]
    lens = [d + (FADE if i < n - 1 else 0) for i, d in enumerate(durs)]

    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for p in images:
        cmd += ["-i", str(p)]
    for p in audios:
        cmd += ["-i", str(p)]
    bgm = next(iter(sorted(BGM_DIR.glob("*.mp3"))), None)
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm)]    # 動画より短ければ繰り返す

    f = []
    for i, L in enumerate(lens):
        frames = math.ceil(L * FPS)
        zoom = "min(zoom+0.0004,1.08)" if i % 2 == 0 else "if(eq(on,0),1.08,max(zoom-0.0004,1.0))"
        f.append(f"[{i}:v]scale=2160:3840,zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                 f":d={frames}:s=1080x1920:fps={FPS},setsar=1,format=yuv420p[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, n):
        offset += durs[i - 1]
        f.append(f"[{prev}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[x{i}]")
        prev = f"x{i}"
    for i, d in enumerate(durs):
        f.append(f"[{n + i}:a]atempo={tempo},apad=whole_dur={d:.3f}[a{i}]")
    total = sum(durs)
    voice_out = "voice" if bgm else "aout"
    f.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[{voice_out}]")
    if bgm:
        f.append(f"[{2 * n}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={BGM_VOLUME},"
                 f"afade=t=in:d={BGM_FADE_IN},afade=t=out:st={total - BGM_FADE_OUT:.3f}:d={BGM_FADE_OUT},"
                 f"aformat=sample_rates=48000:channel_layouts=stereo[bgm]")
        f.append("[voice]aformat=sample_rates=48000:channel_layouts=stereo[voice2]")
        f.append("[voice2][bgm]amix=inputs=2:duration=first:normalize=0[aout]")

    cmd += ["-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out_path)]
    subprocess.run(cmd, check=True)
    return total


def main(path, dry):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    pid = spec["id"]
    work = OUT / f"_work_{pid}"
    work.mkdir(parents=True, exist_ok=True)

    texts = [apply_readings(narration_for(s)) for s in spec["slides"]]
    (OUT / f"{pid}_script.txt").write_text("\n\n".join(texts), encoding="utf-8")

    images = render_vertical_slides(spec, work)
    voice = spec.get("voice", "male")
    audios, secs = make_audio(texts, work, dry, voice)
    total = build_video(images, audios, secs, OUT / f"{pid}.mp4", VOICES[voice][2])
    print(f"作成: reels/{pid}.mp4（{total:.1f}秒）{'※声なしの試し' if dry else ''}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv
    OUT.mkdir(exist_ok=True)
    for p in (args or sorted(str(x) for x in Path("posts").glob("carousel_*.json"))):
        main(p, dry)
