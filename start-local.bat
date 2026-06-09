@echo off
setlocal

set "BACKEND_PORT=%~1"
set "FRONTEND_PORT=%~2"
if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=3000"

set "ROOT=%~dp0"
set "WEB_ROOT=%ROOT%web"

if not exist "%ROOT%main.py" (
  echo main.py not found. Please put this BAT in the project root.
  pause
  exit /b 1
)

if not exist "%WEB_ROOT%\package.json" (
  echo web\package.json not found. Frontend directory is missing.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%G in (`where git.exe 2^>nul`) do (
  if not defined GIT_EXE set "GIT_EXE=%%G"
)

if not defined GIT_EXE if exist "C:\Program Files\Git\cmd\git.exe" (
  set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
)

if not defined GIT_EXE if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd\git.exe" (
  set "GIT_EXE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd\git.exe"
)

if exist "%USERPROFILE%\miniconda3\python.exe" (
  set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Python environment is missing uvicorn.
  echo Current Python: %PYTHON_EXE%
  echo Please install dependencies in this Python environment, or edit PYTHON_EXE in start-local.bat.
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
  echo Backend port %BACKEND_PORT% is already in use.
  echo Stop the old backend first, or run: start-local.bat 8001 %FRONTEND_PORT%
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %FRONTEND_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
  echo Frontend port %FRONTEND_PORT% is already in use.
  echo Stop the old frontend first, or run: start-local.bat %BACKEND_PORT% 3001
  pause
  exit /b 1
)

start "chatgpt2api backend" cmd /k "cd /d ""%ROOT%"" && set ""PYTHONPATH=."" && set ""GIT_PYTHON_REFRESH=quiet"" && set ""GIT_PYTHON_GIT_EXECUTABLE=%GIT_EXE%"" && ""%PYTHON_EXE%"" -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%"

timeout /t 2 /nobreak >nul

start "chatgpt2api frontend" cmd /k "cd /d ""%WEB_ROOT%"" && npm run dev -- -p %FRONTEND_PORT%"

echo.
echo Local chatgpt2api is starting...
echo Backend:  http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo.
echo Login key: chatgpt2api
echo Close the two opened command windows to stop the services.
echo.
pause
