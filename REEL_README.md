# リールの作り方

## 最初の1回だけ
1. 動画づくりの部品を入れる（PowerShellで）
   python -m pip install imageio-ffmpeg
2. C:\sns-auto の中に secrets というフォルダを作り、openai_key.txt というファイルに
   OpenAIのAPIキー（sk- で始まる文字列）を1行だけ書いて保存する
   ※ 環境変数 OPENAI_API_KEY には入れないこと（Codexの画像生成がAPI課金に切り替わるため）

## 毎回
- 声なしで試す（無料）： python make_reel.py --dry posts/carousel_001.json
- 本番（全投稿）：       python make_reel.py
- できあがり：           reels/001.mp4 〜 007.mp4（縦1080x1920、30〜45秒ほど）
- 読み上げ原稿：         reels/001_script.txt

## 読み方を直したいとき
posts/carousel_XXX.json の該当スライドに "narration": "読ませたい文" を足すと、その文を優先して読む。
（例：人名の読みを間違えたとき、「安藤百福（あんどうももふく）」を「あんどうももふく」と書く）

## 投稿するとき
Business Suiteのアプリで「リール動画」→ reels/XXX.mp4 を選ぶ → 音楽を追加（ナレーションが聞こえるよう音量は小さめ）
→ キャプションは予約キューのページの本文をそのまま使う → 日時を指定
