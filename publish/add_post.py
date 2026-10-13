"""パソコンで使う：投稿をGitHubに載せる準備をして、予定表に追加する。

使い方:
  python publish/add_post.py reel 001 "2026-10-14 12:30"
  python publish/add_post.py carousel 008 "2026-10-19 21:00"
  python publish/add_post.py threads 002 "2026-10-13 21:30"

・カルーセルの画像は output/<id>/01〜05.png を JPEG に変換して docs/media/<id>/ に置く
  （インスタのAPIはJPEGしか受け付けないため）
・リールは reels/<id>.mp4 を docs/media/reels/ にコピーする
・本文は posts/carousel_<id>.json の caption と hashtags を使う
・Threadsは posts/carousel_<id>.json の threads_text をそのまま投稿する（画像・動画なし）
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "media"
SCHEDULE = ROOT / "publish" / "schedule.json"


def main(kind, pid, when):
    spec = json.loads((ROOT / "posts" / f"carousel_{pid}.json").read_text(encoding="utf-8"))
    at = when.replace(" ", "T")
    item = {"key": f"{kind}-{pid}", "type": kind, "at": at}
    if kind != "threads":
        item["caption"] = spec["caption"] + "\n\n" + spec["hashtags"]

    if kind == "threads":
        if not spec.get("threads_text"):
            sys.exit(f"posts/carousel_{pid}.json に threads_text がありません")
        item["text"] = spec["threads_text"]
    elif kind == "reel":
        src = ROOT / "reels" / f"{pid}.mp4"
        dst = MEDIA / "reels" / f"{pid}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        item["video"] = f"media/reels/{pid}.mp4"
    elif kind == "carousel":
        imgs = []
        for src in sorted((ROOT / "output" / pid).glob("0*.png")):
            dst = MEDIA / pid / (src.stem + ".jpg")
            dst.parent.mkdir(parents=True, exist_ok=True)
            Image.open(src).convert("RGB").save(dst, "JPEG", quality=92)
            imgs.append(f"media/{pid}/{dst.name}")
        if not imgs:
            sys.exit(f"output/{pid} に画像がありません")
        item["images"] = imgs
    else:
        sys.exit("種類は reel / carousel / threads のどれかを指定してください")

    (ROOT / "docs" / ".nojekyll").touch()
    schedule = json.loads(SCHEDULE.read_text(encoding="utf-8")) if SCHEDULE.exists() else []
    schedule = [i for i in schedule if i["key"] != item["key"]] + [item]
    schedule.sort(key=lambda i: i["at"])
    SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"追加: {item['key']} を {at} に投稿予定")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
