# Abstrator

> Pesquisa por abstração recursiva — decompõe qualquer ideia, pesquisa cada sub-conceito por múltiplas lentes nomeadas e sintetiza o resultado em JSON estruturado com fontes citadas.

## O que é

O Abstrator é um **servidor MCP + CLI** que recebe uma pergunta ou tópico e executa uma cadeia recursiva de:

1. **Decomposição** — divide o conceito em sub-conceitos mais simples (via LLM)
2. **Pesquisa por lentes** — cada sub-conceito é pesquisado em perspectivas fixas e nomeadas (significado, teoria, prática, ferramentas…) via SearXNG local + download de páginas
3. **Integração bottom-up** — sintetiza achados dos filhos para o pai, preservando conflitos e lacunas
4. **Síntese da raiz** — gera o resumo final com fontes citadas, perguntas abertas e learning path

O resultado é um `Run` com árvore de nós, fontes indexadas, trilha de aprendizado e recomendações — tudo em JSON tipado.

---

## Diferenciais

**Lentes nomeadas e fixas.** Em vez de busca genérica, cada sub-conceito é pesquisado por dimensões explícitas (`meaning`, `theory`, `practice`, `expert_views`…). Isso produz contexto rico e comparável entre runs, não uma lista de links.

**Budget rígido por run.** Limites configuráveis de queries, páginas, chamadas LLM, tokens, segundos e USD — com contabilidade em tempo real. Quando qualquer limite é atingido, a run para e entrega o que foi processado até ali, sem surpresas de custo.

**SearXNG local.** Busca web sem dependência de API paga e sem rastreamento. Você controla o índice, o cache e as fontes habilitadas.

**MCP nativo desde o design.** O servidor MCP não é um wrapper adicionado depois — é a interface principal. Todas as ferramentas (`abstract`, `assess_complexity`, `expand_node`, `research_concept`) são pensadas para uso em conversas com IA, com retorno JSON estruturado e suporte a progresso em tempo real.

**Múltiplos providers LLM.** Troca de provider sem alterar código — Anthropic, Ollama, OpenRouter, OpenCode, Gemini CLI — com resolução automática baseada nas chaves configuradas.

---

## Início rápido

```bat
REM 1. Preparar ambiente (Python, uv, deps, Docker, SearXNG)
preparar.bat

REM 2. Preencher credenciais
notepad .env

REM 3. Usar
uv run abstrator run "arquitetura de microsserviços"
uv run abstrator run "machine learning" --mode deep
uv run abstrator mcp          REM servidor MCP (stdio)
```

---

## Instalação manual

### Pré-requisitos

| Ferramenta | Versão mínima | Para quê |
|---|---|---|
| Python | 3.12 | runtime |
| [uv](https://docs.astral.sh/uv/) | qualquer | gerenciador de pacotes |
| Docker Desktop | qualquer | SearXNG local |
| Chave de API ou Ollama | — | LLM |

```bash
uv sync
cp .env.example .env   # editar com suas chaves
docker compose up -d
uv run abstrator doctor
```

---

## Variáveis de ambiente (`.env`)

```env
# Provider: opencode_zen | anthropic | ollama | openrouter | gemini_cli | fake
ABSTRATOR_LLM_PROVIDER=auto   # auto detecta pela chave disponível

# OpenCode
OPENCODE_API_KEY=sk-...
ABSTRATOR_LLM_MODEL=claude-sonnet-5

# Anthropic direto
ANTHROPIC_API_KEY=sk-ant-...

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:14b

# OpenRouter
OPENROUTER_API_KEY=sk-or-...

# SearXNG
SEARXNG_URL=http://localhost:8080

# Orçamento padrão (modo standard)
ABSTRATOR_BUDGET_MAX_QUERIES=60
ABSTRATOR_BUDGET_MAX_LLM_CALLS=80
ABSTRATOR_BUDGET_MAX_USD=2.0
```

### Resolução automática de provider (`auto`)

Quando `ABSTRATOR_LLM_PROVIDER=auto`, o sistema resolve na ordem:

1. `opencode_zen` — se `OPENCODE_API_KEY` estiver preenchida
2. `anthropic` — se `ANTHROPIC_API_KEY` estiver preenchida
3. `openrouter` — se `OPENROUTER_API_KEY` estiver preenchida
4. `gemini_cli` — fallback (sem chave, usa binário `gemini`)

---

## CLI

```
abstrator run <query>                     Executa pesquisa completa
abstrator run <query> --mode quick|standard|deep
abstrator run <query> --lenses meaning,practice,existing_tools
abstrator expand <run_id> <node_id>       Aprofunda nó específico
abstrator runs                            Lista execuções salvas
abstrator get <run_id>                    Mostra JSON de uma run
abstrator improve                         Meta-modo: abstrai o próprio projeto
abstrator eval <run_id>                   Avalia qualidade offline
abstrator mcp                             Inicia servidor MCP (stdio)
abstrator doctor                          Verifica saúde do ambiente
abstrator schema                          Exporta JSON Schema da saída
```

---

## Servidor MCP

### Ferramentas disponíveis

| Ferramenta | Descrição |
|---|---|
| `assess_complexity` | Avalia se vale decompor (barato, use primeiro) |
| `abstract` | Executa a cadeia completa, retorna JSON da Run |
| `research_concept` | Pesquisa um único conceito sem recursão |
| `expand_node` | Aprofunda um nó que parou cedo |
| `get_run` | Recupera uma Run salva |
| `list_runs` | Lista Runs recentes |
| `cancel_run` | Kill switch para Run em andamento |

### Configurar no Claude Desktop

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "uv",
      "args": ["run", "abstrator", "mcp"],
      "cwd": "C:/Projetos/abstrator"
    }
  }
}
```

### Configurar no Gemini CLI

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "uv",
      "args": ["--directory", "C:/Projetos/abstrator", "run", "abstrator", "mcp"]
    }
  }
}
```

