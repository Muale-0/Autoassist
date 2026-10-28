"""AutoAssist IA - interface Streamlit.

Execucao:  streamlit run app.py
"""
import json
import os
import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from agentes.orquestrador import Orquestrador  # noqa: E402
from cenarios import CENARIOS  # noqa: E402
from nucleo.contexto import RegistroFluxo  # noqa: E402
from nucleo.llm import LLM, MODELO_PADRAO  # noqa: E402

st.set_page_config(page_title="AutoAssist IA", layout="wide")
st.markdown(f"<style>{(RAIZ / 'estilo.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

CORES = {"INPUT": "#6b7280", "SISTEMA": "#6b7280", "ORCHESTRATOR": "#7c3aed", "ROUTING": "#2563eb",
         "VISION AGENT": "#0891b2", "AUDIO AGENT": "#0d9488", "DATA AGENT": "#16a34a",
         "SPECIALIST AGENT": "#ca8a04", "TOOL": "#ea580c", "REVIEW": "#db2777", "FINAL": "#4fd1ff", "ERRO": "#dc2626"}


def linha_html(ev):
    cor = CORES.get(ev.etapa, "#8aa0b8")
    return (f"<div style='font-family:monospace;font-size:13px;margin:2px 0'>"
            f"<span style='color:{cor};font-weight:700'>[{ev.etapa}]</span> {ev.mensagem}</div>")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Configuracao")
    chave_padrao = os.getenv("GEMINI_API_KEY", "")
    try:
        chave_padrao = chave_padrao or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    api_key = st.text_input("Chave da API Gemini", value=chave_padrao, type="password",
                            help="Gratuita em aistudio.google.com. Sem chave, o sistema roda em MODO OFFLINE.")
    modelo = st.text_input("Modelo", value=MODELO_PADRAO)
    st.divider()
    st.subheader("Cenarios de demonstracao")
    idx = st.selectbox("Escolha um cenario", range(len(CENARIOS)), format_func=lambda i: f"{i + 1}. {CENARIOS[i]['titulo']}")
    if st.button("Carregar cenario", use_container_width=True):
        st.session_state["cenario"] = CENARIOS[idx]
        st.session_state["texto"] = CENARIOS[idx]["texto"]
    if st.session_state.get("cenario") and st.button("Limpar cenario", use_container_width=True):
        st.session_state.pop("cenario")
        st.session_state["texto"] = ""
    st.divider()
    with st.expander("Agentes do sistema"):
        o = Orquestrador(LLM(api_key=""), RegistroFluxo())
        st.markdown(f"**{o.nome}** — {o.responsabilidade}")
        for a in o.especialistas.values():
            st.markdown(f"**{a.nome}** — {a.responsabilidade}")

# ------------------------------------------------------------------ main
st.title("AutoAssist IA")
st.caption("Assistente automotivo multimodal e multiagente — texto + foto do painel + audio + telemetria OBD-II")

cen = st.session_state.get("cenario")
col1, col2 = st.columns([1, 1])
with col1:
    texto = st.text_area("Descreva o problema", key="texto", height=110,
                         placeholder="Ex.: acendeu uma luz vermelha e o carro esta esquentando...")
    img_up = st.file_uploader("Foto do painel (opcional)", type=["png", "jpg", "jpeg", "webp"])
    csv_up = st.file_uploader("Telemetria OBD-II em CSV (opcional)", type=["csv", "txt"])
with col2:
    aud_up = st.file_uploader("Audio (opcional) — comando de voz ou ruido do motor", type=["wav", "mp3", "m4a", "ogg"])
    aud_rec = st.audio_input("...ou grave aqui")
    if cen:
        st.info(f"Cenario carregado: **{cen['titulo']}**\n\nArquivos: "
                + (", ".join(Path(cen[k]).name for k in ("imagem", "csv", "audio") if cen.get(k)) or "nenhum"))
        if cen.get("imagem") and Path(RAIZ / cen["imagem"]).exists():
            try:
                st.image(str(RAIZ / cen["imagem"]), width=320)
            except Exception:
                st.warning("A imagem do cenario nao pode ser exibida (arquivo invalido - proposital neste cenario).")


def arquivo(upload, chave_cenario, mime_padrao):
    if upload is not None:
        return upload.getvalue(), upload.type or mime_padrao
    if cen and cen.get(chave_cenario):
        p = RAIZ / cen[chave_cenario]
        return p.read_bytes(), mime_padrao if p.suffix != ".jpg" else "image/jpeg"
    return None


if st.button("Analisar", type="primary", use_container_width=True):
    imagem = arquivo(img_up, "imagem", "image/png")
    audio = (aud_rec.getvalue(), "audio/wav") if aud_rec else arquivo(aud_up, "audio", "audio/wav")
    csv = arquivo(csv_up, "csv", "text/csv")

    llm = LLM(api_key=api_key or None, modelo=modelo or None)
    with st.status("Agentes trabalhando...", expanded=True) as status:
        registro = RegistroFluxo(ao_registrar=lambda ev: st.markdown(linha_html(ev), unsafe_allow_html=True))
        ctx = Orquestrador(llm, registro).executar(texto, imagem, audio, csv[0] if csv else None)
        status.update(label="Fluxo concluido", state="complete", expanded=False)
    st.session_state["resultado"] = (ctx, registro)

if "resultado" in st.session_state:
    ctx, registro = st.session_state["resultado"]
    st.subheader("Resposta final")
    st.markdown(ctx.resposta_final)

    abas = st.tabs(["Fluxo dos agentes", "Contexto compartilhado", "Ferramentas", "Telemetria"])
    with abas[0]:
        st.markdown("".join(linha_html(e) for e in registro.eventos), unsafe_allow_html=True)
        st.download_button("Baixar log do fluxo", registro.como_texto(), "fluxo_agentes.txt")
    with abas[1]:
        st.caption("O que cada agente escreveu no contexto (blackboard) e foi lido pelos agentes seguintes.")
        st.json({"modalidades": ctx.modalidades, "intencao": ctx.intencao, "plano": ctx.plano, "urgencia": ctx.urgencia,
                 "avisos": ctx.avisos,
                 "resultados": json.loads(json.dumps({k: v for k, v in ctx.resultados.items() if k != "revisor"},
                                                     default=str, ensure_ascii=False))})
    with abas[2]:
        st.table(ctx.ferramentas_usadas) if ctx.ferramentas_usadas else st.write("Nenhuma ferramenta usada.")
    with abas[3]:
        if ctx.telemetria is not None:
            cols = [c for c in ctx.telemetria.columns if c != "tempo_s"]
            sel = st.multiselect("Grandezas", cols, default=[c for c in ["temp_motor_c", "tensao_bateria_v"] if c in cols] or cols[:1])
            if sel:
                st.line_chart(ctx.telemetria.set_index("tempo_s")[sel])
        else:
            st.write("Nenhuma telemetria valida nesta execucao.")
