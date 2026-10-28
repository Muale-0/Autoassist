"""ORCHESTRATOR AGENT: percebe as entradas, entende a intencao, decide a rota,
aciona os especialistas e entrega a resposta consolidada.
"""
from __future__ import annotations

import io
import re
from typing import Optional

from PIL import Image

from ferramentas.base_conhecimento import extrair_codigos_dtc
from ferramentas.telemetria import TelemetriaInvalida, carregar_csv
from nucleo.contexto import Contexto, RegistroFluxo
from nucleo.llm import LLM

from .audio import AgenteAudio
from .base import Agente
from .mecanico import AgenteMecanico
from .revisor import AgenteRevisor
from .telemetria import AgenteTelemetria
from .visao import AgenteVisao

SISTEMA_INTENCAO = """Voce e o Orchestrator Agent de um assistente automotivo. Classifique a solicitacao.
Responda SOMENTE em JSON:
{"intencao": "diagnostico" | "duvida_manutencao" | "fora_do_escopo",
 "sintomas": ["sintomas citados pelo usuario, curtos"],
 "luz_piscando": true/false (usuario disse que alguma luz esta piscando?),
 "justificativa": "uma frase"}
'fora_do_escopo' = assunto que nao tem relacao com veiculos."""

PALAVRAS_AUTO = ["carro", "motor", "luz", "painel", "oleo", "óleo", "bateria", "freio", "pneu", "temperatura", "esquent",
                 "barulho", "ruido", "ruído", "falha", "codigo", "código", "veiculo", "veículo", "moto", "injecao", "injeção",
                 "check engine", "aquecendo", "fumaca", "fumaça", "embreagem", "marcha", "rpm", "obd", "revis"]


