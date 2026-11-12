@echo off
rem 可选交付形态：PyInstaller onedir 独立包（不含源码，运行时配置/技能仍在工作目录）
rem 用法：在源码根目录执行 build_exe.bat，产物在 dist\xAgent\
setlocal
cd /d %~dp0
set "PY=C:\Users\matin\AppData\Local\Programs\Python\Python313\python.exe"
"%PY%" -m PyInstaller --noconfirm --clean --onedir --name xAgent ^
  --add-data "tui\style.tcss;tui" ^
  --collect-submodules mcp --collect-submodules trafilatura ^
  --collect-data textual ^
  --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module pyaudio --exclude-module numpy ^
  main.py
endlocal
