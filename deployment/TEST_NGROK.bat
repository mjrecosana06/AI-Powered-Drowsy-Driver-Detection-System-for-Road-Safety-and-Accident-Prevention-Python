@echo off
echo ================================
echo  ngrok Connection Test
echo ================================
echo.
echo This will test if ngrok is set up correctly.
echo.
echo Testing ngrok version...
ngrok version
echo.
if %errorlevel% neq 0 (
    echo ❌ ERROR: ngrok not found or not configured!
    echo.
    echo Solutions:
    echo 1. Make sure ngrok.exe is in this folder
    echo 2. Or install ngrok from: https://ngrok.com/download
    echo.
    pause
    exit /b 1
)
echo ✅ ngrok is installed!
echo.
echo Checking ngrok configuration...
ngrok config check
echo.
echo ================================
echo  Next Steps:
echo ================================
echo.
echo 1. If you see errors above, run:
echo    ngrok config add-authtoken YOUR_TOKEN
echo.
echo 2. Get your token from:
echo    https://dashboard.ngrok.com/get-started/your-authtoken
echo.
echo 3. Once configured, run:
echo    start_flask.bat (Terminal 1)
echo    start_ngrok.bat (Terminal 2)
echo.
pause

