"""VISION AGENT: percebe o que existe na foto do painel (luzes, ponteiros, mensagens)."""
from __future__ import annotations

from ferramentas.base_conhecimento import chaves_luzes, consultar_luz_painel

from .base import Agente

SISTEMA = """Voce e o Vision Agent de um assistente automotivo.
Sua UNICA responsabilidade e DESCREVER o que esta visivel na imagem. Nao faca diagnostico.
Se nao tiver certeza de um simbolo, diga isso e reduza a confianca. Nunca invente luzes."""

PROMPT = """Analise a imagem e responda SOMENTE em JSON com o formato:
{{
  "e_painel_veicular": true/false,
  "qualidade_imagem": "boa" | "regular" | "ruim",
  "luzes_acesas": [{{"chave": "<uma de: {chaves} ou 'outra'>", "descricao": "...", "cor": "vermelha|amarela|verde|azul"}}],
  "instrumentos": {{"temperatura": "normal|alta|baixa|nao_visivel", "combustivel": "...", "velocidade_kmh": "...", "rpm": "..."}},
  "mensagens_ou_codigos_visiveis": ["texto exibido no painel, ex.: P0300"],
  "descricao_geral": "uma frase",
  "confianca": 0.0 a 1.0
}}
Pergunta do usuario (apenas para contexto): {pergunta}"""


class AgenteVisao(Agente):
    nome = "VISION AGENT"
    responsabilidade = "Identificar luzes de alerta, ponteiros e mensagens na foto do painel."

    def executar(self, ctx):
        if not self.llm.disponivel:
            ctx.avisos.append("A imagem nao foi analisada: modelo de visao indisponivel (modo offline).")
            self.log.log(self.nome, f"Indisponivel ({self.llm.motivo_indisponivel}). Seguindo sem a imagem.")
            return None
        res = self.llm.gerar_json(
            PROMPT.format(chaves=", ".join(chaves_luzes()), pergunta=ctx.pergunta_efetiva() or "(nenhuma)"),
            SISTEMA, anexos=[(ctx.imagem_bytes, ctx.imagem_mime)])

        if not res.get("e_painel_veicular", False):
            ctx.avisos.append("A imagem enviada nao parece ser um painel de veiculo; ela foi desconsiderada.")
            self.log.log(self.nome, f"Imagem NAO reconhecida como painel: {res.get('descricao_geral', '')}")
            res["luzes_acesas"] = []
            return res
        if res.get("qualidade_imagem") == "ruim" or float(res.get("confianca", 1)) < 0.4:
            ctx.avisos.append("Imagem com baixa qualidade/confianca; o resultado visual pode estar incompleto.")

        # Normaliza as chaves das luzes contra a base (evita nomes inventados)
        validas = []
        for luz in res.get("luzes_acesas", []):
            chave = luz.get("chave", "outra")
            if chave != "outra" and consultar_luz_painel(chave).get("encontrado"):
                validas.append(luz)
            else:
                ctx.avisos.append(f"Luz nao catalogada na base: {luz.get('descricao', chave)}")
        res["luzes_acesas"] = validas
        nomes = [l["chave"] for l in validas] or ["nenhuma luz catalogada"]
        self.log.log(self.nome, f"Luzes identificadas: {', '.join(nomes)} | instrumentos: {res.get('instrumentos')} "
                                f"| confianca {res.get('confianca')}", res)
        return res
