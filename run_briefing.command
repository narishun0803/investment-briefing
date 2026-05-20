#!/bin/bash
# macOS launcher — ダブルクリックでFinderから起動可能

cd "$(dirname "$0")"

echo "============================================"
echo " 投資情報ブリーフィング 起動中..."
echo "============================================"
echo ""
echo " [1] PCブラウザで開く（通常）"
echo " [2] スマホ共有モード（同じWiFiのスマホからアクセス可）"
echo ""
read -p " 選択 [1/2, デフォルト=1]: " MODE
MODE="${MODE:-1}"

if [ "$MODE" = "2" ]; then
    echo ""
    echo " スマホ共有モードで起動します..."
    python3 fetch_briefing.py --serve
    exit 0
fi

# 通常モード
python3 fetch_briefing.py
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] fetch_briefing.py の実行に失敗しました。"
    read -p "Enterキーで終了..."
    exit 1
fi

echo ""
HTML_PATH="$(pwd)/output/briefing.html"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -f "$CHROME_APP" ]; then
    "$CHROME_APP" --app="file://$HTML_PATH" 2>/dev/null &
else
    open "$HTML_PATH"
fi

echo "完了しました。"
sleep 1
