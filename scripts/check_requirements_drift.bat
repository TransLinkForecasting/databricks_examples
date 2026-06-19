@echo off
setlocal EnableExtensions

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "CANONICAL_PATH=%~1"
if "%CANONICAL_PATH%"=="" set "CANONICAL_PATH=requirements\requirements-serverless.txt"

if not exist "%CANONICAL_PATH%" (
  echo [error] Canonical requirements file not found: %CANONICAL_PATH%
  exit /b 1
)

set "UV_EXE=%ROOT%.uv\uv.exe"
if not exist "%UV_EXE%" (
  set "UV_EXE=uv"
)

set "TEMP_FILE=%TEMP%\requirements-generated-%RANDOM%%RANDOM%.txt"

%UV_EXE% lock --check
if errorlevel 1 exit /b 1

%UV_EXE% export --format requirements-txt --no-dev -o "%TEMP_FILE%"
if errorlevel 1 exit /b 1

fc /b "%CANONICAL_PATH%" "%TEMP_FILE%" >nul
if errorlevel 1 (
  del /q "%TEMP_FILE%" >nul 2>&1
  echo [error] requirements-serverless.txt is stale. Run scripts\export_requirements.bat and commit changes.
  exit /b 1
)

del /q "%TEMP_FILE%" >nul 2>&1
echo Dependency artifact is aligned with uv.lock
exit /b 0