"""REVIEWER AGENT: verifica consistencia entre as fontes e consolida UMA resposta final.

Tres camadas:
1. Ferramenta deterministica de urgencia (trava de seguranca).
2. Checagens de consistencia entre modalidades (imagem x telemetria x texto).
3. Redacao da resposta final (LLM ou modelo de texto), sempre com a urgencia
   calculada por regra no topo - o LLM nao pode "rebaixar" um alerta critico.
"""
from __future__ import annotations

import json

from ferramentas.urgencia import classificar_urgencia

from .base import Agente

SISTEMA = """Voce e o Reviewer Agent de um assistente automotivo. Recebe os resultados de varios
agentes e deve produzir UMA resposta final, clara e integrada, para um motorista leigo.
REGRAS:
- O nivel de urgencia ja foi decidido por regra e NAO pode ser contrariado.
- Use somente informacoes presentes nos resultados; nao invente leituras.
- Se houver divergencias entre fontes, mencione-as.
- Formato (markdown, sem titulo principal):
### O que foi identificado
(1 linha por fonte: imagem, telemetria, texto/audio)
### Causa mais provavel
(1 a 3 hipoteses, com a evidencia de cada)
### Proximos passos
(lista numerada, do mais simples/seguro ao mais complexo)
Maximo de 220 palavras."""


class AgenteRevisor(Agente):
    nome = "REVIEW"
    responsabilidade = "Checar consistencia, aplicar trava de seguranca e consolidar a resposta final."

    def _consistencia(self, ctx) -> list[str]:
        obs = []
        visao = ctx.resultados.get("visao") or {}
        tele = ctx.resultados.get("telemetria") or {}
        luzes = {l["chave"] for l in visao.get("luzes_acesas", [])}
        anom = {a["metrica"]: a for a in tele.get("anomalias", [])}
        cols = set(tele.get("colunas", []))
        pares = [("temperatura_motor", "temp_motor_c"), ("bateria", "tensao_bateria_v"), ("pressao_oleo", "pressao_oleo_bar"),
                 ("injecao_check_engine", "rpm")]
        for luz, metrica in pares:
            if luz in luzes and metrica in anom:
                obs.append(f"CONFIRMADO por duas fontes: luz '{luz}' na imagem + anomalia em '{metrica}' na telemetria.")
            elif luz in luzes and metrica in cols and metrica not in anom and luz != "injecao_check_engine":
                obs.append(f"DIVERGENCIA: a imagem mostra a luz '{luz}', mas a telemetria de '{metrica}' esta normal "
                           f"(possivel falha de sensor ou dados de outro momento).")
            elif metrica in anom and visao and luz not in luzes and anom[metrica]["nivel"] == "critico":
                obs.append(f"ATENCAO: telemetria critica em '{metrica}', mas a luz '{luz}' nao foi vista na imagem.")
        if "injecao_check_engine" in luzes and not ctx.intencao.get("codigos_dtc"):
            obs.append("FALTA INFORMACAO: luz de injecao acesa sem codigo DTC informado; recomenda-se leitura com scanner OBD-II.")
        return obs

    def executar(self, ctx):
        mec = ctx.resultados.get("mecanico") or {}
        tele = ctx.resultados.get("telemetria") or {}
        urg = self.usar_ferramenta(ctx, "classificar_urgencia", classificar_urgencia,
                                   luzes=mec.get("luzes", []), codigos_dtc=mec.get("codigos", []),
                                   anomalias=tele.get("anomalias", []), luz_piscando=ctx.intencao.get("luz_piscando", False),
                                   fontes_analisadas=sum([bool((ctx.resultados.get("visao") or {}).get("e_painel_veicular")),
                                                          bool(tele), bool(mec.get("codigos"))]))
        ctx.urgencia = urg
        consist = self._consistencia(ctx)
        for c in consist:
            self.log.log(self.nome, c)
        self.log.log(self.nome, f"Urgencia definida por regra: {urg['rotulo']} (nivel {urg['nivel']})")

        corpo = None
        if self.llm.disponivel:
            try:
                dados = {"pergunta": ctx.pergunta_efetiva(), "urgencia_fixa": urg, "consistencia": consist,
                         "visao": ctx.resultados.get("visao"), "audio": ctx.resultados.get("audio"),
                         "telemetria": {k: tele.get(k) for k in ("anomalias", "interpretacao", "estatisticas")} if tele else None,
                         "analise_especialista": mec.get("analise")}
                corpo = self.llm.gerar(json.dumps(dados, ensure_ascii=False, default=str), SISTEMA, temperatura=0.3)
            except Exception as e:
                self.log.log("ERRO", f"{self.nome}: consolidacao via LLM falhou ({e}); usando modelo de texto")
        if not corpo:
            corpo = self._corpo_por_regras(ctx, mec, tele, consist)

        topo = f"## Urgencia: {urg['rotulo']}\n**{urg['recomendacao']}**\n\n"
        limites = ctx.avisos + [c for c in consist if c.startswith(("DIVERGENCIA", "FALTA"))]
        rodape = "\n\n### Limitacoes desta analise\n" + "".join(f"- {a}\n" for a in dict.fromkeys(limites))
        rodape += ("- Diagnostico preliminar gerado por IA com base de conhecimento simplificada; "
                   "nao substitui a avaliacao de um mecanico.")
        return topo + corpo + rodape

    def _corpo_por_regras(self, ctx, mec, tele, consist) -> str:
        visao = ctx.resultados.get("visao")
        audio = ctx.resultados.get("audio")
        fontes = []
        if visao:
            luzes = ", ".join(l.get("descricao", l["chave"]) for l in visao.get("luzes_acesas", [])) or "nenhuma luz catalogada"
            fontes.append(f"- **Imagem:** {luzes}")
        if tele:
            fontes.append(f"- **Telemetria:** {tele.get('interpretacao')}")
        if ctx.texto:
            fontes.append(f"- **Texto:** \"{ctx.texto.strip()[:160]}\"")
        if audio:
            fontes.append(f"- **Audio:** {audio.get('transcricao') or audio.get('ruidos_descritos')}")
        fontes += [f"- {c}" for c in consist if c.startswith(("CONFIRMADO", "ATENCAO"))]
        return "### O que foi identificado\n" + "\n".join(fontes) + "\n\n" + (mec.get("analise") or "")
