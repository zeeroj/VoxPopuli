@echo off
cd /d "%~dp0"
echo.
echo    VoxPopuli - Motor de analisis electoral 2027
echo    ============================================
echo.
echo    Abriendo en el navegador...
echo.
start "" http://localhost:8501
streamlit run app.py --server.port 8501
pause
