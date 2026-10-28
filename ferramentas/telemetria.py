"""FERRAMENTA: leitura, validacao e analise estatistica de telemetria OBD-II (CSV).

Calculos numericos sao feitos em Python (pandas), e nao pelo LLM: e mais
preciso, reprodutivel e barato.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .base_conhecimento import carregar_base

COLUNAS_CONHECIDAS = ["tempo_s", "velocidade_kmh", "rpm", "temp_motor_c", "tensao_bateria_v", "pressao_oleo_bar"]
APELIDOS = {
    "tempo": "tempo_s", "time": "tempo_s", "timestamp": "tempo_s",
    "velocidade": "velocidade_kmh", "speed": "velocidade_kmh",
    "temperatura": "temp_motor_c", "temp_motor": "temp_motor_c", "coolant_temp": "temp_motor_c",
    "bateria": "tensao_bateria_v", "tensao": "tensao_bateria_v", "voltage": "tensao_bateria_v",
    "pressao_oleo": "pressao_oleo_bar", "oil_pressure": "pressao_oleo_bar",
}


class TelemetriaInvalida(ValueError):
    pass


def carregar_csv(dados: bytes) -> pd.DataFrame:
    """Le e valida o CSV. Lanca TelemetriaInvalida com mensagem clara se algo estiver errado."""
    if not dados or not dados.strip():
        raise TelemetriaInvalida("o arquivo CSV esta vazio")
    try:
        df = pd.read_csv(io.BytesIO(dados), sep=None, engine="python")
    except Exception as e:
        raise TelemetriaInvalida(f"nao foi possivel ler o CSV ({e})")
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={c: APELIDOS.get(c, c) for c in df.columns})
    metricas = [c for c in COLUNAS_CONHECIDAS if c in df.columns and c != "tempo_s"]
    if len(metricas) < 2:
        raise TelemetriaInvalida(
            f"o CSV precisa de pelo menos 2 colunas de telemetria entre {COLUNAS_CONHECIDAS[1:]}; "
            f"colunas recebidas: {list(df.columns)}")
    for c in metricas + (["tempo_s"] if "tempo_s" in df.columns else []):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=metricas, how="all")
    if len(df) < 5:
        raise TelemetriaInvalida("o CSV tem menos de 5 leituras validas; nao e possivel analisar")
    if "tempo_s" not in df.columns:
        df["tempo_s"] = np.arange(len(df))
    return df[[c for c in COLUNAS_CONHECIDAS if c in df.columns]]


def analisar_telemetria(df: pd.DataFrame) -> dict:
    """Compara as leituras com os limites da base e devolve estatisticas + anomalias."""
    limites = carregar_base()["limites_telemetria"]
    estat, anomalias = {}, []
    for col in df.columns:
        if col == "tempo_s":
            continue
        s = df[col].dropna()
        estat[col] = {"min": round(float(s.min()), 2), "max": round(float(s.max()), 2),
                      "media": round(float(s.mean()), 2), "ultimo": round(float(s.iloc[-1]), 2)}

    def anomalia(metrica, nivel, msg, valor):
        lim = limites[metrica]
        anomalias.append({"metrica": metrica, "nivel": nivel, "mensagem": msg, "valor": valor,
                          "luz_relacionada": lim.get("luz_relacionada"), "dtc_relacionado": lim.get("dtc_relacionado")})

    # Temperatura do motor + tendencia (graus por minuto)
    if "temp_motor_c" in df:
        t = df["temp_motor_c"].dropna()
        lim = limites["temp_motor_c"]
        tend = float(np.polyfit(df.loc[t.index, "tempo_s"], t, 1)[0] * 60) if len(t) > 2 else 0.0
        estat["temp_motor_c"]["tendencia_c_por_min"] = round(tend, 2)
        pct = round(float((t > lim["normal_max"]).mean() * 100), 1)
        if t.max() >= lim["critico_max"]:
            anomalia("temp_motor_c", "critico", f"temperatura chegou a {t.max():.0f} C (limite critico {lim['critico_max']} C); "
                     f"{pct}% das leituras acima de {lim['normal_max']} C; tendencia {tend:+.1f} C/min", float(t.max()))
        elif t.max() > lim["normal_max"]:
            anomalia("temp_motor_c", "atencao", f"temperatura acima do normal ({t.max():.0f} C) em {pct}% das leituras", float(t.max()))

    # Tensao da bateria (so faz sentido com motor ligado: rpm > 400)
    if "tensao_bateria_v" in df:
        lig = df[df["rpm"] > 400] if "rpm" in df else df
        v = lig["tensao_bateria_v"].dropna()
        lim = limites["tensao_bateria_v"]
        if len(v):
            if v.min() <= lim["critico_min"]:
                anomalia("tensao_bateria_v", "critico", f"tensao caiu para {v.min():.2f} V com motor ligado (alternador nao carrega)", float(v.min()))
            elif v.median() < lim["normal_min"]:
                anomalia("tensao_bateria_v", "atencao", f"tensao mediana de {v.median():.2f} V com motor ligado (esperado >= {lim['normal_min']} V)", float(v.median()))
            elif v.max() > lim["normal_max"]:
                anomalia("tensao_bateria_v", "atencao", f"sobretensao de {v.max():.2f} V (regulador de tensao?)", float(v.max()))

    # Pressao de oleo
    if "pressao_oleo_bar" in df:
        lig = df[df["rpm"] > 400] if "rpm" in df else df
        p = lig["pressao_oleo_bar"].dropna()
        lim = limites["pressao_oleo_bar"]
        if len(p):
            if p.min() <= lim["critico_min"]:
                anomalia("pressao_oleo_bar", "critico", f"pressao de oleo caiu para {p.min():.2f} bar com motor ligado", float(p.min()))
            elif p.min() < lim["normal_min"]:
                anomalia("pressao_oleo_bar", "atencao", f"pressao de oleo baixa ({p.min():.2f} bar)", float(p.min()))

    # Oscilacao de RPM em marcha lenta -> possivel falha de ignicao
    if "rpm" in df and "velocidade_kmh" in df:
        lenta = df[(df["velocidade_kmh"] < 1) & (df["rpm"] > 400)]["rpm"]
        lim = limites["rpm"]
        if len(lenta) >= 5:
            desvio = float(lenta.std())
            estat["rpm"]["desvio_marcha_lenta"] = round(desvio, 1)
            if desvio > lim["marcha_lenta_desvio_max"]:
                anomalia("rpm", "atencao", f"RPM oscilando em marcha lenta (desvio padrao {desvio:.0f} rpm, "
                         f"limite {lim['marcha_lenta_desvio_max']}) - padrao tipico de falha de ignicao", desvio)

    duracao = float(df["tempo_s"].max() - df["tempo_s"].min())
    return {"leituras": int(len(df)), "duracao_s": round(duracao, 1), "colunas": list(df.columns),
            "estatisticas": estat, "anomalias": anomalias}
