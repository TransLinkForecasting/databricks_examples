@echo off
setlocal EnableExtensions

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "OUTPUT_PATH=%~1"
if "%OUTPUT_PATH%"=="" set "OUTPUT_PATH=requirements\requirements-standard.txt"

set "UV_EXE=%ROOT%.uv\uv.exe"
if not exist "%UV_EXE%" (
  set "UV_EXE=uv"
)

%UV_EXE% lock
if errorlevel 1 exit /b 1

%UV_EXE% export --format requirements-txt --no-dev -o "%OUTPUT_PATH%"
if errorlevel 1 exit /b 1

echo Exported pinned runtime dependencies to %OUTPUT_PATH%
exit /b 0