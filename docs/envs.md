# Variáveis de Ambiente

Os arquivos `.env` **não são commitados** (`.gitignore` cobre `.env` e `.env.*`).
Este documento serve de referência para recriar qualquer configuração do zero.

---

## Arquivos em uso

| Arquivo | Propósito | Commitado? |
|---------|-----------|------------|
| `.env` | Configuração ativa carregada pelo abstrator | Não |
| `.env.example` | Template com valores padrão | Sim |

---

## `.env` — configuração atual (OpenRouter, modelos gratuitos)

Crie o arquivo `.env` na raiz do projeto com o conteúdo abaixo,
substituindo os valores marcados com `<...>`.

```env
# --- Busca (SearXNG) ---
# local (porta 8888 — Steam ocupa 8080):
SEARXNG_URL=http://localhost:8888
# público (instância que aceita a API JSON):
# SEARXNG_URL=https://searx.tiekoetter.com

ABSTRATOR_USER_AGENT=Abstrator/0.1 (pesquisa; contato: local)
ABSTRATOR_CACHE_TTL_HOURS=24
ABSTRATOR_CONCEPT_CACHE_TTL_HOURS=72
ABSTRATOR_SEARCH_PER_DOMAIN=1
ABSTRATOR_FETCH_DELAY_SECONDS=1.0
ABSTRATOR_FETCH_TIMEOUT=15
ABSTRATOR_MAX_PAGE_BYTES=200000
ABSTRATOR_MAX_PAGES_PER_RUN=80
ABSTRATOR_HTTP_TIMEOUT=30
ABSTRATOR_MAX_SOURCES_PER_LENS=6
ABSTRATOR_MIN_CREDIBILITY=0.2

# --- LLM (OpenRouter — modelos gratuitos) ---
ABSTRATOR_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<chave em https://openrouter.ai/keys>
ABSTRATOR_LLM_MODEL=nvidia/nemotron-3.5-lightning:free
ABSTRATOR_LLM_MAX_OUTPUT_TOKENS=4096
ABSTRATOR_LLM_TIMEOUT=120
ABSTRATOR_LLM_MAX_RETRIES=2

# --- Budget ---
ABSTRATOR_BUDGET_MAX_QUERIES=200
ABSTRATOR_BUDGET_MAX_PAGES=250
ABSTRATOR_BUDGET_MAX_LLM_CALLS=200
ABSTRATOR_BUDGET_MAX_TOKENS=800000
ABSTRATOR_BUDGET_MAX_SECONDS=1200
ABSTRATOR_BUDGET_MAX_USD=1.00
```

### Modelos gratuitos disponíveis no OpenRouter (novembro 2026)

Troque `ABSTRATOR_LLM_MODEL` por qualquer um abaixo se o atual parar de funcionar:

| Modelo | Observação |
|--------|-----------|
| `nvidia/nemotron-3.5-lightning:free` | **Atual** — reasoning model, retorna JSON válido para prompts complexos |
| `recursive/flint-v1.0:free` | Alternativa leve, JSON funcional |
| `google/gemma-4-26b-a4b-it:free` | Bom, mas rate-limit frequente no pool compartilhado |
| `google/gemma-4-31b-it:free` | Idem Gemma 26b |
| `cohere/north-mini-code:free` | Code model — falha em prompts de análise complexos |

> Para listar os modelos gratuitos disponíveis na sua conta:
> ```bash
> curl https://openrouter.ai/api/v1/models \
>   -H "Authorization: Bearer $OPENROUTER_API_KEY" \
>   | python -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data'] if m['id'].endswith(':free')]"
> ```

---

## Histórico de provedores testados

| Provedor | Status | Motivo |
|----------|--------|--------|
| OpenRouter `meta-llama/llama-3.3-70b-instruct:free` | Descontinuado | Removido do tier gratuito (404) |
| Google AI Studio via OpenRouter | Instável | Rate-limit constante no pool compartilhado |
| Anthropic API direta | Requer créditos | Conta API separada da assinatura Claude.ai |
| Gemini CLI | Deprecado | Modelo `gemini-2.0-flash` não encontrado |
| OpenRouter `nvidia/nemotron-3.5-lightning:free` | **Ativo** | Funciona, reasoning model, precisa de 4096 tokens |