class Orquestrador(Agente):
    nome = "ORCHESTRATOR"
    responsabilidade = "Perceber as modalidades, interpretar a intencao, rotear para especialistas e coordenar o fluxo."

    def __init__(self, llm: LLM, registro: RegistroFluxo):
        super().__init__(llm, registro)
        self.especialistas = {
            "audio": AgenteAudio(llm, registro),
            "visao": AgenteVisao(llm, registro),
            "telemetria": AgenteTelemetria(llm, registro),
            "mecanico": AgenteMecanico(llm, registro),
            "revisor": AgenteRevisor(llm, registro),
        }

    # ------------------------------------------------------------ 1. PERCEBER
    def perceber(self, texto: str = "", imagem: Optional[tuple[bytes, str]] = None,
                 audio: Optional[tuple[bytes, str]] = None, csv: Optional[bytes] = None) -> Contexto:
        ctx = Contexto(texto=(texto or "").strip())
        recebido = [n for n, v in (("texto", ctx.texto), ("imagem", imagem), ("audio", audio), ("telemetria CSV", csv)) if v]
        self.log.log("INPUT", f"Entradas recebidas: {', '.join(recebido) or 'nenhuma'}")
        if ctx.texto:
            ctx.modalidades.append("texto")
        if imagem:
            try:
                Image.open(io.BytesIO(imagem[0])).verify()
                ctx.imagem_bytes, ctx.imagem_mime = imagem
                ctx.modalidades.append("imagem")
            except Exception:
                ctx.avisos.append("O arquivo de imagem esta corrompido ou nao e uma imagem valida; foi ignorado.")
                self.log.log("ERRO", "Imagem invalida/corrompida - descartada")
        if audio:
            if len(audio[0]) < 1000:
                ctx.avisos.append("Audio muito curto ou vazio; foi ignorado.")
                self.log.log("ERRO", "Audio vazio/curto demais - descartado")
            else:
                ctx.audio_bytes, ctx.audio_mime = audio
                ctx.modalidades.append("audio")
        if csv is not None:
            try:
                ctx.telemetria = carregar_csv(csv)
                ctx.modalidades.append("dados (telemetria)")
            except TelemetriaInvalida as e:
                ctx.avisos.append(f"Telemetria descartada: {e}.")
                self.log.log("ERRO", f"CSV de telemetria invalido: {e}")
        self.log.log(self.nome, f"Modalidades validas identificadas: {ctx.modalidades or 'nenhuma'}")
        return ctx

    # ---------------------------------------------------------- 2. INTERPRETAR
    def interpretar(self, ctx: Contexto) -> None:
        pergunta = ctx.pergunta_efetiva()
        codigos = extrair_codigos_dtc(pergunta)
        intencao = None
        if self.llm.disponivel and pergunta:
            try:
                intencao = self.llm.gerar_json(f"Solicitacao do usuario: {pergunta}\nArquivos anexados: {ctx.modalidades}",
                                               SISTEMA_INTENCAO)
            except Exception as e:
                self.log.log("ERRO", f"Classificacao via LLM falhou ({e}); usando regras")
        if not intencao:  # classificador por regras (fallback / modo offline)
            baixo = pergunta.lower()
            ligado = any(p in baixo for p in PALAVRAS_AUTO) or bool(codigos)
            intencao = {"intencao": "diagnostico" if ligado or len(ctx.modalidades) > 1 or not pergunta else "fora_do_escopo",
                        "sintomas": [], "luz_piscando": bool(re.search(r"piscand|pisca", baixo)),
                        "justificativa": "classificacao por palavras-chave"}
        # Se o usuario mandou imagem/dados, consideramos que o pedido e sobre o veiculo
        if intencao.get("intencao") == "fora_do_escopo" and any(m != "texto" for m in ctx.modalidades):
            intencao["intencao"] = "diagnostico"
        intencao["codigos_dtc"] = codigos
        ctx.intencao = intencao
        self.log.log(self.nome, f"Intencao: {intencao['intencao']} | codigos no texto: {codigos or 'nenhum'} | "
                                f"motivo: {intencao.get('justificativa', '')}")

    # ------------------------------------------------------------- 3. PLANEJAR
    def planejar(self, ctx: Contexto) -> list[tuple[str, str]]:
        plano = []
        if ctx.imagem_bytes:
            plano.append(("visao", "ha uma imagem -> Vision Agent extrai luzes e instrumentos"))
        if ctx.telemetria is not None:
            plano.append(("telemetria", "ha dados OBD-II -> Data Agent calcula estatisticas e anomalias"))
        plano.append(("mecanico", "Specialist Agent cruza as evidencias e consulta a base de conhecimento"))
        plano.append(("revisor", "Reviewer valida consistencia, define urgencia e consolida"))
        ctx.plano = [p for p, _ in plano]
        return plano

    # -------------------------------------------------------------- EXECUTAR
    def _rodar(self, ctx: Contexto, chave: str) -> None:
        agente = self.especialistas[chave]
        try:
            ctx.resultados[chave] = agente.executar(ctx)
        except Exception as e:  # um agente com falha nao derruba o sistema
            ctx.resultados[chave] = None
            ctx.avisos.append(f"{agente.nome} falhou e foi ignorado ({type(e).__name__}).")
            self.log.log("ERRO", f"{agente.nome} falhou: {e}. O fluxo continua sem ele.")

    def executar(self, texto: str = "", imagem=None, audio=None, csv=None) -> Contexto:
        modo = f"Gemini ({self.llm.modelo})" if self.llm.disponivel else f"OFFLINE - {self.llm.motivo_indisponivel}"
        self.log.log("SISTEMA", f"Modo de execucao: {modo}")
        ctx = self.perceber(texto, imagem, audio, csv)

        # O audio e processado ANTES da interpretacao, pois a pergunta pode estar na fala
        if ctx.audio_bytes:
            self.log.log("ROUTING", "Audio presente -> Audio Agent (a pergunta pode estar na fala)")
            self._rodar(ctx, "audio")

        if not ctx.pergunta_efetiva() and not ctx.imagem_bytes and ctx.telemetria is None:
            ctx.resposta_final = ("## Nao foi possivel analisar\nNenhuma entrada valida foi recebida.\n\n"
                                  + "".join(f"- {a}\n" for a in ctx.avisos)
                                  + "\nEnvie uma descricao do problema e, se possivel, uma foto do painel ou o CSV OBD-II.")
            self.log.log("FINAL", "Encerrado: ausencia de entrada valida (pedido de nova entrada ao usuario)")
            return ctx

        self.interpretar(ctx)
        if ctx.intencao["intencao"] == "fora_do_escopo":
            ctx.resposta_final = ("## Fora do escopo\nSou um assistente automotivo e so consigo ajudar com duvidas "
                                  "sobre o seu veiculo (luzes do painel, codigos de falha, ruidos, telemetria).")
            self.log.log("ROUTING", "Pedido fora do escopo -> nenhum especialista acionado")
            self.log.log("FINAL", "Resposta de recusa educada entregue")
            return ctx

        plano = self.planejar(ctx)
        self.log.log("ROUTING", "Plano: " + " -> ".join(p for p, _ in plano))
        for chave, motivo in plano:
            self.log.log("ROUTING", f"Encaminhando para {self.especialistas[chave].nome}: {motivo}")
            self._rodar(ctx, chave)

        ctx.resposta_final = ctx.resultados.get("revisor") or (
            "## Resposta parcial\nO revisor falhou. Resultado do especialista:\n\n"
            + str((ctx.resultados.get("mecanico") or {}).get("analise", "indisponivel")))
        agentes = [self.especialistas[k].nome for k in ["audio"] + ctx.plano if ctx.resultados.get(k) is not None]
        self.log.log("FINAL", f"Resposta consolidada entregue | agentes acionados: {' -> '.join(agentes)} | "
                              f"ferramentas: {len(ctx.ferramentas_usadas)}")
        return ctx