### Fluxo recomendado numa conversa

```
1. assess_complexity("meu tópico")          → decide se vale abstract() ou research_concept()
2. abstract("meu tópico", mode="standard")  → Run completa com árvore e fontes
3. expand_node(run_id, node_id)             → aprofunda nó que parou em max_depth
```

---

## Modos de pesquisa

| Modo | Profundidade | Fanout | Lentes | Budget scale |
|---|---|---|---|---|
| `quick` | 2 | 3 | meaning, practice, existing_tools | 0.35× |
| `standard` | 3 | 4 | todas de integração | 1.0× |
| `deep` | 5 | 5 | todas | 2.5× |

---

## Lentes disponíveis

| Lente | O que busca |
|---|---|
| `meaning` | Definição precisa, fronteiras do conceito |
| `analogy` | Analogias com outros domínios (com onde quebram) |
| `theory` | Enquadramento teórico, estado da arte |
| `practice` | Passo a passo real, custos, decisões |
| `best_practices` | Regras de practitioners + erro típico que cada uma evita |
| `expert_views` | Posições de pesquisadores e autores reconhecidos |
| `advanced_methods` | Abordagens sofisticadas com critério de uso |
| `existing_tools` | Ferramentas, libs, serviços com URLs |

---

## Providers LLM

### `opencode_zen` (padrão)
Gateway OpenAI-compatible do OpenCode. Requer `OPENCODE_API_KEY`.
Suporta modelos free (`space-bunny-free` etc.) e modelos premium.

### `anthropic`
API direta da Anthropic. Requer `uv add anthropic` + `ANTHROPIC_API_KEY`.

**Cache de prompt nativo:** o system prompt (incluindo o JSON Schema de cada chamada) é marcado como `cache_control: ephemeral`. Em runs longas — onde o mesmo schema se repete dezenas de vezes — isso reduz custo de entrada em até 90% nas chamadas cacheadas.

```bash
uv add anthropic
# .env: ANTHROPIC_API_KEY=sk-ant-...
# .env: ABSTRATOR_LLM_PROVIDER=anthropic
# .env: ABSTRATOR_LLM_MODEL=claude-sonnet-5
```

### `ollama`
Modelos locais via Ollama. **Zero custo por token.** Ideal para exploração, testes e uso intensivo sem preocupação com budget de USD.

```bash
# Instalar Ollama: https://ollama.com
ollama pull qwen2.5:14b
# .env: ABSTRATOR_LLM_PROVIDER=ollama
# .env: OLLAMA_MODEL=qwen2.5:14b
```

Modelos recomendados: `qwen2.5:14b` (equilibrado), `mistral-nemo` (contexto longo), `llama3.3` (raciocínio).

### `openrouter`
Acesso a centenas de modelos (Llama, DeepSeek, Mistral, Qwen, Command R…) com uma única chave. Requer `OPENROUTER_API_KEY`.

Útil para alternar entre modelos especializados sem gerenciar múltiplas contas — ex.: DeepSeek para raciocínio técnico, Qwen para textos longos, modelos open source para uso intensivo.

```bash
# .env: ABSTRATOR_LLM_PROVIDER=openrouter
# .env: OPENROUTER_API_KEY=sk-or-...
# .env: ABSTRATOR_LLM_MODEL=deepseek/deepseek-r1
```

### `gemini_cli`
Delega ao binário `gemini` instalado localmente. Sem chave de API. Detecta shims `.cmd`/`.bat` do npm no Windows automaticamente.

### `fake`
Provider determinístico para testes — sem rede, sem custo, sem configuração.

---

## Ideias de extensão MCP

### Base vetorial local
Antes de pesquisar na web, consultar uma base vetorial (ChromaDB, Qdrant) com documentos já processados. Ferramenta MCP: `search_local_knowledge(query, top_k)` — evita buscas redundantes em domínios recorrentes.

