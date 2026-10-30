@echo off
if not "%~1"=="--run" ( cmd /k "%~f0" --run & exit /b )
setlocal EnableExtensions EnableDelayedExpansion

title Abstrator MCP - Iniciando

echo ==========================================
echo   ABSTRATOR MCP - INICIANDO
echo ==========================================
echo.

cd /d "%~dp0"

if not exist "pyproject.toml" (
    echo [FALHA] Execute este .bat de dentro de C:\Projetos\abstrator
    pause & exit /b 1
)
echo [OK] Pasta: %CD%
echo.

if not exist ".venv\Scripts\abstrator.exe" (
    echo [FALHA] Ambiente virtual nao encontrado.
    echo         Execute preparar.bat primeiro.
    pause & exit /b 1
)
echo [OK] .venv encontrado
echo.

:: -- Docker ------------------------------------------------------------------
set DOCKER_OK=0
docker version >nul 2>&1
if not errorlevel 1 set DOCKER_OK=1

if %DOCKER_OK%==0 (
    echo [INFO] Docker nao responde. Tentando iniciar Docker Desktop...
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        echo [INFO] Aguardando Docker (ate 2 min)...
        set /a DTRY=0
        :WAIT_DOCKER
        timeout /t 5 /nobreak >nul
        docker version >nul 2>&1
        if not errorlevel 1 ( set DOCKER_OK=1 & goto DOCKER_DONE )
        set /a DTRY+=1
        if !DTRY! lss 24 goto WAIT_DOCKER
        echo [AVISO] Docker nao respondeu. Continuando sem SearXNG.
        goto START_MCP
    ) else (
        echo [AVISO] Docker Desktop nao encontrado. Continuando sem SearXNG.
        goto START_MCP
    )
)

:DOCKER_DONE
echo [OK] Docker pronto
echo.

:: -- SearXNG -----------------------------------------------------------------
echo [CHECK] Subindo SearXNG...
docker compose up -d searxng >nul 2>&1

echo [CHECK] Aguardando SearXNG ficar pronto...
set /a STRY=0
:WAIT_SEARXNG
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "try{if((Invoke-WebRequest 'http://127.0.0.1:8888/' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200){exit 0}}catch{};exit 1" >nul 2>&1
if not errorlevel 1 ( echo [OK] SearXNG online & goto START_MCP )
set /a STRY+=1
if !STRY! lss 18 ( timeout /t 5 /nobreak >nul & goto WAIT_SEARXNG )
echo [AVISO] SearXNG ainda nao respondeu, continuando assim mesmo...

:: -- MCP ---------------------------------------------------------------------
:START_MCP
echo.
echo [INFO] Iniciando servidor MCP em nova janela...
start "ABSTRATOR-MCP" cmd /k ".\.venv\Scripts\abstrator.exe mcp"
timeout /t 3 /nobreak >nul

echo [OK] Servidor MCP rodando na janela "ABSTRATOR-MCP"
echo.
echo ==========================================
echo   CONFIGURACAO MCP
echo ==========================================
echo.
echo Claude Code (se ainda nao registrou):
echo   claude mcp add abstrator -- uv --directory "%CD%" run abstrator mcp
echo.
echo Claude Desktop (%APPDATA%\Claude\claude_desktop_config.json):
echo   "abstrator": { "command": "uv", "args": ["--directory","%CD%","run","abstrator","mcp"] }
echo.
echo NAO FECHE a janela "ABSTRATOR-MCP" enquanto estiver usando.
echo.
pause
endlocal
