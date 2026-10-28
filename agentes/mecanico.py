"""SPECIALIST AGENT (Mecanico): cruza as evidencias e levanta hipoteses de causa.

E o agente que DECIDE quais consultas fazer na base de conhecimento (function
calling): o modelo escolhe a ferramenta, o sistema executa, o modelo observa o
resultado e continua o raciocinio.
"""
from __future__ import annotations

import json

from ferramentas.base_conhecimento import consultar_codigo_dtc, consultar_luz_painel, extrair_codigos_dtc

from .base import Agente

SISTEMA = """Voce e o Specialist Agent (mecanico automotivo) de um sistema multiagente.
Voce recebe evidencias de outros agentes (visao, audio, telemetria) e do texto do usuario.
REGRAS:
- Antes de afirmar o significado de qualquer luz ou codigo OBD-II, CONSULTE a ferramenta correspondente.
- Cruze as evidencias: diga quando duas fontes confirmam a mesma coisa e quando divergem.
- Liste no maximo 3 hipoteses de causa, da mais para a menos provavel, citando a evidencia de cada uma.
- Indique de 2 a 4 verificacoes praticas, em ordem (da mais simples/segura para a mais complexa).
- Nao invente dados. Se faltar informacao, diga qual informacao ajudaria.
Responda em portugues, em topicos curtos."""

DECLARACOES = [
    {"name": "consultar_luz_painel",
     "description": "Consulta na base local o significado, severidade e acao recomendada de uma luz do painel.",
     "parameters": {"type": "object", "properties": {"luz": {"type": "string", "description": "chave da luz, ex.: temperatura_motor"}},
                    "required": ["luz"]}},
    {"name": "consultar_codigo_dtc",
     "description": "Consulta na base local a descricao, causas comuns e verificacao de um codigo de falha OBD-II.",
     "parameters": {"type": "object", "properties": {"codigo": {"type": "string", "description": "ex.: P0300"}},
                    "required": ["codigo"]}},
]


class AgenteMecanico(Agente):
    nome = "SPECIALIST AGENT"
    responsabilidade = "Interpretar tecnicamente as evidencias, consultar a base e levantar hipoteses."

    def _evidencias(self, ctx) -> dict:
        visao = ctx.resultados.get("visao") or {}
        tele = ctx.resultados.get("telemetria") or {}
        audio = ctx.resultados.get("audio") or {}
        luzes = [l["chave"] for l in visao.get("luzes_acesas", [])]
        codigos = list(ctx.intencao.get("codigos_dtc", []))
        for txt in visao.get("mensagens_ou_codigos_visiveis", []) or []:
            codigos += extrair_codigos_dtc(txt)
        return {
            "pergunta": ctx.pergunta_efetiva(),
            "sintomas_relatados": ctx.intencao.get("sintomas", []),
            "luz_piscando": ctx.intencao.get("luz_piscando", False),
            "luzes_vistas_na_imagem": luzes,
            "instrumentos_na_imagem": visao.get("instrumentos"),
            "codigos_dtc": sorted(set(codigos)),
            "ruidos_no_audio": audio.get("ruidos_descritos", []),
            "anomalias_telemetria": tele.get("anomalias", []),
            "resumo_telemetria": tele.get("interpretacao"),
        }

    def executar(self, ctx):
        ev = self._evidencias(ctx)
        self.log.log(self.nome, f"Evidencias recebidas: luzes={ev['luzes_vistas_na_imagem']} codigos={ev['codigos_dtc']} "
                                f"anomalias={[a['metrica'] for a in ev['anomalias_telemetria']]}")
        resultado = {"evidencias": ev, "luzes": ev["luzes_vistas_na_imagem"], "codigos": ev["codigos_dtc"]}

        if self.llm.disponivel:
            try:
                funcoes = {"consultar_luz_painel": consultar_luz_painel, "consultar_codigo_dtc": consultar_codigo_dtc}
                executar = lambda nome, args: self.usar_ferramenta(ctx, nome, funcoes[nome], **args)
                resultado["analise"] = self.llm.conversar_com_ferramentas(
                    SISTEMA, "Evidencias:\n" + json.dumps(ev, ensure_ascii=False, indent=1), DECLARACOES, executar)
                self.log.log(self.nome, "Hipoteses elaboradas (LLM + consultas a base).")
                return resultado
            except Exception as e:
                self.log.log("ERRO", f"{self.nome}: falha no LLM ({e}); usando raciocinio por regras")

        resultado["analise"] = self._analise_por_regras(ctx, ev)
        self.log.log(self.nome, "Hipoteses elaboradas (modo regras + consultas a base).")
        return resultado

    # ---------------------------------------------------------- modo offline
    def _analise_por_regras(self, ctx, ev) -> str:
        linhas, verificacoes = [], []
        luzes = set(ev["luzes_vistas_na_imagem"])
        codigos = set(ev["codigos_dtc"])
        for a in ev["anomalias_telemetria"]:   # telemetria aponta para luzes/codigos relacionados
            if a.get("dtc_relacionado"):
                codigos.add(a["dtc_relacionado"])
        for luz in sorted(luzes):
            info = self.usar_ferramenta(ctx, "consultar_luz_painel", consultar_luz_painel, luz=luz)
            if info.get("encontrado"):
                linhas.append(f"- **{info['nome']}**: {info['significado']} Causas comuns: {', '.join(info['causas_comuns'][:3])}.")
                verificacoes.append(info["acao"])
        for cod in sorted(codigos):
            info = self.usar_ferramenta(ctx, "consultar_codigo_dtc", consultar_codigo_dtc, codigo=cod)
            if info.get("encontrado"):
                origem = "informado/visto" if cod in ev["codigos_dtc"] else "sugerido pela telemetria"
                linhas.append(f"- **{cod}** ({origem}): {info['descricao']}. Causas comuns: {', '.join(info['causas_comuns'][:3])}.")
                verificacoes.append(info["verificacao"])
            else:
                linhas.append(f"- **{cod}**: {info.get('mensagem')}")
        for a in ev["anomalias_telemetria"]:
            linhas.append(f"- Telemetria ({a['nivel']}): {a['mensagem']}.")
        if not linhas:
            linhas.append("- Nenhuma luz, codigo ou anomalia foi identificado com as informacoes disponiveis.")
            verificacoes.append("Enviar uma foto do painel e/ou o CSV de telemetria OBD-II para uma analise mais precisa.")
        out = "**Hipoteses e evidencias**\n" + "\n".join(linhas)
        out += "\n\n**Verificacoes sugeridas**\n" + "\n".join(f"{i}. {v}" for i, v in enumerate(dict.fromkeys(verificacoes), 1))
        return out
