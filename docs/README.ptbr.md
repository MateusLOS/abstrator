# Abstrator

<!-- mcp-name: io.github.mateuslos/abstrator -->

> Pesquisa por abstração recursiva — transforma qualquer tema complexo em um guia profissional direto, pesquisando na web por múltiplas lentes especializadas e sintetizando o resultado.

## O que é

O Abstrator é um **servidor MCP + CLI** que recebe uma pergunta ou tópico e executa uma cadeia recursiva de:

1. **Decomposição** — divide o conceito em sub-conceitos mais simples (via LLM)
2. **Pesquisa por lentes** — cada sub-conceito é pesquisado em perspectivas fixas e nomeadas (`meaning`, `theory`, `practice`, `best_practices`, `expert_views`, `advanced_methods`, `existing_tools`) via SearXNG local + download de páginas
3. **Integração bottom-up** — sintetiza achados dos filhos para o pai, preservando conflitos e lacunas
4. **Síntese da raiz** — gera o resultado final como guia profissional com boas práticas, visão de especialistas, metodologias e ferramentas

O resultado da ferramenta `ask` é markdown limpo, pronto para usar diretamente em qualquer conversa com IA.

---

## Como usar no Claude Code

### Slash command (principal)

Em qualquer conversa do Claude Code com o projeto aberto:

```
/abstrator design de site
/abstrator como negociar salário
/abstrator event sourcing para backend
/abstrator machine learning, foco em iniciante
```

O comando pesquisa o tema e entrega um guia de nível profissional com:
- Síntese clara do tema
- Boas práticas (o que practitioners seguem e por quê)
- O que os especialistas dizem (com atribuição)
- Metodologias e arquiteturas (ordenadas por fit)
- Ferramentas e recursos disponíveis
- Próximos passos concretos

---

## Início rápido

```bash
# 1. Instalar
pip install abstrator        # ou: uv tool install abstrator

# 2. Iniciar mecanismo de busca local (requer Docker)
docker run -d -p 8888:8080 searxng/searxng

# 3. Configurar o provider LLM (wizard interativo)
abstrator setup

# 4. Registrar o MCP no Claude Code
claude mcp add abstrator -- abstrator mcp
```

> **Sem chave de API?** Use `claude_code_cli` (requer Claude Code instalado) ou `ollama` (100% local) no wizard de configuração.

---

## Instalação

### Pré-requisitos

| Ferramenta | Versão mínima | Para quê |
|---|---|---|
| Python | 3.11+ | runtime |
| Docker | qualquer | SearXNG local (busca web) |
| LLM | — | qualquer: Claude Code, Anthropic API, OpenRouter, Gemini CLI, Ollama |

```bash
# Via PyPI
pip install abstrator

# Ou a partir do código-fonte
git clone https://github.com/MateusLOS/abstrator
cd abstrator
uv sync
docker compose up -d    # inicia SearXNG na porta 8888
abstrator setup         # wizard interativo de provider
abstrator doctor        # verifica se tudo funciona
```

---

## Variáveis de ambiente (`.env`)

Execute `abstrator setup` para configurar interativamente, ou edite manualmente:

```env
# Provider (execute 'abstrator setup' para configurar interativamente)
ABSTRATOR_LLM_PROVIDER=claude_code_cli   # sem chave — usa OAuth do Claude Code
ABSTRATOR_LLM_MODEL=claude-haiku-4-5-20251001

# Anthropic direto (prompt caching nativo — até 90% de economia)
# ABSTRATOR_LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter (50 req/dia grátis, centenas de modelos)
# ABSTRATOR_LLM_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-...
# ABSTRATOR_LLM_MODEL=google/gemma-3-27b-it:free

# Ollama (local, custo zero)
# ABSTRATOR_LLM_PROVIDER=ollama
# ABSTRATOR_LLM_MODEL=qwen2.5:14b

# SearXNG local (porta 8888)
SEARXNG_URL=http://localhost:8888
```

Trocar provider a qualquer momento:

```bash
abstrator config provider claude_code_cli
abstrator config provider anthropic
abstrator config provider ollama
```

---

## Ferramentas MCP

| Ferramenta | Saída | Quando usar |
|---|---|---|
| `ask` | Markdown profissional | **Principal.** Pesquisa e entrega guia pronto para conversa |
| `assess_complexity` | JSON | Avalia se vale decompor (barato, use antes do abstract) |
| `abstract` | JSON completo da Run | Quando precisa da árvore estruturada, fontes indexadas e learning path |
| `research_concept` | JSON de um nó | Pesquisa um conceito específico sem recursão |
| `expand_node` | JSON da Run atualizada | Aprofunda um nó que parou cedo |
| `get_run` | JSON | Recupera uma Run salva |
| `list_runs` | Lista | Lista Runs recentes |
| `cancel_run` | Status | Kill switch para Run em andamento |

### Registrar no Claude Code

```bash
claude mcp add abstrator -- abstrator mcp
```

Se `abstrator` não estiver no PATH (comum em installs com venv), use o caminho completo:

