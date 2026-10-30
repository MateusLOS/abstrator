@echo off
if not "%~1"=="--run" ( cmd /k "%~f0" --run & exit /b )
setlocal EnableExtensions EnableDelayedExpansion

title Abstrator MCP - Iniciando

echo ========================================
echo   ABSTRATOR MCP - INICIANDO
echo ========================================
echo.

cd /d "%~dp0"

if not exist "pyproject.toml" (
    echo [FALHA] Nao encontrei pyproject.toml nesta pasta.
    echo         Execute este arquivo de dentro de C:\Projetos\abstrator
    pause
    exit /b 1
)
echo [OK] Pasta correta: %CD%
echo.

if not exist ".venv\Scripts\abstrator.exe" (
    echo [FALHA] Ambiente virtual nao encontrado.
    echo         Execute preparar.bat primeiro.
    pause
    exit /b 1
)
echo [OK] .venv encontrado
echo.

REM -- Docker -----------------------------------------------------------------
set DOCKER_BIN=C:\Program Files\Docker\Docker\resources\bin\docker.exe
if not exist "%DOCKER_BIN%" set DOCKER_BIN=docker

echo [CHECK] Verificando Docker...
"%DOCKER_BIN%" version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Docker nao responde. Tentando iniciar Docker Desktop...
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        echo [INFO] Aguardando Docker iniciar (ate 2 minutos)...
        set /a DATT=0
        :WAITDOCKER
        timeout /t 5 /nobreak >nul
        "%DOCKER_BIN%" version >nul 2>&1
        if not errorlevel 1 goto DOCKER_OK
        set /a DATT+=1
        if !DATT! lss 24 goto WAITDOCKER
        echo [FALHA] Docker nao respondeu. Abra o Docker Desktop manualmente e tente novamente.
        pause
        exit /b 1
    ) else (
        echo [AVISO] Docker Desktop nao encontrado. Continuando sem SearXNG...
        goto STARTMCP
    )
)
:DOCKER_OK
echo [OK] Docker pronto
echo.

REM -- SearXNG ----------------------------------------------------------------
echo [CHECK] Subindo SearXNG...
"%DOCKER_BIN%" compose up -d searxng >nul 2>&1

echo [CHECK] Aguardando SearXNG ficar pronto...
set /a SATT=0
:WAITSEARXNG
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "try{$r=Invoke-WebRequest -Uri 'http://localhost:8080/search?q=test&format=json' -UseBasicParsing -TimeoutSec 5; if($r.StatusCode -eq 200){exit 0}}catch{}; exit 1" >nul 2>&1
if not errorlevel 1 (
    echo [OK] SearXNG online em http://localhost:8080
    goto STARTMCP
)
set /a SATT+=1
if !SATT! lss 18 (
    timeout /t 5 /nobreak >nul
    goto WAITSEARXNG
)
echo [AVISO] SearXNG nao respondeu ainda, mas continuando...

REM -- MCP --------------------------------------------------------------------
:STARTMCP
echo.
echo [INFO] Iniciando servidor MCP...
set MCP_CMD=.\.venv\Scripts\abstrator.exe mcp
start "ABSTRATOR-MCP" cmd /k %MCP_CMD%
timeout /t 3 /nobreak >nul

echo [OK] Servidor MCP iniciando na janela "ABSTRATOR-MCP"
echo.
echo ========================================
echo   PRONTO
echo ========================================
echo.
echo O provider e modelo serao lidos do .env (ou variaveis de ambiente).
echo.
echo Para registrar no Claude Code (se ainda nao fez):
echo   claude mcp add abstrator -- uv --directory "%CD%" run abstrator mcp
echo.
echo NAO FECHE a janela ABSTRATOR-MCP enquanto estiver usando.
echo.
pause
endlocal
