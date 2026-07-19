@echo off
setlocal

echo ==============================================================================
echo OMEGA V5 - FULL SYSTEM BOOTSTRAP (WINDOWS)
echo ==============================================================================

REM --- 1. Dependency Check ---
echo [1/5] Checking dependencies...

REM Check for Rust/Cargo
where cargo >nul 2>nul
if %errorlevel% neq 0 (
    echo   - Rust (cargo) not found. Please install from https://rustup.rs/
    goto :error
) else (
    echo   - Rust (cargo) found.
)

REM Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo   - Python not found. Please install from https://www.python.org/
    goto :error
) else (
    echo   - Python found.
)

REM Check for Node/npm (for pm2)
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo   - Node.js (npm) not found. Please install from https://nodejs.org/
    goto :error
) else (
    echo   - Node.js (npm) found.
)

REM --- 2. Environment Setup ---
echo [2/5] Setting up Python environment...
if not exist .venv (
    echo   - Creating virtual environment...
    python -m venv .venv
)

echo   - Activating virtual environment and installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt

REM --- 3. .env File Setup ---
echo [3/5] Checking for .env file...
if not exist .env (
    echo   - .env file not found. Creating from .env.example...
    copy .env.example .env
    echo   - IMPORTANT: Please edit the .env file with your private keys and API tokens.
) else (
    echo   - .env file found.
)

REM --- 4. Build Rust Engine ---
echo [4/5] Building Rust engine...
cd rust_engine
cargo build --release
cd ..
if %errorlevel% neq 0 (
    echo   - Rust engine build failed.
    goto :error
)

REM --- 5. Launch Services with PM2 ---
echo [5/5] Launching services with PM2...

REM Check for pm2
where pm2 >nul 2>nul
if %errorlevel% neq 0 (
    echo   - pm2 not found. Installing globally...
    npm install -g pm2
)

echo   - Updating pm2 to the latest version...
pm2 update

echo   - Starting all services via ecosystem.config.cjs...
pm2 start ecosystem.config.cjs

echo.
echo ==============================================================================
pm2 save
echo ✅ Omega V5 system is booting. Monitor status with 'pm2 list' or 'pm2 logs'.
echo ==============================================================================
goto :eof

:error
echo.
echo ❌ Bootstrap failed. Please resolve the errors above and re-run.
pause
exit /b 1

:eof
endlocal