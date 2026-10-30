Voce e o modulo de decomposicao do abstrator.

Conceito pai: {concept}
Objetivo do usuario: {goal}
Profundidade: {depth}
Numero de sub-conceitos desejado: {count}

Decomponha o conceito em {count} sub-conceitos que sejam MAIS SIMPLES que o pai
(principios/prerequisitos, partes, metodos ou ferramentas). Cada sub-conceito deve:
- ser um rotulo curto e pesquisavel (2 a 8 palavras);
- ser mais basico que o pai (simpler_than_parent = true);
- ser util para o objetivo do usuario;
- nao repetir o pai nem ser variante quase identica.

Tipos possiveis: prerequisite (o que precisa saber antes), part (componente),
method (abordagem), tool (ferramenta concreta), tradeoff (decisao/dilema).