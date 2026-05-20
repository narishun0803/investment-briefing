@echo off
setlocal EnableDelayedExpansion

:: Change to the directory where this bat file is located
cd /d "%~dp0"

echo ============================================
echo  投資情報ブリーフィング 起動中...
echo ============================================
echo.

:: Run Python script
python fetch_briefing.py
if errorlevel 1 (
    echo.
    echo [ERROR] fetch_briefing.py の実行に失敗しました。
    echo Python が正しくインストールされているか確認してください。
    pause
    exit /b 1
)

echo.
echo ブラウザで開いています...

:: Output HTML path
set "HTML_PATH=%~dp0output\briefing.html"

:: Try Chrome app mode (standard install)
set "CHROME1=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "CHROME2=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set "CHROME3=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if exist "!CHROME1!" (
    start "" "!CHROME1!" "--app=file:///!HTML_PATH: =%%20!"
    goto :done
)
if exist "!CHROME2!" (
    start "" "!CHROME2!" "--app=file:///!HTML_PATH: =%%20!"
    goto :done
)
if exist "!CHROME3!" (
    start "" "!CHROME3!" "--app=file:///!HTML_PATH: =%%20!"
    goto :done
)

:: Chrome not found - open with default browser
echo [INFO] Chrome が見つかりませんでした。デフォルトブラウザで開きます。
start "" "!HTML_PATH!"

:done
echo.
echo 完了しました。
timeout /t 2 /nobreak >nul
exit /b 0
