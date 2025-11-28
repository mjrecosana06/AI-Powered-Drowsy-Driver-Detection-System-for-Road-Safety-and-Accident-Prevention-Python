@echo off
echo ================================
echo  AI Drowsy Detection - Flask
echo ================================
echo.
echo Activating virtual environment...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo Virtual environment activated!
) else (
    echo Warning: Virtual environment not found. Using system Python.
)
echo.
echo Setting Flask to accept network connections...
set FLASK_HOST=0.0.0.0
set FLASK_PORT=5000
echo.
echo Starting Flask server...
echo IMPORTANT: Wait until you see "Running on http://0.0.0.0:5000"
echo Then start ngrok in another window by double-clicking start_ngrok.bat!
echo.
python app.py
pause

