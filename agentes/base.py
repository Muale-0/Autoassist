"""Classe base dos agentes e utilitario para executar ferramentas com registro."""
from __future__ import annotations

import json
from typing import Any, Callable

from nucleo.contexto import Contexto, RegistroFluxo
from nucleo.llm import LLM


class Agente:
    nome = "AGENTE"
    responsabilidade = ""

    def __init__(self, llm: LLM, registro: RegistroFluxo):
        self.llm = llm
        self.log = registro

    def executar(self, ctx: Contexto) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def usar_ferramenta(self, ctx: Contexto, nome: str, funcao: Callable, **args) -> Any:
        """Executa uma ferramenta, registra a chamada no fluxo e guarda no contexto."""
        args_txt = ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "df")
        self.log.log("TOOL", f"{self.nome} -> {nome}({args_txt})")
        try:
            resultado = funcao(**args)
        except Exception as e:
            resultado = {"erro": str(e)}
            self.log.log("ERRO", f"Ferramenta {nome} falhou: {e}")
        resumo = json.dumps(resultado, ensure_ascii=False, default=str)
        self.log.log("TOOL", f"{nome} retornou: {resumo[:220]}{'...' if len(resumo) > 220 else ''}", resultado)
        ctx.ferramentas_usadas.append({"agente": self.nome, "ferramenta": nome, "args": {k: v for k, v in args.items() if k != "df"}})
        return resultado
