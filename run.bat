@echo off
echo Starting Insurance Quote Comparison Tool...
cd /d "%~dp0"
call .venv\Scripts\activate 2>nul || call venv\Scripts\activate 2>nul || echo No virtual environment found, using system Python
streamlit run app/main.py --server.port 8501
pause
