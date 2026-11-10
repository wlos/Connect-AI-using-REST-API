@echo off
rem Reuse the API course folder inside the TAFE working directory.
cd /d C:\ProgramData\Laragon\www
if errorlevel 1 goto failed
if not exist api_ss mkdir api_ss
if errorlevel 1 goto failed
cd api_ss
if errorlevel 1 goto failed

rem Reuse .venv if present; otherwise create it, then activate it.
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\activate.bat
if errorlevel 1 goto failed

rem Require a Python version supported by the lesson.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto python_required

python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install --upgrade fastmcp requests httpx ipykernel jupyterlab arxiv
if errorlevel 1 goto failed

rem Register the teaching kernel inside this environment, without a user-wide install.
python -m ipykernel install --prefix "%CD%\.venv" --name api_ss --display-name "Python (api_ss)"
if errorlevel 1 goto failed

rem Define course paths only after the required setup steps succeed.
set "API_SS_PATH=%CD%"
echo.
echo Setup complete. The .venv environment is active in %API_SS_PATH%.
echo API_SS_PATH=%API_SS_PATH%
echo.
echo Save weather_mcp_server.py in this working folder before starting the server.
echo Start Jupyter from this window using the active environment:
echo   python -m jupyterlab
echo Select the Python (api_ss) kernel when opening the notebook.
echo.

echo Terminal 1 - start the weather MCP server:
echo   python weather_mcp_server.py
echo Terminal 2 - activate the same environment, then run the client:
echo   python mcp_client.py
echo Or run the chatbot:
echo   python mcp_chatbot.py
echo.

:ready
rem Leave an interactive Command Prompt open with the environment and paths available.
cmd /k
exit /b 0

:python_required
echo Python 3.10 or newer must be available as python before running this script.
goto failed

:failed
echo Setup failed. Check the error above or ask your lecturer for help.
pause
exit /b 1
