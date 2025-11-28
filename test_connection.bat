@echo off
echo ================================
echo  Connection Test Script
echo ================================
echo.

echo Testing Flask connection...
echo.

REM Test if Flask is running on port 5000
curl -s http://localhost:5000/login.html >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Flask is running on port 5000
) else (
    echo [ERROR] Flask is NOT running on port 5000
    echo.
    echo Please start Flask first:
    echo   start_flask.bat
    echo.
)

echo.
echo Testing if port 5000 is accessible...
netstat -ano | findstr :5000 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Port 5000 is in use (Flask should be running)
    echo.
    netstat -ano | findstr :5000
) else (
    echo [WARNING] Port 5000 is not in use
    echo Flask might not be running
)

echo.
echo ================================
echo  Next Steps:
echo ================================
echo.
echo 1. Make sure Flask is running: start_flask.bat
echo 2. Make sure Tunnel is running: start_cloudflare.bat
echo 3. Open tunnel URL in browser
echo 4. Press F12 to open Developer Tools
echo 5. Check Console tab for errors
echo.
pause

