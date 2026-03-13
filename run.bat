@echo off
echo.
echo ================================================
echo  Blog Pipeline - Run
echo ================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env file not found.
    echo Copy .env.example to .env and fill in API keys.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py

echo.
echo Done. Check the logs\ folder for results.
pause
