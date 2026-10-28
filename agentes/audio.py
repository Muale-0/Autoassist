"""AUDIO AGENT: transcreve o comando de voz e descreve ruidos do motor, se houver."""
from __future__ import annotations

from .base import Agente

SISTEMA = """Voce e o Audio Agent de um assistente automotivo. Sua responsabilidade e
transcrever a fala e descrever ruidos mecanicos presentes no audio. Nao faca diagnostico final."""

PROMPT = """Ouca o audio e responda SOMENTE em JSON:
{
  "transcricao": "fala do usuario em portugues ('' se nao houver fala)",
  "tipo": "fala" | "ruido_veiculo" | "misto" | "inaudivel",
  "ruidos_descritos": ["ex.: batida metalica ritmada", "chiado agudo ao frear"],
  "confianca": 0.0 a 1.0
}"""


class AgenteAudio(Agente):
    nome = "AUDIO AGENT"
    responsabilidade = "Transcrever comando de voz e descrever ruidos do veiculo."

    def executar(self, ctx):
        if not self.llm.disponivel:
            ctx.avisos.append("O audio nao foi processado: modelo indisponivel (modo offline).")
            self.log.log(self.nome, "Indisponivel. Seguindo sem o audio.")
            return None
        res = self.llm.gerar_json(PROMPT, SISTEMA, anexos=[(ctx.audio_bytes, ctx.audio_mime)])
        if res.get("tipo") == "inaudivel":
            ctx.avisos.append("Audio inaudivel ou sem conteudo util.")
        self.log.log(self.nome, f"Transcricao: \"{res.get('transcricao', '')}\" | ruidos: {res.get('ruidos_descritos', [])}", res)
        return res
