@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Abstrator MCP - Inicializador Completo

echo ========================================
echo   ABSTRATOR MCP - INICIANDO TUDO
echo ========================================
echo.
echo Pasta: %CD%
echo.

if not exist "pyproject.toml" (
    echo [FALHA] Rode este arquivo dentro de C:\Projetos\abstrator
    pause
    exit /b 1
)
cd /d "%~dp0"
echo [OK] Na pasta correta
echo.

set GEMINI_CLI_TRUST_WORKSPACE=true
set ABSTRATOR_LLM_PROVIDER=gemini_cli
set ABSTRATOR_GEMINI_CLI_MODEL=gemini-3.5-flash-lite

echo [OK] Variaveis de ambiente definidas
echo.

if not exist ".venv\Scripts\abstrator.exe" (
    echo [FALHA] .venv\Scripts\abstrator.exe nao encontrado
    pause
    exit /b 1
)
echo [OK] .venv\Scripts\abstrator.exe encontrado
echo.

set DOCKER_BIN=C:\Program Files\Docker\Docker\resources\bin\docker.exe
echo [CHECK] Verificando Docker Desktop...
"%DOCKER_BIN%" version --format "{{.Server.Version}}" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Iniciando Docker Desktop...
    if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
        start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        echo [INFO] Aguardando motor do Docker...
        timeout /t 40 /nobreak >nul
    )
    set ATT=0
    :WAITD
    "%DOCKER_BIN%" version --format "{{.Server.Version}}" >nul 2>&1
    if not errorlevel 1 goto DOCKEROK2
    set /a ATT+=1
    if %ATT% geq 25 (
        echo [FALHA] Nao consegui conectar ao Docker
        echo         Abra o Docker Desktop e espere "Engine running" e rode este .bat novamente
        pause
        exit /b 1
    )
    timeout /t 5 /nobreak >nul
    goto WAITD
)
:DOCKEROK2
echo [OK] Docker pronto
echo.

echo [CHECK] Subindo SearXNG...
"%DOCKER_BIN%" compose up -d searxng >nul 2>&1
timeout /t 12 /nobreak >nul
echo [OK] Comando para subir SearXNG enviado
echo.

echo [CHECK] Aguardando SearXNG responder...
set SATT=0
:WAITSEARX
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "try{ $r=Invoke-WebRequest -Uri 'http://localhost:8080/search?q=test&format=json' -UseBasicParsing -Headers @{'User-Agent'='Abstrator/0.1'} -TimeoutSec 7; if($r.StatusCode -eq 200 -and $r.Content -match 'results'){exit 0}}catch{}; exit 1" >nul 2>&1
if not errorlevel 1 (
    echo [OK] SearXNG online
    goto STARTMCP
)
set /a SATT+=1
if %SATT% geq 18 (
    echo [AVISO] SearXNG ainda inicializando, mas vou seguir assim mesmo
    goto STARTMCP
)
timeout /t 5 /nobreak >nul
goto WAITSEARX

:STARTMCP
echo.
echo [INFO] Iniciando servidor MCP em nova janela...
start "ABSTRATOR-MCP" cmd /k "cd /d "%CD%" && set GEMINI_CLI_TRUST_WORKSPACE=true && set ABSTRATOR_LLM_PROVIDER=gemini_cli && set ABSTRATOR_GEMINI_CLI_MODEL=gemini-3.5-flash-lite && ".\.venv\Scripts\abstrator.exe" mcp"
timeout /t 4 /nobreak >nul
echo [OK] Servidor MCP rodando na janela ABSTRATOR-MCP
echo.

echo ========================================
echo   CONFIGURAÇÃO PARA O OPENCODE
echo ========================================
echo.
echo Crie/edite na raiz do projeto que voce vai abrir com o OpenCode:
echo   opencode.json
echo.
echo Cole exatamente isto:
echo.
echo {
echo   "$schema": "https://opencode.ai/config.json",
echo   "mcp": {
echo     "abstrator": {
echo       "type": "local",
echo       "command": ["%CD:\=\\%\\.venv\\Scripts\\abstrator.exe", "mcp"],
echo       "enabled": true,
echo       "environment": {
echo         "GEMINI_CLI_TRUST_WORKSPACE": "true",
echo         "ABSTRATOR_LLM_PROVIDER": "gemini_cli",
echo         "ABSTRATOR_GEMINI_CLI_MODEL": "gemini-3.5-flash-lite"
echo       }
echo     }
echo   }
echo }
echo.
echo ========================================
echo.
echo PRONTO. Abra o OpenCode na pasta com esse opencode.json e converse normalmente.
echo NAO FECHE a janela ABSTRATOR-MCP enquanto estiver usando.
echo.
pause
endlocal
