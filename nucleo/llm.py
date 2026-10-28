"""Camada fina sobre a API do Google Gemini.

Se nao houver chave de API (ou a API falhar), o sistema continua funcionando em
MODO OFFLINE: os agentes que dependem de visao/audio ficam indisponiveis e os
demais usam regras + ferramentas locais. Isso faz parte do tratamento de erros.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Optional

MODELO_PADRAO = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


class LLMErro(Exception):
    pass


class LLM:
    def __init__(self, api_key: Optional[str] = None, modelo: Optional[str] = None):
        self.modelo = modelo or MODELO_PADRAO
        self.disponivel = False
        self.motivo_indisponivel = ""
        chave = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not chave:
            self.motivo_indisponivel = "nenhuma chave GEMINI_API_KEY configurada"
            return
        try:
            from google import genai
            from google.genai import types

            self._types = types
            self.client = genai.Client(api_key=chave)
            self.disponivel = True
        except Exception as e:  # pacote ausente, chave mal formatada etc.
            self.motivo_indisponivel = f"falha ao iniciar cliente Gemini: {e}"

    # ------------------------------------------------------------------ util
    def _chamar(self, contents, config, tentativas: int = 2):
        ultimo = None
        for i in range(tentativas):
            try:
                return self.client.models.generate_content(model=self.modelo, contents=contents, config=config)
            except Exception as e:
                ultimo = e
                time.sleep(1.5 * (i + 1))
        raise LLMErro(f"Gemini falhou apos {tentativas} tentativas: {ultimo}")

    def _parte_binaria(self, dados: bytes, mime: str):
        return self._types.Part.from_bytes(data=dados, mime_type=mime)

    # --------------------------------------------------------------- publico
    def gerar(self, prompt: str, sistema: str = "", anexos: Optional[list[tuple[bytes, str]]] = None,
              json_mode: bool = False, temperatura: float = 0.2) -> str:
        if not self.disponivel:
            raise LLMErro(self.motivo_indisponivel)
        t = self._types
        contents = [self._parte_binaria(b, m) for b, m in (anexos or [])] + [prompt]
        config = t.GenerateContentConfig(
            system_instruction=sistema or None,
            temperature=temperatura,
            response_mime_type="application/json" if json_mode else None,
        )
        resp = self._chamar(contents, config)
        return (resp.text or "").strip()

    def gerar_json(self, prompt: str, sistema: str = "", anexos=None) -> dict:
        bruto = self.gerar(prompt, sistema, anexos, json_mode=True)
        return extrair_json(bruto)

    def conversar_com_ferramentas(self, sistema: str, prompt: str, declaracoes: list[dict],
                                  executar: Callable[[str, dict], Any], max_passos: int = 6) -> str:
        """Loop de agente: o modelo DECIDE chamar uma ferramenta, nos EXECUTAMOS,
        devolvemos a OBSERVACAO e ele continua ate produzir a resposta final."""
        if not self.disponivel:
            raise LLMErro(self.motivo_indisponivel)
        t = self._types
        ferramentas = [t.Tool(function_declarations=[
            t.FunctionDeclaration(name=d["name"], description=d["description"],
                                  parameters_json_schema=d["parameters"]) for d in declaracoes])]
        config = t.GenerateContentConfig(
            system_instruction=sistema, temperature=0.2, tools=ferramentas,
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
        )
        contents: list = [t.Content(role="user", parts=[t.Part.from_text(text=prompt)])]
        for _ in range(max_passos):
            resp = self._chamar(contents, config)
            chamadas = resp.function_calls or []
            if not chamadas:
                return (resp.text or "").strip()
            contents.append(resp.candidates[0].content)
            respostas = []
            for c in chamadas:
                resultado = executar(c.name, dict(c.args or {}))
                respostas.append(t.Part.from_function_response(name=c.name, response={"resultado": resultado}))
            contents.append(t.Content(role="user", parts=respostas))
        raise LLMErro("limite de passos de ferramenta atingido")


def extrair_json(texto: str) -> dict:
    """Extrai JSON mesmo que o modelo devolva com ```json ... ``` em volta."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.MULTILINE).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise LLMErro(f"resposta nao era JSON valido: {texto[:200]}")
