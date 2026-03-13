@echo off
echo.
echo ================================================
echo  Blog Pipeline - Setup
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create venv
    pause
    exit /b 1
)
echo Done.

echo [2/4] Activating venv...
call venv\Scripts\activate.bat
echo Done.

echo [3/4] Installing packages (1-3 min)...
pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo Done.

echo [4/4] Creating folders...
if not exist "data\bigkinds" mkdir data\bigkinds
if not exist "logs" mkdir logs
echo Done.

echo.
echo ================================================
echo  Setup complete!
echo  1. Copy .env.example to .env
echo  2. Fill in API keys in .env
echo  3. Run run.bat
echo ================================================
echo.
pause
