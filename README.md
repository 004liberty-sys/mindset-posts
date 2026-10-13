# SNS自動投稿（インスタ・Threads）作業フォルダ

## 中身
- `posts/carousel_<id>.json` … 1投稿分（5枚の文章、インスタ本文、Threads文、背景の指示文、出典）
- `make_carousel.py` … JSONから投稿画像（1080x1350、5枚）を作る
- `backgrounds/` … Codexが作る背景画像の置き場所（なければ暗いグラデーションで作る）
- `output/<id>/` … 完成した投稿画像
- `成功者ネタ帳.xlsx` … ネタ帳（出典・確認度つき）
- `CODEX_BACKGROUNDS.md` … Codexに背景画像を作らせる手順

## 使い方
1. Pythonの部品を入れる（最初の1回だけ）: `pip install pillow`
2. 画像を作る: `python make_carousel.py`
3. 背景を作る: Claude Code で `/codex:rescue CODEX_BACKGROUNDS.md の手順で背景画像を作って`

## 設定
- `make_carousel.py` の `BRAND` を自分のインスタのユーザー名にする
- フォントはWindowsの游明朝を自動で使う（見つからない場合はフォントの場所を `FONT_CANDIDATES` に追加）
