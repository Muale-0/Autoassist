"""FERRAMENTA: classificacao deterministica de urgencia.

Decisao de seguranca ("posso continuar rodando?") NAO fica a cargo do LLM:
e calculada por regra a partir das evidencias. O Revisor usa este resultado
como trava (guardrail) sobre o texto gerado.
"""
from __future__ import annotations

from .base_conhecimento import consultar_codigo_dtc, consultar_luz_painel

NIVEIS = {
    0: ("SEM ALERTA", "Nenhum indicio de falha nas informacoes recebidas."),
    1: ("BAIXA", "Pode rodar normalmente; agende uma verificacao."),
    2: ("ATENCAO", "Pode rodar com cautela ate uma oficina; evite viagens longas."),
    3: ("CRITICA", "PARE o veiculo em local seguro e desligue o motor. Nao continue rodando."),
}


def classificar_urgencia(luzes: list[str], codigos_dtc: list[str], anomalias: list[dict],
                         luz_piscando: bool = False, fontes_analisadas: int = 1) -> dict:
    """fontes_analisadas = quantas fontes de evidencia objetiva (imagem, telemetria, codigos) foram
    realmente analisadas. Sem nenhuma, a ausencia de alerta e INCONCLUSIVA, e nao 'sem problema'."""
    motivos, nivel = [], 0
    for luz in luzes or []:
        info = consultar_luz_painel(luz)
        if info.get("encontrado"):
            sev = info["severidade"]
            if info["chave"] == "injecao_check_engine" and luz_piscando:
                sev = 3
                motivos.append("luz de injecao PISCANDO (falha de ignicao grave, risco ao catalisador)")
            motivos.append(f"luz '{info['chave']}' (severidade {sev})")
            nivel = max(nivel, sev)
    for cod in codigos_dtc or []:
        info = consultar_codigo_dtc(cod)
        if info.get("encontrado"):
            motivos.append(f"codigo {cod} (severidade {info['severidade']})")
            nivel = max(nivel, info["severidade"])
    for a in anomalias or []:
        sev = 3 if a.get("nivel") == "critico" else 2
        motivos.append(f"telemetria: {a['metrica']} {a['nivel']}")
        nivel = max(nivel, sev)
    rotulo, recomendacao = NIVEIS[nivel]
    if nivel == 0 and fontes_analisadas == 0:
        rotulo = "INCONCLUSIVO"
        recomendacao = ("Nao ha evidencias objetivas suficientes (foto do painel, telemetria ou codigo de falha). "
                        "Se o sintoma envolver superaquecimento, fumaca, freio ou pressao de oleo, pare com seguranca.")
    return {"nivel": nivel, "rotulo": rotulo, "recomendacao": recomendacao,
            "pode_rodar": nivel < 3, "motivos": motivos}
