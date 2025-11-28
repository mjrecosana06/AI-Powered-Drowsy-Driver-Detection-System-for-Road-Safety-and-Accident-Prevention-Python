@echo off
echo ================================
echo  AI Drowsy Detection - Cloudflare Tunnel
echo ================================
echo.
echo Starting Cloudflare tunnel on port 5000...
echo.
echo Make sure Flask is running in another terminal!
echo.
echo If cloudflared.exe is not found, download it from:
echo https://github.com/cloudflare/cloudflared/releases
echo.
if exist cloudflared.exe (
    cloudflared tunnel --url http://127.0.0.1:5000
) else (
    echo ERROR: cloudflared.exe not found!
    echo.
    echo Please download cloudflared.exe and place it in this folder.
    echo Download from: https://github.com/cloudflare/cloudflared/releases
    echo.
    pause
)