```bash
# macOS / Linux
claude mcp add abstrator -- ~/.local/bin/abstrator mcp

# Windows (PowerShell)
claude mcp add abstrator -- "$env:APPDATA\Python\Scripts\abstrator.exe" mcp
```

### Claude Desktop

Adicione ao `claude_desktop_config.json` (`%APPDATA%\Claude\` no Windows, `~/Library/Application Support/Claude/` no macOS):

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "abstrator",
      "args": ["mcp"]
    }
  }
}
```

### Gemini CLI

Adicione ao `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "abstrator",
      "args": ["mcp"]
    }
  }
}
```

### OpenCode

Crie `opencode.json` na pasta do projeto:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "abstrator": {
      "type": "local",
      "command": ["abstrator", "mcp"],
      "enabled": true
    }
  }
}
```

### Fluxo recomendado numa conversa

**Uso comum — slash command:**
```
/abstrator event sourcing para backend
```

**Uso avançado — ferramentas diretas:**
```
1. assess_complexity("meu tópico")          → decide se vale abstract() ou research_concept()
2. abstract("meu tópico", mode="standard")  → Run completa com árvore e fontes em JSON
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

| Provider | Chave necessária | Notas |
|---|---|---|
| `claude_code_cli` | nenhuma | **Recomendado.** Usa OAuth do Claude Code (assinatura Pro) — sem chave extra |
| `anthropic` | `ANTHROPIC_API_KEY` | API direta com cache de prompt nativo — até 90% de economia em runs longas |
| `openrouter` | `OPENROUTER_API_KEY` | Centenas de modelos, uma só chave — 50 req/dia grátis |
| `gemini_cli` | nenhuma | Delega ao binário `gemini` (requer Gemini CLI instalado) |
| `opencode_zen` | `OPENCODE_API_KEY` | Gateway OpenAI-compatible |
| `ollama` | nenhuma | Modelos locais, zero custo por token |
| `fake` | nenhuma | Determinístico, sem rede — só para testes |

Configure com:
```bash
abstrator setup                           # wizard interativo
abstrator config provider <nome>          # troca rápida
abstrator config show                     # status atual
```

---

## Budget e limites

Limites rígidos — quando qualquer um é atingido, a run para e retorna resultado parcial:

| Variável | Padrão | O que limita |
|---|---|---|
| `ABSTRATOR_BUDGET_MAX_QUERIES` | 60 | buscas web |
| `ABSTRATOR_BUDGET_MAX_PAGES` | 120 | páginas baixadas |
| `ABSTRATOR_BUDGET_MAX_LLM_CALLS` | 80 | chamadas LLM |
| `ABSTRATOR_BUDGET_MAX_TOKENS` | 400 000 | tokens totais |
| `ABSTRATOR_BUDGET_MAX_SECONDS` | 900 | tempo total |
| `ABSTRATOR_BUDGET_MAX_USD` | 2.0 | custo estimado em USD |

Modos escalam o budget: `quick` = 0.35×, `standard` = 1×, `deep` = 2.5×.

---

## CLI

```
abstrator run <query>                      Executa pesquisa completa
abstrator run <query> --mode quick|standard|deep
abstrator run <query> --lenses meaning,practice,existing_tools
abstrator expand <run_id> <node_id>        Aprofunda nó específico
abstrator runs                             Lista execuções salvas
abstrator get <run_id>                     Mostra JSON de uma run
abstrator improve                          Meta-modo: abstrai o próprio projeto
abstrator eval <run_id>                    Avalia qualidade offline
abstrator mcp                              Inicia servidor MCP (stdio)
abstrator doctor                           Verifica saúde do ambiente
abstrator schema                           Exporta JSON Schema da saída
abstrator setup                            Wizard interativo de configuração
abstrator config provider <nome>           Troca de provider sem wizard
abstrator config show                      Mostra provider atual
```

---

## Testes

```bash
uv run pytest              # todos os testes
uv run pytest -x           # para no primeiro erro
uv run pytest tests/test_orchestrator.py
```

---

## Arquitetura

```
CLI (typer)  /  MCP (MCPServer)
        └── Orchestrator
                ├── assess_complexity  (LLM)
                ├── decompose          (LLM → SubConcept[])
                ├── ResearchEngine
                │     ├── SearxngClient  (busca web local — porta 8888)
                │     ├── Fetcher        (download + trafilatura)
                │     └── LLMRunner      (análise por lente)
                ├── integrate          (LLM bottom-up)
                └── synthesize_root    (LLM síntese final)

Store : runs/<run_id>/result.json + report.md + audit.jsonl
Cache : data/abstrator.sqlite3  (search, page, concept, llm — TTL configurável)
```

---

## Contribuindo

1. Fork + branch a partir de `main`
2. `uv sync` para instalar deps de dev
3. Escreva testes antes de implementar (TDD London School)
4. `uv run pytest` — todos os testes devem passar
5. Abra PR com descrição do problema e solução

---

## Documentação

- [README in English](../README.md)
