"""GitHubのクラウドで30分ごとに動き、予定時刻を過ぎた投稿を1本だけインスタに出す。

必要な設定（GitHub の Settings → Secrets and variables → Actions）:
  Secrets : IG_TOKEN（ページのアクセストークン）, IG_USER_ID（InstagramビジネスアカウントのID）
  Variables: MEDIA_BASE_URL（例 https://ユーザー名.github.io/リポジトリ名）
"""
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
JST = datetime.timezone(datetime.timedelta(hours=9))
HERE = Path(__file__).parent
SCHEDULE = HERE / "schedule.json"
POSTED = HERE / "posted.json"

TOKEN = os.environ["IG_TOKEN"].strip()
IG = os.environ["IG_USER_ID"].strip()
BASE = os.environ["MEDIA_BASE_URL"].strip().rstrip("/")


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params)
    if method == "GET":
        req = urllib.request.Request(f"{API}/{path}?{data}")
    else:
        req = urllib.request.Request(f"{API}/{path}", data=data.encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # エラー本文にトークンは含まれない
        raise RuntimeError(f"Graph API {e.code}: {e.read().decode(errors='replace')[:600]}")


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


def main():
    schedule = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    now = datetime.datetime.now(JST)

    due = [i for i in schedule
           if i["key"] not in posted
           and datetime.datetime.fromisoformat(i["at"]).replace(tzinfo=JST) <= now]
    if not due:
        print("投稿予定の時刻になったものはありません")
        return
    item = sorted(due, key=lambda i: i["at"])[0]   # 1回に1本だけ（連投を防ぐ）
    print(f"投稿します: {item['key']}（予定 {item['at']}）")

    media_id = post_reel(item) if item["type"] == "reel" else post_carousel(item)
    posted[item["key"]] = {"media_id": media_id,
                           "posted_at": now.isoformat(timespec="minutes")}
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"投稿しました: {item['key']} → {media_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"失敗: {e}")
        sys.exit(1)   # 失敗するとGitHubからメールで知らせが来る
