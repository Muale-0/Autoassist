"""Gera os arquivos de exemplo (CSVs de telemetria e imagens sinteticas de painel).

Uso: python gerar_exemplos.py
Dica: para a apresentacao, fotos REAIS de painel funcionam ainda melhor.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

PASTA = Path(__file__).parent / "exemplos"
PASTA.mkdir(exist_ok=True)
rng = np.random.default_rng(42)


# ------------------------------------------------------------------ CSVs
def base(n=120, passo=5):
    t = np.arange(n) * passo
    vel = np.clip(40 + 25 * np.sin(t / 90) + rng.normal(0, 3, n), 0, None)
    rpm = 900 + vel * 35 + rng.normal(0, 40, n)
    return pd.DataFrame({"tempo_s": t, "velocidade_kmh": vel.round(1), "rpm": rpm.round(0),
                         "temp_motor_c": (90 + rng.normal(0, 1.2, n)).round(1),
                         "tensao_bateria_v": (14.1 + rng.normal(0, 0.08, n)).round(2),
                         "pressao_oleo_bar": (2.8 + rng.normal(0, 0.1, n)).round(2)})


df = base()
df.to_csv(PASTA / "telemetria_normal.csv", index=False)

df = base()
subida = np.clip((df.index - 50) * 0.45, 0, None)
df["temp_motor_c"] = (90 + subida + rng.normal(0, 0.8, len(df))).round(1)   # ate ~121 C
df.to_csv(PASTA / "telemetria_superaquecimento.csv", index=False)

df = base()
df.loc[90:, "velocidade_kmh"] = 0.0                                              # parado em marcha lenta
df.loc[90:, "rpm"] = (800 + rng.normal(0, 160, len(df) - 90)).round(0)          # RPM "falhando"
df.to_csv(PASTA / "telemetria_falha_ignicao.csv", index=False)

df = base()
df["tensao_bateria_v"] = np.linspace(13.9, 11.6, len(df)).round(2)              # alternador parou de carregar
df.to_csv(PASTA / "telemetria_bateria.csv", index=False)

(PASTA / "telemetria_invalida.csv").write_text("data;cliente;valor\n2026-01-01;Ana;10\n2026-01-02;Bia;20\n", encoding="utf-8")


# ------------------------------------------------------------------ Imagens
def fonte(tam):
    for nome in ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def mostrador(d, cx, cy, r, frac, rotulo, vermelho_a_partir=0.8):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(200, 200, 200), width=4)
    for i in range(11):
        a = math.radians(225 - 270 * i / 10)
        cor = (230, 40, 40) if i / 10 >= vermelho_a_partir else (220, 220, 220)
        d.line([cx + (r - 18) * math.cos(a), cy - (r - 18) * math.sin(a), cx + (r - 4) * math.cos(a), cy - (r - 4) * math.sin(a)], fill=cor, width=4)
    a = math.radians(225 - 270 * frac)
    d.line([cx, cy, cx + (r - 25) * math.cos(a), cy - (r - 25) * math.sin(a)], fill=(255, 90, 0), width=6)
    d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(255, 90, 0))
    d.text((cx, cy + r * 0.5), rotulo, fill=(220, 220, 220), font=fonte(20), anchor="mm")


def icone_temperatura(d, x, y, cor):
    d.line([x, y - 30, x, y + 10], fill=cor, width=7)
    for k in range(3):
        d.line([x, y - 25 + 10 * k, x + 12, y - 25 + 10 * k], fill=cor, width=4)
    d.ellipse([x - 10, y + 5, x + 10, y + 25], fill=cor)
    for off in (-8, 8):
        pts = [(x - 32 + i * 4, y + 22 + off + 4 * math.sin(i)) for i in range(17)]
        d.line(pts, fill=cor, width=4)


def icone_motor(d, x, y, cor):
    d.polygon([(x - 34, y - 12), (x - 14, y - 12), (x - 14, y - 22), (x + 10, y - 22), (x + 10, y - 12), (x + 24, y - 12),
               (x + 34, y - 20), (x + 34, y + 20), (x + 24, y + 12), (x + 24, y + 22), (x - 26, y + 22), (x - 34, y + 10)], outline=cor, width=5)


def icone_bateria(d, x, y, cor):
    d.rectangle([x - 32, y - 18, x + 32, y + 22], outline=cor, width=5)
    d.rectangle([x - 24, y - 26, x - 12, y - 18], fill=cor)
    d.rectangle([x + 12, y - 26, x + 24, y - 18], fill=cor)
    d.text((x - 18, y + 2), "-", fill=cor, font=fonte(26), anchor="mm")
    d.text((x + 18, y + 2), "+", fill=cor, font=fonte(26), anchor="mm")


def painel(nome, temp_frac, icones):
    img = Image.new("RGB", (900, 420), (12, 12, 16))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 10, 890, 410], radius=40, outline=(60, 60, 70), width=6)
    mostrador(d, 220, 200, 150, 0.35, "km/h")
    mostrador(d, 680, 200, 150, 0.25, "x1000 rpm")
    # mini-mostrador de temperatura (C ... H)
    d.text((450, 70), "C", fill=(200, 200, 200), font=fonte(22), anchor="mm")
    d.text((560, 70), "H", fill=(230, 40, 40), font=fonte(22), anchor="mm")
    d.rectangle([465, 62, 545, 78], outline=(200, 200, 200), width=2)
    d.rectangle([465, 62, 465 + 80 * temp_frac, 78], fill=(230, 40, 40) if temp_frac > 0.8 else (200, 200, 200))
    for i, (func, cor, rotulo) in enumerate(icones):
        x = 450 + (i - (len(icones) - 1) / 2) * 110
        func(d, x, 300, cor)
        d.text((x, 360), rotulo, fill=cor, font=fonte(14), anchor="mm")
    img.save(PASTA / nome)


VERMELHO, AMARELO = (235, 35, 35), (255, 180, 0)
painel("painel_superaquecimento.png", 0.95, [(icone_temperatura, VERMELHO, "TEMP")])
painel("painel_injecao.png", 0.5, [(icone_motor, AMARELO, "CHECK ENGINE")])
painel("painel_bateria.png", 0.5, [(icone_bateria, VERMELHO, "BATT")])
Image.new("RGB", (400, 300), (40, 120, 60)).save(PASTA / "imagem_nao_relacionada.png")  # p/ testar imagem fora de contexto
(PASTA / "imagem_corrompida.png").write_bytes(b"isto nao e uma imagem")
print("Exemplos gerados em", PASTA)
