"""Executa o sistema pelo terminal, mostrando o fluxo entre os agentes.

Exemplos:
  python executar_cli.py --texto "A luz de temperatura acendeu" --imagem exemplos/painel_superaquecimento.png --csv exemplos/telemetria_superaquecimento.csv
  python executar_cli.py --cenario 2
"""
import argparse
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agentes.orquestrador import Orquestrador  # noqa: E402
from cenarios import CENARIOS  # noqa: E402
from nucleo.contexto import RegistroFluxo  # noqa: E402
from nucleo.llm import LLM  # noqa: E402


def ler(caminho):
    if not caminho:
        return None
    p = Path(caminho)
    if not p.exists():
        sys.exit(f"Arquivo nao encontrado: {caminho}")
    return p.read_bytes(), (mimetypes.guess_type(p.name)[0] or "application/octet-stream")


def main():
    ap = argparse.ArgumentParser(description="AutoAssist IA - sistema multimodal multiagente")
    ap.add_argument("--texto", default="")
    ap.add_argument("--imagem")
    ap.add_argument("--audio")
    ap.add_argument("--csv")
    ap.add_argument("--cenario", type=int, help="numero de um cenario pronto (ver cenarios.py)")
    ap.add_argument("--offline", action="store_true", help="forca o modo offline (sem Gemini)")
    a = ap.parse_args()

    if a.cenario:
        c = CENARIOS[a.cenario - 1]
        print(f"=== Cenario {a.cenario}: {c['titulo']} ===")
        a.texto, a.imagem, a.csv, a.audio = c["texto"], c.get("imagem"), c.get("csv"), c.get("audio")

    llm = LLM(api_key="" if a.offline else None)
    if a.offline:
        llm.disponivel, llm.motivo_indisponivel = False, "modo offline forcado"
    registro = RegistroFluxo(verboso=True)
    csv = ler(a.csv)
    ctx = Orquestrador(llm, registro).executar(a.texto, ler(a.imagem), ler(a.audio), csv[0] if csv else None)
    print("\n" + "=" * 70 + "\nRESPOSTA FINAL\n" + "=" * 70)
    print(ctx.resposta_final)


if __name__ == "__main__":
    main()
