@echo off
if not "%~1"=="--run" ( cmd /k "%~f0" --run & exit /b )
setlocal EnableDelayedExpansion

title Abstrator - Preparacao do Ambiente

echo.
echo ==========================================
echo   ABSTRATOR - PREPARACAO DO AMBIENTE
echo ==========================================
echo.

cd /d "%~dp0"

if not exist "pyproject.toml" (
    echo [FALHA] Execute este .bat de dentro de C:\Projetos\abstrator
    pause & exit /b 1
)

:: -- 1. Python ----------------------------------------------------------------
echo [1/7] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERRO: Python nao encontrado. Instale em https://python.org
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   OK: Python %%v

:: -- 2. uv -------------------------------------------------------------------
echo.
echo [2/7] Verificando uv...
set UV=uv
where uv >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo   OK: %%v
    goto UV_PRONTO
)

:: uv nao esta no PATH — tentar via python -m uv primeiro
python -m uv --version >nul 2>&1
if not errorlevel 1 (
    set UV=python -m uv
    for /f "tokens=*" %%v in ('python -m uv --version 2^>^&1') do echo   OK (via python -m uv^): %%v
    goto UV_PRONTO
)

:: nenhum funciona: instalar
echo   uv nao encontrado. Instalando via pip...
pip install uv --quiet
if errorlevel 1 ( echo   ERRO: falha ao instalar uv. & pause & exit /b 1 )

:: Apos instalar, PATH ainda nao atualizado — usar python -m uv
python -m uv --version >nul 2>&1
if errorlevel 1 ( echo   ERRO: uv instalado mas nao responde. Reinicie o terminal. & pause & exit /b 1 )
set UV=python -m uv
echo   OK: uv instalado e disponivel via python -m uv

:UV_PRONTO

:: -- 3. Dependencias ----------------------------------------------------------
echo.
echo [3/7] Sincronizando dependencias...
%UV% sync
if errorlevel 1 (
    echo   ERRO: sync falhou. Verifique pyproject.toml e conexao de rede.
    pause & exit /b 1
)
echo   OK: Ambiente virtual atualizado.

:: -- 4. .env -----------------------------------------------------------------
echo.
echo [4/7] Verificando .env...
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo   AVISO: .env criado a partir de .env.example.
        echo   ACAO: Edite .env e preencha suas chaves de API.
    ) else (
        echo   AVISO: Nem .env nem .env.example encontrados.
    )
) else (
    echo   OK: .env ja existe.
)

:: -- 5. Diretorios -----------------------------------------------------------
echo.
echo [5/7] Criando diretorios de dados...
if not exist "data" mkdir data
if not exist "runs" mkdir runs
if not exist "docs" mkdir docs
echo   OK: data\, runs\, docs\ prontos.

:: -- 6. Docker / SearXNG -----------------------------------------------------
echo.
echo [6/7] Verificando Docker e SearXNG...
docker info >nul 2>&1
if errorlevel 1 (
    echo   AVISO: Docker nao esta rodando. Inicie o Docker Desktop e execute novamente.
    echo   Continuando sem SearXNG...
    goto SEM_SEARXNG
)

docker compose up -d >nul 2>&1
if errorlevel 1 docker-compose up -d >nul 2>&1
echo   SearXNG iniciado. Aguardando ficar pronto...

set /a STRY=0
:WAIT_SEARXNG
set /a STRY+=1
if !STRY! gtr 15 (
    echo   AVISO: SearXNG nao respondeu em 30s. Continuando mesmo assim.
    goto SEM_SEARXNG
)
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "try{if((Invoke-WebRequest 'http://127.0.0.1:8888/' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200){exit 0}}catch{};exit 1" >nul 2>&1
if not errorlevel 1 goto SEARXNG_OK
timeout /t 2 /nobreak >nul
goto WAIT_SEARXNG
:SEARXNG_OK
echo   OK: SearXNG online em http://localhost:8888

:SEM_SEARXNG

:: -- 7. Doctor ---------------------------------------------------------------
echo.
echo [7/7] Executando verificacao de saude...
%UV% run abstrator doctor 2>&1
if errorlevel 1 (
    echo   AVISO: Alguns checks falharam. Veja o log acima.
) else (
    echo   OK: Todos os checks passaram.
)

echo.
echo ==========================================
echo   AMBIENTE PRONTO
echo ==========================================
echo.
echo   %UV% run abstrator run "meu topico"   - pesquisar
echo   %UV% run abstrator mcp                - servidor MCP
echo   %UV% run abstrator doctor             - checar saude
echo.
pause
endlocal
