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
        "Liste regras que practitioners seguem de forma consistente, com o porquao de "
        "cada uma e o erro tipico que ela evita."
    ),
    Lens.EXPERT_VIEWS: (
        "Registre o que/researchers, autores e especialistas reconhecidos dizem, "
        "atribuindo cada claim a quem e a qual fonte. Separe consenso de posicao "
        "minoritaria."
    ),
    Lens.ADVANCED_METHODS: (
        "Liste abordagens mais sofisticadas que a media busca, com o momento certo de "
        "usar cada uma e o custo/fit para o objetivo do usuario."
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
