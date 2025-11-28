@echo off
echo ================================
echo  Testing Flask Connection
echo ================================
echo.
echo Testing if Flask is accessible...
echo.
curl http://localhost:5000/login.html
echo.
echo.
if %ERRORLEVEL% EQU 0 (
    echo ✅ SUCCESS! Flask is running and accessible!
    echo You can now start LocalTunnel.
) else (
    echo ❌ FAILED! Flask is not accessible.
    echo Make sure Flask is running first with start_flask.bat
)
echo.
pause

