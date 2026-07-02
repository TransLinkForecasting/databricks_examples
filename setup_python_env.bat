@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "UV_DIR=%ROOT%.uv"
set "UV_EXE=%UV_DIR%\uv.exe"
set "UV_ZIP=%TEMP%\uv-x86_64-pc-windows-msvc.zip"
set "MODEL_GROUP=activitysim"

if /I "%~1"=="--group" (
  if "%~2"=="" (
    echo [error] Missing value for --group. Use activitysim or populationsim.
    exit /b 1
  )
  set "MODEL_GROUP=%~2"
  shift
  shift
) else if /I "%~1"=="-g" (
  if "%~2"=="" (
    echo [error] Missing value for -g. Use activitysim or populationsim.
    exit /b 1
  )
  set "MODEL_GROUP=%~2"
  shift
  shift
)

if not "%MODEL_GROUP%"=="" if /I not "%MODEL_GROUP%"=="activitysim" if /I not "%MODEL_GROUP%"=="populationsim" (
  echo [error] Invalid group "%MODEL_GROUP%". Allowed values: activitysim, populationsim.
  exit /b 1
)

if not exist "%UV_DIR%" mkdir "%UV_DIR%"

if not exist "%UV_EXE%" (
  echo [setup] Downloading uv into .uv ...
  where curl >nul 2>&1
  if errorlevel 1 (
    echo [error] curl is required but not found on PATH.
    exit /b 1
  )

  curl -fsSL -o "%UV_ZIP%" "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
  if errorlevel 1 (
    echo [error] Failed to download uv.
    exit /b 1
  )

  tar -xf "%UV_ZIP%" -C "%UV_DIR%"
  if errorlevel 1 (
    echo [error] Failed to extract uv archive.
    exit /b 1
  )
)

set "PATH=%UV_DIR%;%PATH%"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment in .venv ...
  "%UV_EXE%" venv "%ROOT%.venv"
  if errorlevel 1 exit /b 1
)

call "%ROOT%.venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo [setup] Synchronizing dependencies ...
if "%MODEL_GROUP%"=="" (
  "%UV_EXE%" sync --group dev
) else (
  "%UV_EXE%" sync --group dev --group %MODEL_GROUP%
)
if errorlevel 1 exit /b 1

echo [setup] Refreshing uv.lock ...
"%UV_EXE%" lock
if errorlevel 1 exit /b 1

echo [setup] Exporting requirements ...
call "%ROOT%scripts\export_requirements.bat"
if errorlevel 1 exit /b 1

if "%~1"=="" (
  echo [ok] Environment is ready.
  if "%MODEL_GROUP%"=="" (
    echo [ok] dependency group: none ^(dev only^)
  ) else (
    echo [ok] dependency group: %MODEL_GROUP%
  )
  echo [ok] uv: "%UV_EXE%"
  echo [ok] python: "%ROOT%.venv\Scripts\python.exe"
  echo [hint] Run python with: setup_python_env.bat -c "print('hello')"
  echo [hint] Add model group with: setup_python_env.bat --group activitysim
  echo [hint] Or: setup_python_env.bat --group populationsim
  exit /b 0
)

"%ROOT%.venv\Scripts\python.exe" %*
PAUSE
exit /b %ERRORLEVEL%