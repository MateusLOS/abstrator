from __future__ import annotations

from ..models import Lens

LENS_GUIDANCE: dict[Lens, str] = {
    Lens.MEANING: (
        "Defina o conceito com precisao: o que e, o que NAO e, e o vocabulario minimo "
        "para falar dele. Prefira definicoes que demarcam fronteiras."
    ),
    Lens.ANALOGY: (
        "Apresente 2 a 3 analogias com dominios diferentes, e diga onde cada analogia "
        "quebra (analogia e mapa, nao territorio)."
    ),
    Lens.THEORY: (
        "Apresente o enquadramento teorico, os modelos/metricas relevantes e o estado da "
        "arte. Distinga consenso Acceptance de discussao aberta."
    ),
    Lens.PRACTICE: (
        "Descreva o passo a passo real, com as decisoes que aparecem na pratica e os "
        "custos (tempo, dinheiro, complexidade) de cada opcao."
    ),
    Lens.BEST_PRACTICES: (
        "Liste as regras que practitioners experientes seguem de forma consistente. "
        "Para cada regra: (1) o que fazer concretamente, (2) por que isso importa — "
        "qual problema especifico evita, (3) o erro tipico de quem nao segue essa regra. "
        "Evite generalizacoes como 'e importante testar' — seja especifico: o que testar, quando, como."
    ),
    Lens.EXPERT_VIEWS: (
        "Registre posicoes de pesquisadores, autores e profissionais reconhecidos na area, "
        "atribuindo cada claim a nome e fonte especifica. Priorize: visoes contra-intuitivas, "
        "consensos que surpreendem iniciantes, e divergencias reais entre especialistas. "
        "Separe o que e consenso do que e posicao minoritaria ou controversa."
    ),
    Lens.ADVANCED_METHODS: (
        "Liste abordagens que profissionais seniorespuseram em pratica — nao as mais famosas, "
        "mas as que realmente funcionam em producao. Para cada uma: quando usar (criterio concreto), "
        "quando NAO usar, e o custo real de adotar. Inclua metodos que iniciantes tipicamente ignoram."
    ),
    Lens.EXISTING_TOOLS: (
        "Liste ferramentas, libs, servicos e projetos existentes, marcando quais sao "
        "gratuitas/open source e dando a URL quando as fontes trouxerem."
    ),
}

LENS_SYSTEM = (
    "Voce e um pesquisador rigoroso. So afirma o que as fontes mostram, sempre citando "
    "o id da fonte. Prefere preciso a completo: e melhor dizer 'as fontes nao cobrem X' "
    "do que preencher lacuna com suposicao."
)