### Export para Anki / Obsidian
Transformar a `learning_path` de uma Run em flashcards Anki (`.apkg`) ou notas Obsidian (`.md`). Ferramenta MCP: `generate_flashcards(run_id, format)`.

### Comparação entre Runs
Detectar contradições ou evoluções entre duas pesquisas sobre o mesmo tema. Ferramenta MCP: `compare_runs(run_id_a, run_id_b)` → diff estruturado de claims e conflitos.

### Notificação por webhook
Para runs longas (`deep`), notificar ao concluir. Ferramenta MCP: `abstract_async(query, webhook_url)` → retorna `run_id` imediatamente, POST ao webhook quando terminar.

### Export para Notion / Obsidian
Publicar o `report.md` gerado diretamente em um workspace. Ferramenta MCP: `export_run(run_id, destination)`.

---

## Arquitetura

```
CLI (typer)  /  MCP (FastMCP)
        └── Orchestrator
                ├── assess_complexity  (LLM)
                ├── decompose          (LLM → SubConcept[])
                ├── ResearchEngine
                │     ├── SearxngClient  (busca web local)
                │     ├── Fetcher        (download + trafilatura)
                │     └── LLMRunner      (análise por lente)
                ├── integrate          (LLM bottom-up)
                └── synthesize_root    (LLM síntese final)

Store : runs/<run_id>/result.json + report.md + audit.jsonl
Cache : data/abstrator.sqlite3  (search, page, concept, llm — TTL configurável)
```

---

## Estrutura de arquivos

```
src/abstrator/
├── cli.py              Comandos CLI (typer)
├── config.py           Settings (pydantic-settings) + ModePreset + PRICING
├── mcp_server.py       Servidor MCP (FastMCP)
├── models.py           Modelos Pydantic (Run, Node, Analysis, Budget…)
├── store.py            Persistência (JSON + Markdown por run)
├── audit.py            Log de auditoria (JSONL append-only)
├── doctor.py           Verificação de saúde do ambiente
├── evaluation.py       Rubrica de qualidade offline
├── engine/
│   ├── orchestrator.py Loop recursivo principal
│   ├── budget.py       Limites de queries/pages/tokens/USD/tempo
│   ├── complexity.py   Heurística + LLM: simples vs. complexo
│   ├── decompose.py    LLM → sub-conceitos (com dedup por similaridade)
│   ├── research.py     Pesquisa por lentes (search + fetch + LLM)
│   ├── synthesize.py   Integração bottom-up e síntese da raiz
│   ├── expand.py       Aprofundar nó parado
│   ├── improve.py      Meta-modo: abstrator analisa a si mesmo
│   └── llm_runner.py   Wrapper de cache + budget + auditoria
├── llm/
│   ├── base.py             Protocolo LLMProvider + helpers de JSON estruturado
│   ├── opencode_zen.py     HTTP OpenAI-compatible (OpenCode)
│   ├── anthropic_direct.py API Anthropic com cache de prompt nativo
│   ├── ollama.py           Modelos locais via Ollama
│   ├── openrouter.py       Centenas de modelos via OpenRouter
│   ├── gemini_cli.py       Subprocess `gemini` (sem chave de API)
│   └── fake.py             Provider determinístico para testes
├── search/
│   ├── searxng.py      Cliente SearXNG (busca local, sem rastreamento)
│   ├── fetch.py        Downloader (robots.txt, rate limit, trafilatura)
│   ├── cache.py        SQLite com TTL (4 tabelas)
│   ├── credibility.py  Heurística URL → tipo de fonte + score
│   └── lenses.py       Templates de query por lente
└── prompts/            Templates .md com {placeholders}
```

---

## Testes

```bash
uv run pytest              # todos os testes
uv run pytest -x           # para no primeiro erro
uv run pytest tests/test_orchestrator.py  # suite específica
```

---

## Budget e custos

Limites rígidos configuráveis — quando qualquer um é atingido, a run para e entrega o resultado parcial:

| Variável | Padrão | O que limita |
|---|---|---|
| `ABSTRATOR_BUDGET_MAX_QUERIES` | 60 | buscas web |
| `ABSTRATOR_BUDGET_MAX_PAGES` | 120 | páginas baixadas |
| `ABSTRATOR_BUDGET_MAX_LLM_CALLS` | 80 | chamadas LLM |
| `ABSTRATOR_BUDGET_MAX_TOKENS` | 400 000 | tokens totais |
| `ABSTRATOR_BUDGET_MAX_SECONDS` | 900 | tempo total |
| `ABSTRATOR_BUDGET_MAX_USD` | 2.0 | custo estimado em USD |

Modos escalam o budget proporcionalmente: `quick` = 0.35×, `standard` = 1×, `deep` = 2.5×.

---

## Contribuindo

1. Fork + branch a partir de `main`
2. `uv sync` para instalar deps de dev
3. Escreva testes antes de implementar (TDD London School)
4. `uv run pytest` — todos os testes devem passar
5. Abra PR com descrição do problema e solução
