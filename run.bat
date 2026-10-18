@echo off
REM ============================================================
REM  VYRO Backend - Windows Quick Start (CMD)
REM
REM  Usage:
REM    run.bat             install deps + migrate + start server
REM    run.bat --seed      also seed demo data (idempotent)
REM    run.bat --dbinit    create tables without Alembic (fallback)
REM
REM  Requirement: Python 3.11+  (https://www.python.org/downloads/)
REM  During Python install CHECK "Add python.exe to PATH".
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo  ================== VYRO Backend (Windows) ==================
echo.

REM ---------- 1) Check Python ----------
where python >nul 2>&1
if errorlevel 1 goto :nopython
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [1/5] Python %PYVER% found.

REM ---------- 2) Virtual environment ----------
if exist ".venv\Scripts\python.exe" (
    echo  [2/5] Virtual environment already exists.
    goto :deps
)
echo  [2/5] Creating virtual environment ...
python -m venv .venv
if errorlevel 1 goto :venvfail

:deps
set "VPY=%~dp0.venv\Scripts\python.exe"
if exist ".venv\.deps_installed" (
    echo  [3/5] Dependencies already installed. [delete .venv\.deps_installed to reinstall]
    goto :envfile
)
echo  [3/5] Installing dependencies - this may take a few minutes ...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :pipfail
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pipfail
type nul > ".venv\.deps_installed"

:envfile
if exist ".env" (
    echo  [4/5] .env found.
    goto :db
)
if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo  [4/5] Created .env from .env.example
) else (
    echo  [4/5] WARNING: .env not found - defaults will be used.
)

:db
if "%~1"=="--dbinit" (
    echo  [5/5] Creating tables via app.db_init ...
    "%VPY%" -m app.db_init
    if errorlevel 1 goto :dbfail
    goto :seed
)
echo  [5/5] Applying migrations via Alembic ...
"%VPY%" -m alembic upgrade head
if errorlevel 1 goto :dbfail

:seed
if not "%~1"=="--seed" goto :run
echo  Seeding demo data ...
"%VPY%" scripts\seed.py

:run
echo.
echo  ============================================================
echo   Server starting...
echo.
echo   API root      : http://127.0.0.1:8000
echo   Swagger docs  : http://127.0.0.1:8000/docs
echo   ReDoc         : http://127.0.0.1:8000/redoc
echo   Playground    : http://127.0.0.1:8000/playground
echo.
echo   Stop server   : press CTRL+C
echo  ============================================================
echo.
"%VPY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :end

:nopython
echo  [ERROR] Python not found!
echo  1. Download Python 3.11+ : https://www.python.org/downloads/
echo  2. During install CHECK the box "Add python.exe to PATH"
echo  3. Close this window and run run.bat again
pause
exit /b 1

:venvfail
echo  [ERROR] Could not create venv.
pause
exit /b 1

:pipfail
echo  [ERROR] pip install failed. Check your internet connection.
pause
exit /b 1

:dbfail
echo.
echo  [ERROR] Database migration failed - PostgreSQL is probably not reachable.
echo.
echo  Fix options:
echo   A. Make sure PostgreSQL is running and DATABASE_URL in .env is correct.
echo      Default: postgresql+asyncpg://vyro:vyro_secret@127.0.0.1:5432/vyro
echo      Create the user and database in pgAdmin or psql:
echo        CREATE USER vyro WITH PASSWORD 'vyro_secret';
echo        CREATE DATABASE vyro OWNER vyro;
echo   B. Or use Docker for the DB only:
echo        docker run -d --name vyro-db -e POSTGRES_USER=vyro -e POSTGRES_PASSWORD=vyro_secret -e POSTGRES_DB=vyro -p 5432:5432 postgres:16-alpine
echo   C. Or run everything with Docker:  docker compose up --build -d
echo.
pause
exit /b 1

:end
pause
