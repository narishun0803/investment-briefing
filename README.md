# 投資情報ブリーフィング

時間帯に応じた投資情報（マーケットデータ＋ニュース＋個別株寄与度）をHTMLダッシュボードとして生成するツールです。

## セットアップ

```bash
cd investment_briefing
pip3 install -r requirements.txt
```

Python 3.10 以上が必要です。

## デスクトップから起動する

### macOS（run_briefing.command）

1. Finder で `investment_briefing/` フォルダを開く
2. `run_briefing.command` を**ダブルクリック**
   - 初回は「開発元を確認できない」警告が出る場合があります
   - Finder で右クリック →「開く」→「開く」で許可してください
3. Chromeアプリモードでダッシュボードが開きます

**デスクトップにエイリアス（ショートカット）を作成：**

1. Finder で `run_briefing.command` を右クリック
2. 「エイリアスを作成」を選択
3. 作成された `run_briefing.command のエイリアス` をデスクトップに移動
4. 名前を「📊 投資ブリーフィング」などに変更（任意）

---

### Windows（run_briefing.bat）

1. `run_briefing.bat` を**ダブルクリック**
   - Chromeアプリモードで `output/briefing.html` が開きます
   - Chrome未インストールの場合はデフォルトブラウザで開きます

**デスクトップにショートカットを作成：**

1. `run_briefing.bat` を右クリック →「ショートカットの作成」
2. 作成されたショートカットをデスクトップにドラッグ
3. ショートカットを右クリック →「プロパティ」
4. 「アイコンの変更」→「参照」→ `icon.ico` を選択
5. 「ショートカットキー」欄でキーボードショートカット設定（任意、例: Ctrl+Alt+B）
6. 「OK」で保存

---

## コマンドラインでの使い方

```bash
# 実行時刻から時間帯を自動判定して生成
python3 fetch_briefing.py

# 時間帯を手動指定（morning / noon / evening / night）
python3 fetch_briefing.py --slot=morning
python3 fetch_briefing.py --slot=noon
python3 fetch_briefing.py --slot=evening
python3 fetch_briefing.py --slot=night

# 生成後にブラウザで自動オープン
python3 fetch_briefing.py --open
python3 fetch_briefing.py --slot=morning --open
```

生成されたHTMLは `output/briefing.html` に保存されます。

## 時間帯と表示内容

| 時間帯 | 時刻 | フォーカス |
|--------|------|-----------|
| 朝     | 5:00–9:00   | 米国市場結果・ADR・先物・夜間ニュース |
| 昼     | 11:00–13:30 | 日本前場総括・セクター騰落・決算速報 |
| 夕     | 17:00–21:00 | 日本大引け総括・主要決算・米国市場プレビュー |
| 夜     | 22:00–24:00 | 米国寄り付き直前・経済指標・欧州市場 |

## 機能

- **マーケットデータ**: 日経225, TOPIX連動ETF, S&P 500, NASDAQ, ダウ, ドル円, 米10年債, WTI原油, 金
- **個別株寄与度**: 日経225（主要30銘柄）・S&P500（時価総額上位50銘柄）の寄与度ランキング
- **ニュース**: 複数RSSフィードから投資関連ニュースを収集・4セクション分類表示
- **Claudeコピーボタン3種**: 全体解説 / 個別深掘り / リスク注目点
- **ダーク/ライトモード切替**: ブラウザが記憶
- **エラー耐性**: 一部データ取得失敗でもHTML生成

## アイコンの再生成

```bash
python3 create_icon.py
```

`icon.ico`（Windows用）と `icon_preview.png`（確認用）が生成されます。

## キャッシュファイル

| ファイル | 内容 | 更新頻度 |
|---------|------|---------|
| `data/sp500_constituents.csv` | S&P500構成銘柄 | 実行毎（Wikipedia取得） |
| `data/sp500_mcap_cache.json` | S&P500時価総額・取引所 | 7日ごと |
| `data/nikkei225_constituents.csv` | 日経225構成銘柄（任意） | 手動更新 |

## 処理時間の目安

| 実行回数 | 所要時間 |
|---------|---------|
| 初回（S&P500キャッシュ生成） | 60–120秒 |
| 2回目以降（キャッシュ有効） | 20–35秒 |

## 依存ライブラリ

- `yfinance` — 株価・為替データ取得
- `feedparser` — RSSフィード解析
- `jinja2` — HTMLテンプレートエンジン
- `requests` — HTTP通信
- `pandas` — S&P500構成銘柄の取得・処理
- `lxml` — HTML/XML解析
- `Pillow` — アイコン生成（`create_icon.py` 使用時）
