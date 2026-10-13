"""GitHubのクラウドで30分ごとに動き、予定時刻を過ぎた投稿をインスタ・Threadsに出す。

・予定時刻を過ぎたもののうち、いちばん早い時刻の予定をまとめて投稿する
  （同じ 21:30 のリールとThreadsは同じ回に出る。たまっていても1回に1つの時刻ぶんだけ）
・Threadsのトークンは、前回の更新から7日たっていたら自動で更新し、GitHubのSecretを書き換える
  （Threadsの長期トークンは60日で切れるため。更新は発行から24時間以上たっていないとできない）

必要な設定（GitHub の Settings → Secrets and variables → Actions）:
  Secrets : IG_TOKEN（ページのアクセストークン）, IG_USER_ID（InstagramビジネスアカウントのID）
            THREADS_TOKEN（Threadsの長期トークン）, THREADS_USER_ID（ThreadsのユーザーID）
            GH_PAT（このリポジトリのSecretsを書き換えられるGitHubのトークン。Threadsトークンの更新用）
  Variables: MEDIA_BASE_URL（例 https://ユーザー名.github.io/リポジトリ名）
"""
import base64
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.facebook.com/v21.0"
THREADS_API = "https://graph.threads.net"
JST = datetime.timezone(datetime.timedelta(hours=9))
HERE = Path(__file__).parent
SCHEDULE = HERE / "schedule.json"
POSTED = HERE / "posted.json"
TOKEN_STATE = HERE / "token_state.json"   # トークンを最後に更新した日時だけを記録（トークン自体は書かない）
THREADS_REFRESH_DAYS = 7

TOKEN = os.environ.get("IG_TOKEN", "").strip()
IG = os.environ.get("IG_USER_ID", "").strip()
BASE = os.environ.get("MEDIA_BASE_URL", "").strip().rstrip("/")
THREADS_TOKEN = os.environ.get("THREADS_TOKEN", "").strip()
THREADS_USER = os.environ.get("THREADS_USER_ID", "").strip()
GH_PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "")


def request(req):
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        # エラー本文にトークンは含まれない
        raise RuntimeError(f"{req.full_url.split('?')[0]} {e.code}: {e.read().decode(errors='replace')[:600]}")


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params)
    if method == "GET":
        return request(urllib.request.Request(f"{API}/{path}?{data}"))
    return request(urllib.request.Request(f"{API}/{path}", data=data.encode(), method="POST"))


def threads_call(method, path, **params):
    params["access_token"] = THREADS_TOKEN
    data = urllib.parse.urlencode(params)
    if method == "GET":
        return request(urllib.request.Request(f"{THREADS_API}/{path}?{data}"))
    return request(urllib.request.Request(f"{THREADS_API}/{path}", data=data.encode(), method="POST"))


def wait_ready(container_id, limit=900):
    waited = 0
    while waited < limit:
        st = call("GET", container_id, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"メディアの処理に失敗しました: {st}")
        time.sleep(10)
        waited += 10
    raise RuntimeError("メディアの処理が時間内に終わりませんでした")


def caption_of(item):
    return item["caption"]


def post_reel(item):
    cid = call("POST", f"{IG}/media", media_type="REELS", video_url=f"{BASE}/{item['video']}",
               caption=caption_of(item), share_to_feed="true")["id"]
    wait_ready(cid)
    return call("POST", f"{IG}/media_publish", creation_id=cid)["id"]


def post_carousel(item):
    children = []
    for img in item["images"]:
        cid = call("POST", f"{IG}/media", image_url=f"{BASE}/{img}", is_carousel_item="true")["id"]
        wait_ready(cid, 180)
        children.append(cid)
    cid = call("POST", f"{IG}/media", media_type="CAROUSEL", children=",".join(children),
               caption=caption_of(item))["id"]
    wait_ready(cid, 300)
    return call("POST", f"{IG}/media_publish", creation_id=cid)["id"]


def post_threads(item):
    if not (THREADS_TOKEN and THREADS_USER):
        raise RuntimeError("THREADS_TOKEN / THREADS_USER_ID が設定されていません")
    cid = threads_call("POST", f"v1.0/{THREADS_USER}/threads", media_type="TEXT", text=item["text"])["id"]
    time.sleep(5)   # 作成直後は公開できないことがあるため少し待つ
    return threads_call("POST", f"v1.0/{THREADS_USER}/threads_publish", creation_id=cid)["id"]


POSTERS = {"reel": post_reel, "carousel": post_carousel, "threads": post_threads}


# ---------- Threadsトークンの自動更新 ----------
def set_github_secret(name, value):
    """GitHub APIでリポジトリのSecretを書き換える（値はリポジトリの公開鍵で暗号化して送る）。"""
    from nacl import encoding, public
    headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    base = f"https://api.github.com/repos/{REPO}/actions/secrets"
    key = request(urllib.request.Request(f"{base}/public-key", headers=headers))
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    sealed = base64.b64encode(box.encrypt(value.encode())).decode()
    body = json.dumps({"encrypted_value": sealed, "key_id": key["key_id"]}).encode()
    request(urllib.request.Request(f"{base}/{name}", data=body, method="PUT",
                                   headers={**headers, "Content-Type": "application/json"}))


def refresh_threads_token(now):
    global THREADS_TOKEN
    if not THREADS_TOKEN:
        return
    state = json.loads(TOKEN_STATE.read_text(encoding="utf-8")) if TOKEN_STATE.exists() else {}
    last = state.get("threads_refreshed_at")
    if last and now - datetime.datetime.fromisoformat(last) < datetime.timedelta(days=THREADS_REFRESH_DAYS):
        return
    if not (GH_PAT and REPO):
        raise RuntimeError("GH_PAT が設定されていないため、Threadsのトークンを更新できません")
    r = threads_call("GET", "refresh_access_token", grant_type="th_refresh_token")
    new_token = r["access_token"]
    print(f"::add-mask::{new_token}")   # 万一ログに出ても伏せ字にする
    set_github_secret("THREADS_TOKEN", new_token)
    THREADS_TOKEN = new_token
    state["threads_refreshed_at"] = now.isoformat(timespec="minutes")
    state["threads_expires_in_days"] = round(r.get("expires_in", 0) / 86400)
    TOKEN_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Threadsのトークンを更新しました（有効期限 {state['threads_expires_in_days']}日）")


def main():
    now = datetime.datetime.now(JST)
    errors = []
    try:
        refresh_threads_token(now)
    except Exception as e:
        errors.append(f"Threadsトークンの更新に失敗: {e}")   # 投稿は続ける。最後に失敗として知らせる

    schedule = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    due = [i for i in schedule
           if i["key"] not in posted
           and datetime.datetime.fromisoformat(i["at"]).replace(tzinfo=JST) <= now]
    if not due:
        print("投稿予定の時刻になったものはありません")
    else:
        first = min(i["at"] for i in due)
        batch = [i for i in due if i["at"] == first]   # いちばん早い時刻の予定をまとめて出す
        for item in batch:
            print(f"投稿します: {item['key']}（予定 {item['at']}）")
            try:
                media_id = POSTERS[item["type"]](item)
            except Exception as e:
                errors.append(f"{item['key']}: {e}")
                continue
            posted[item["key"]] = {"media_id": media_id,
                                   "posted_at": datetime.datetime.now(JST).isoformat(timespec="minutes")}
            POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"投稿しました: {item['key']} → {media_id}")

    if errors:
        raise RuntimeError(" / ".join(errors))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"失敗: {e}")
        sys.exit(1)   # 失敗するとGitHubからメールで知らせが来る
