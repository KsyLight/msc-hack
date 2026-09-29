@echo off
setlocal
cd /d "%~dp0"
if not "%~1"=="" if /I not "%~1"=="demo" if /I not "%~1"=="real" (
  echo Usage: start.cmd [demo^|real]
  exit /b 2
)
set "APP_MODE=demo"
if /I "%~1"=="real" set "APP_MODE=real"
if not defined APP_PORT set "APP_PORT=8000"
set "OMP_NUM_THREADS=4"
set "OPENBLAS_NUM_THREADS=4"
if not exist "frontend\dist\index.html" (
  pushd frontend
  call npm.cmd ci --no-audit --no-fund
  if errorlevel 1 exit /b 1
  call npm.cmd run build
  if errorlevel 1 exit /b 1
  popd
)
echo Dashboard: http://localhost:%APP_PORT% ^| API: http://localhost:%APP_PORT%/docs ^| mode: %APP_MODE%
call conda run --no-capture-output -n msc-hack python -m uvicorn backend.main:app --host 127.0.0.1 --port %APP_PORT%
exit /b %errorlevel%
