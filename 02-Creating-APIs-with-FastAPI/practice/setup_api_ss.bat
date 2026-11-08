@echo off
rem Create the course folder inside the TAFE working directory.
cd /d C:\ProgramData\Laragon\www
if errorlevel 1 goto failed
if not exist api_ss mkdir api_ss
if errorlevel 1 goto failed
cd api_ss
if errorlevel 1 goto failed

rem Create the environment if it does not already exist, then activate it.
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\activate.bat
if errorlevel 1 goto failed

rem Install the course libraries in the active environment.
python -m pip install fastapi uvicorn requests httpx ipykernel pandas arxiv google-genai
if errorlevel 1 goto failed

rem Define the course path after all setup steps succeed.
set "API_SS_PATH=%CD%"
echo Setup complete. The .venv environment is active in %API_SS_PATH%.
echo API_SS_PATH=%API_SS_PATH%
rem Leave an interactive Command Prompt open in this folder.
cmd /k
exit /b 0

:failed
echo Setup failed. Check the error above or ask your lecturer for help.
pause
exit /b 1
