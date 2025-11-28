#!/bin/bash
echo "================================"
echo " AI Drowsy Detection - Flask"
echo "================================"
echo ""
echo "Setting Flask to accept network connections..."
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
echo ""
echo "Starting Flask server..."
echo ""
python3 app.py

