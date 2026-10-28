"""FERRAMENTA: consulta a base de conhecimento local (luzes do painel e codigos OBD-II).

Por que uma ferramenta e nao so o LLM? Porque significados de codigos e acoes de
seguranca precisam vir de uma fonte controlada, e nao da "memoria" do modelo
(que pode alucinar).
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CAMINHO = Path(__file__).resolve().parent.parent / "dados" / "base_conhecimento.json"
PADRAO_DTC = re.compile(r"\b([PCBU][0-3][0-9A-F]{3})\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def carregar_base() -> dict:
    with open(CAMINHO, encoding="utf-8") as f:
        return json.load(f)


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def chaves_luzes() -> list[str]:
    return list(carregar_base()["luzes_painel"].keys())


def consultar_luz_painel(luz: str) -> dict:
    """Retorna significado, severidade e acao recomendada para uma luz do painel."""
    luzes = carregar_base()["luzes_painel"]
    chave = _normalizar(luz)
    if chave in luzes:
        return {"encontrado": True, "chave": chave, **luzes[chave]}
    # busca aproximada por palavras do nome
    for k, v in luzes.items():
        if chave and (chave in k or chave in _normalizar(v["nome"])):
            return {"encontrado": True, "chave": k, **v}
    return {"encontrado": False, "luz": luz, "mensagem": "Luz nao encontrada na base local.",
            "luzes_disponiveis": list(luzes.keys())}


def consultar_codigo_dtc(codigo: str) -> dict:
    """Retorna descricao, causas e verificacao para um codigo de falha OBD-II (ex.: P0300)."""
    codigo = (codigo or "").strip().upper()
    if not PADRAO_DTC.fullmatch(codigo):
        return {"encontrado": False, "codigo": codigo, "mensagem": "Formato invalido. Esperado algo como P0300."}
    dtcs = carregar_base()["codigos_dtc"]
    if codigo in dtcs:
        return {"encontrado": True, "codigo": codigo, **dtcs[codigo]}
    return {"encontrado": False, "codigo": codigo,
            "mensagem": "Codigo valido, mas fora da base local. Recomenda-se consultar o manual do fabricante."}


def extrair_codigos_dtc(texto: str) -> list[str]:
    return sorted({m.upper() for m in PADRAO_DTC.findall(texto or "")})
