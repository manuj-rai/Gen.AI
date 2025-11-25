@echo off
echo ====================================
echo Starting Portfolio Q&A Backend
echo ====================================
echo.

REM Check if .env file exists
if not exist .env (
    echo ⚠️  WARNING: .env file not found!
    echo.
    echo Please create a .env file with:
    echo OPENAI_API_KEY=your_api_key_here
    echo SOURCE_URL=https://manuj-rai.vercel.app/
    echo PDF_PATH=Manuj Rai.pdf
    echo.
    pause
    exit /b
)

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    pause
    exit /b
)

echo ✅ Python found
echo.

REM Check if virtual environment exists
if exist venv (
    echo ✅ Virtual environment found. Activating...
    call venv\Scripts\activate.bat
) else (
    echo ℹ️  No virtual environment found. Using global Python.
)

echo.
echo 📦 Installing/updating dependencies...
pip install -r requirements.txt --quiet

echo.
echo 🚀 Starting Flask server...
echo Server will be available at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
echo ====================================
echo.

python app.py

pause
