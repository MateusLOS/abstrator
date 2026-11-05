Pesquise o tema a seguir usando a ferramenta `ask` do MCP abstrator.

Argumentos recebidos: $ARGUMENTS

Instruções:
1. Detecte o modo nos argumentos:
   - Se termina com "--standard" ou "mode=standard": mode="standard", remova do tema
   - Se termina com "--deep" ou "mode=deep": mode="deep", remova do tema
   - Caso contrário: mode="quick"
2. O restante dos argumentos é o tema (query)
3. Chame `ask` com:
   - query=<tema detectado>
   - mode=<modo detectado>
   - goal="guia de nivel senior: o que profissionais experientes fazem de diferente, quais ferramentas e arquiteturas escolhem e por que, quais armadilhas reais existem, o que distingue um resultado mediano de um resultado profissional"
4. Retorne apenas o resultado da ferramenta, sem introdução, sem comentário, sem rodapé seu
5. Não resuma nem reformule o resultado — entregue exatamente o que a ferramenta retornou

Exemplos:
- `/abstrator bot investidor` → query="bot investidor", mode="quick"
- `/abstrator bot investidor --standard` → query="bot investidor", mode="standard"
- `/abstrator design de site --deep` → query="design de site", mode="deep"
