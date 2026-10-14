@echo off
REM Build a single-file, noconsole Windows executable.
REM Run from this folder after: pip install -r requirements.txt

pyinstaller --noconsole --onefile --name LogisticsPDFAuditor ^
  --collect-all tkinterdnd2 ^
  --collect-all google.genai ^
  --hidden-import=PIL._tkinter_finder ^
  --hidden-import=pandas ^
  --collect-all pandas ^
  --hidden-import=fitz ^
  main.py

echo.
echo Output: dist\LogisticsPDFAuditor.exe
echo Place .env (GEMINI_API_KEY) next to the .exe. The Consignee DB is fetched live.
pause
