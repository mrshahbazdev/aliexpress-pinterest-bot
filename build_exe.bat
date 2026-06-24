@echo off
REM ============================================================
REM  Build AE-Pinner as a standalone Windows executable
REM  Run this on Windows with Python 3.10+ installed
REM ============================================================

echo.
echo  AliExpress-Pinterest Bot - EXE Builder
echo  =======================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -e . >nul 2>&1
pip install pyinstaller >nul 2>&1

REM Build
echo [2/3] Building executable...
pyinstaller --onefile --name ae-pinner ^
  --hidden-import=ae_pinner.web ^
  --hidden-import=ae_pinner.database ^
  --hidden-import=ae_pinner.ai_generator ^
  --hidden-import=ae_pinner.aliexpress ^
  --hidden-import=ae_pinner.config ^
  --hidden-import=ae_pinner.bot ^
  --hidden-import=ae_pinner.pinterest ^
  --hidden-import=mysql.connector ^
  --hidden-import=mysql.connector.plugins ^
  --hidden-import=mysql.connector.plugins.caching_sha2_password ^
  --hidden-import=mysql.connector.plugins.mysql_native_password ^
  --collect-all flask ^
  --collect-all jinja2 ^
  --collect-all mysql.connector ^
  src/ae_pinner/cli.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo [3/3] Done!
echo.
echo  EXE file: dist\ae-pinner.exe
echo.
echo  Usage:
echo    dist\ae-pinner.exe web --port 5000
echo    Then open http://localhost:5000 in your browser
echo.
pause
