@echo off
rem Create the course folder inside the TAFE working directory.
cd /d C:\ProgramData\Laragon\www
if errorlevel 1 goto failed
if not exist mcp_ss mkdir mcp_ss
if errorlevel 1 goto failed
cd mcp_ss
if errorlevel 1 goto failed

rem Require a Python version supported by the lesson.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto python_required

rem Create the notebook environment, then install current course libraries.
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\activate.bat
if errorlevel 1 goto failed
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install --upgrade fastmcp requests httpx ipykernel jupyterlab arxiv
if errorlevel 1 goto failed

rem Register the teaching kernel inside this environment, without a user-wide install.
python -m ipykernel install --prefix "%CD%\.venv" --name mcp_ss --display-name "Python (mcp_ss)"
if errorlevel 1 goto failed

rem Define course paths only after the required setup steps succeed.
set "MCP_SS_PATH=%CD%"
echo.
echo Setup complete. The .venv environment is active in %MCP_SS_PATH%.
echo MCP_SS_PATH=%MCP_SS_PATH%
echo.
echo Save weather_mcp_server.py in this working folder before starting the server.
echo Start Jupyter from this window using the active environment:
echo   python -m jupyterlab
echo Select the Python (mcp_ss) kernel when opening the notebook.
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
