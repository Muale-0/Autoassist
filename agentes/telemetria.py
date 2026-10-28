"""DATA AGENT (Telemetria): analisa os dados OBD-II do veiculo.

Usa a ferramenta `analisar_telemetria` (calculo em Python) e, se o LLM estiver
disponivel, pede a ele apenas a INTERPRETACAO dos numeros ja calculados.
"""
from __future__ import annotations

import json

from ferramentas.telemetria import analisar_telemetria

from .base import Agente

SISTEMA = """Voce e o Data Agent de um assistente automotivo. Recebe estatisticas JA CALCULADAS
de telemetria OBD-II. Interprete em ate 3 frases o comportamento do veiculo. Nao recalcule numeros
e nao invente valores que nao estao nos dados."""


class AgenteTelemetria(Agente):
    nome = "DATA AGENT"
    responsabilidade = "Analisar series temporais OBD-II (temperatura, tensao, pressao de oleo, RPM)."

    def executar(self, ctx):
        analise = self.usar_ferramenta(ctx, "analisar_telemetria", analisar_telemetria, df=ctx.telemetria)
        if "erro" in analise:
            ctx.avisos.append("Nao foi possivel analisar a telemetria.")
            return None
        if self.llm.disponivel:
            try:
                analise["interpretacao"] = self.llm.gerar(
                    "Estatisticas e anomalias:\n" + json.dumps(analise, ensure_ascii=False), SISTEMA)
            except Exception as e:
                self.log.log("ERRO", f"{self.nome}: interpretacao via LLM falhou ({e}); usando resumo por regras")
        if "interpretacao" not in analise:
            if analise["anomalias"]:
                analise["interpretacao"] = "; ".join(a["mensagem"] for a in analise["anomalias"]) + "."
            else:
                analise["interpretacao"] = "Todas as grandezas medidas ficaram dentro das faixas normais."
        n = len(analise["anomalias"])
        self.log.log(self.nome, f"{analise['leituras']} leituras em {analise['duracao_s']:.0f}s | {n} anomalia(s): "
                     + (", ".join(f"{a['metrica']}({a['nivel']})" for a in analise["anomalias"]) or "nenhuma"), analise)
        return analise
