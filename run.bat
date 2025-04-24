@echo off
SETLOCAL

REM -- Ensure Python is on PATH
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python and make sure it's on your PATH.
    pause
    exit /b 1
)

REM -- Backend venv setup
echo.
echo === Backend: Checking virtual environment ===
if not exist "backend\venv\Scripts\activate" (
    echo Creating virtual environment in backend\venv...
    python -m venv backend\venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo Activating venv and installing Python requirements...
call backend\venv\Scripts\activate
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
pip install --upgrade pip
pip install -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)


REM -- Frontend dependency setup
echo.
echo === Frontend: Checking Node.js ===
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install from https://nodejs.org/ and rerun this script.
    pause
    exit /b 1
)

echo Checking frontend dependencies...
if not exist "frontend\node_modules" (
    echo Installing frontend npm packages...
    pushd frontend
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
) else (
    echo Frontend dependencies already installed.
)

REM -- Run backend and frontend
echo.
echo === Launching Backend ===
start "Backend" cmd /k "call backend\venv\Scripts\activate && python backend\app.py"

echo === Launching Frontend ===
start "Frontend" cmd /k "cd frontend && npm start"

ENDLOCAL
