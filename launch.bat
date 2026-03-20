@echo off
echo ============================================================
echo   VENDOR SPEND ANALYSIS — AGENTIC AI DASHBOARD
echo ============================================================
echo.
echo Step 1: Installing required packages...
pip install -r requirements.txt
echo.
echo Step 2: Launching Streamlit dashboard...
echo.
echo   --> Open http://localhost:8501 in your browser
echo   --> Enter your Anthropic API key in the sidebar
echo   --> Select "Use Sample Data" or upload your own CSV
echo.
streamlit run vendor_spend_app.py
pause
