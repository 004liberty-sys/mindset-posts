# GitHubで自動投稿する仕組み

## しくみ
1. パソコンで画像・リールを作る（今まで通り）
2. `python publish/add_post.py reel 001 "2026-10-14 12:30"` で、公開用フォルダ（docs/media）にコピーし、予定表（publish/schedule.json）に追加
3. GitHubに送る（git push）
4. GitHubのクラウドが30分ごとに予定表を確認し、時刻を過ぎたものを1本ずつインスタに投稿
   → パソコンの電源は切っていてOK

## 最初の準備（Claude Codeに任せる）
- GitHubに公開リポジトリ「mindset-posts」を作り、このフォルダを送る（secrets/ は .gitignore で除外）
- GitHub Pages を main ブランチの /docs で有効にする
- Secrets: IG_TOKEN（ページトークン）, IG_USER_ID / Variables: MEDIA_BASE_URL

## 注意
- docs/media に置いた画像・動画は、URLを知っている人なら投稿前でも見られる
- 投稿に失敗すると、GitHubから登録メールアドレスに通知が届く
- GitHub Actions のタブで「Run workflow」を押すと、今すぐ確認を動かせる
