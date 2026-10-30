@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Abstrator — Preparação do Ambiente

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║         ABSTRATOR — Preparação do Ambiente           ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: ── 1. Verificar Python ───────────────────────────────────────────────────────
echo [1/7] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERRO: Python nao encontrado. Instale Python 3.12+ de https://python.org
    goto :falhou
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   OK: Python %PYVER%

:: ── 2. Verificar / Instalar uv ────────────────────────────────────────────────
echo.
echo [2/7] Verificando uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo   uv nao encontrado. Instalando via pip...
    pip install uv --quiet
    if errorlevel 1 (
        echo   ERRO: Falha ao instalar uv.
        goto :falhou
    )
    echo   OK: uv instalado.
) else (
    for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo   OK: %%v
)

:: ── 3. Criar / sincronizar ambiente virtual ───────────────────────────────────
echo.
echo [3/7] Sincronizando dependencias com uv...
uv sync
if errorlevel 1 (
    echo   ERRO: uv sync falhou. Verifique pyproject.toml e conexao de rede.
    goto :falhou
)
echo   OK: Ambiente virtual atualizado.

:: ── 4. Copiar .env.example → .env se necessario ──────────────────────────────
echo.
echo [4/7] Verificando arquivo .env...
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo   AVISO: .env criado a partir de .env.example.
        echo   ACAO NECESSARIA: Edite .env e preencha OPENCODE_API_KEY e outras variaveis.
    ) else (
        echo   AVISO: Nem .env nem .env.example encontrados.
    )
) else (
    echo   OK: .env ja existe.
)

:: ── 5. Criar diretorios de dados ──────────────────────────────────────────────
echo.
echo [5/7] Criando diretorios de dados...
if not exist "data" mkdir data
if not exist "runs" mkdir runs
if not exist "docs" mkdir docs
echo   OK: data\, runs\, docs\ prontos.

:: ── 6. Docker / SearXNG ───────────────────────────────────────────────────────
echo.
echo [6/7] Verificando Docker e SearXNG...
docker info >nul 2>&1
if errorlevel 1 (
    echo   AVISO: Docker nao esta rodando ou nao esta instalado.
    echo   Inicie o Docker Desktop e execute este script novamente, ou use um SearXNG externo.
    echo   Continuando sem SearXNG...
    goto :sem_searxng
)

:: Verifica se o container searxng já existe
docker ps -a --format "{{.Names}}" 2>nul | findstr /I "searxng" >nul
if errorlevel 1 (
    echo   Subindo SearXNG via docker-compose...
    docker compose up -d 2>&1
    if errorlevel 1 (
        echo   AVISO: docker compose falhou. Tentando docker-compose (legado)...
        docker-compose up -d 2>&1
    )
) else (
    docker compose start >nul 2>&1
    echo   OK: Container SearXNG iniciado.
)

:: Aguardar SearXNG ficar pronto (max 30s)
echo   Aguardando SearXNG ficar pronto...
set /a TENTATIVAS=0
:aguardar_searxng
set /a TENTATIVAS+=1
if !TENTATIVAS! GTR 15 (
    echo   AVISO: SearXNG nao respondeu em 30s. Continuando mesmo assim.
    goto :sem_searxng
)
curl -s -o nul -w "%%{http_code}" http://localhost:8080/healthz 2>nul | findstr "200" >nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto :aguardar_searxng
)
echo   OK: SearXNG respondendo em http://localhost:8080

:sem_searxng

:: ── 7. Verificacao de saude (doctor) ─────────────────────────────────────────
echo.
echo [7/7] Executando verificacao de saude...
uv run abstrator doctor 2>&1
if errorlevel 1 (
    echo   AVISO: Alguns checks falharam (ver saida acima).
    echo   O sistema pode funcionar parcialmente dependendo das configuracoes.
) else (
    echo   OK: Todos os checks passaram.
)

:: ── Sucesso ───────────────────────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║              AMBIENTE PRONTO!                        ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Comandos uteis:                                     ║
echo ║   uv run abstrator run "meu topico"   - pesquisar   ║
echo ║   uv run abstrator mcp               - servidor MCP ║
echo ║   uv run abstrator runs              - listar runs  ║
echo ║   uv run abstrator doctor            - checar saude ║
echo ╚══════════════════════════════════════════════════════╝
echo.
endlocal
exit /b 0

:falhou
echo.
echo   FALHA na preparacao do ambiente. Corrija os erros acima e tente novamente.
echo.
endlocal
exit /b 1
