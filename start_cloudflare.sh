#!/bin/bash
echo "================================"
echo " AI Drowsy Detection - Cloudflare Tunnel"
echo "================================"
echo ""
echo "Starting Cloudflare tunnel on port 5000..."
echo ""
echo "Make sure Flask is running in another terminal!"
echo ""

# Check if cloudflared is installed
if command -v cloudflared &> /dev/null; then
    echo "✅ Found cloudflared in PATH"
    echo ""
    cloudflared tunnel --url http://127.0.0.1:5000
elif [ -f "./cloudflared" ]; then
    echo "✅ Found cloudflared in current directory"
    echo ""
    ./cloudflared tunnel --url http://127.0.0.1:5000
elif [ -f "./cloudflared-darwin-amd64" ]; then
    echo "✅ Found cloudflared-darwin-amd64 in current directory"
    echo ""
    ./cloudflared-darwin-amd64 tunnel --url http://127.0.0.1:5000
elif [ -f "./cloudflared-darwin-arm64" ]; then
    echo "✅ Found cloudflared-darwin-arm64 in current directory"
    echo ""
    ./cloudflared-darwin-arm64 tunnel --url http://127.0.0.1:5000
else
    echo "❌ ERROR: cloudflared not found!"
    echo ""
    echo "Please install cloudflared using one of these methods:"
    echo ""
    echo "Method 1: Using Homebrew (Recommended)"
    echo "  brew install cloudflared"
    echo ""
    echo "Method 2: Download manually"
    echo "  1. Go to: https://github.com/cloudflare/cloudflared/releases/latest"
    if [[ $(uname -m) == "arm64" ]]; then
        echo "  2. Download: cloudflared-darwin-arm64"
        echo "  3. Rename it to: cloudflared"
        echo "  4. Place it in this folder: $(pwd)"
        echo "  5. Make it executable: chmod +x cloudflared"
    else
        echo "  2. Download: cloudflared-darwin-amd64"
        echo "  3. Rename it to: cloudflared"
        echo "  4. Place it in this folder: $(pwd)"
        echo "  5. Make it executable: chmod +x cloudflared"
    fi
    echo ""
    echo "After installing, run this script again!"
    echo ""
    exit 1
fi



