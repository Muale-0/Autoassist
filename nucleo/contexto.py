"""Contexto compartilhado entre os agentes + registro (log) do fluxo.

O Contexto funciona como um "quadro negro" (blackboard): cada agente le o que
precisa e escreve seu resultado. Assim, a saida de um agente alimenta o proximo.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pandas as pd


@dataclass
class Evento:
    etapa: str          # ex.: INPUT, ORCHESTRATOR, ROUTING, VISION AGENT, TOOL, REVIEW, FINAL, ERRO
    mensagem: str
    detalhes: Any = None
    instante: float = field(default_factory=time.time)

    def linha(self) -> str:
        return f"[{self.etapa}] {self.mensagem}"


class RegistroFluxo:
    """Guarda a sequencia de eventos para mostrar quais agentes foram acionados e em que ordem."""

    def __init__(self, ao_registrar: Optional[Callable[[Evento], None]] = None, verboso: bool = False):
        self.eventos: list[Evento] = []
        self._callback = ao_registrar
        self._verboso = verboso

    def log(self, etapa: str, mensagem: str, detalhes: Any = None) -> None:
        ev = Evento(etapa, mensagem, detalhes)
        self.eventos.append(ev)
        if self._verboso:
            print(ev.linha())
        if self._callback:
            self._callback(ev)

    def como_texto(self) -> str:
        return "\n".join(e.linha() for e in self.eventos)


@dataclass
class Contexto:
    # ---- entradas (percepcao) ----
    texto: str = ""
    imagem_bytes: Optional[bytes] = None
    imagem_mime: str = "image/jpeg"
    audio_bytes: Optional[bytes] = None
    audio_mime: str = "audio/wav"
    telemetria: Optional[pd.DataFrame] = None

    # ---- preenchido pelo orquestrador ----
    modalidades: list[str] = field(default_factory=list)
    intencao: dict = field(default_factory=dict)
    plano: list[str] = field(default_factory=list)

    # ---- resultados de cada agente (memoria compartilhada) ----
    resultados: dict[str, Any] = field(default_factory=dict)
    ferramentas_usadas: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)   # problemas nao fatais (ex.: imagem ilegivel)

    # ---- saida ----
    resposta_final: str = ""
    urgencia: dict = field(default_factory=dict)

    def pergunta_efetiva(self) -> str:
        """Texto digitado + transcricao do audio (se houver)."""
        partes = [self.texto.strip()]
        audio = self.resultados.get("audio")
        if audio and audio.get("transcricao"):
            partes.append(f"(fala do usuario) {audio['transcricao']}")
        return "\n".join(p for p in partes if p)
