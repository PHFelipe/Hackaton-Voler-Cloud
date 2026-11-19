"""Agente Saúde Conecta: interpreta o pedido, escolhe as ferramentas MCP e monta a resposta."""

from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mcp_client import ClienteMCP, ResultadoFerramenta

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"
MAX_ITERACOES = 16
PROVEDOR_PADRAO = "groq"
MODELO_PADRAO = {"groq": "openai/gpt-oss-120b", "anthropic": "claude-opus-5-5"}
# Modelos Claude que aceitam o parâmetro server-side `fallbacks`.
MODELOS_COM_FALLBACK = {
    "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1",
}

FERRAMENTA_CARTOES = {
    "name": "registrar_estabelecimentos",
    "description": (
        "Registra os estabelecimentos que serão exibidos como cartões na interface. "
        "Use somente dados retornados pelas ferramentas do MCP Brasil nesta conversa, "
        "copiados sem alteração. Deixe vazio o campo que não foi retornado. "
        "Chame no máximo uma vez por resposta, antes do texto final."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "estabelecimentos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cnes": {"type": "string", "description": "Código CNES como retornado."},
                        "nome": {"type": "string"},
                        "tipo": {"type": "string", "description": "Tipo de estabelecimento."},
                        "endereco": {"type": "string"},
                        "bairro": {"type": "string"},
                        "municipio": {"type": "string", "description": "Nome do município."},
                        "uf": {"type": "string"},
                        "telefone": {"type": "string"},
                        "gestao": {"type": "string"},
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                        "atualizado_em": {"type": "string"},
                        "relevancia": {
                            "type": "string",
                            "description": "Uma frase: por que esta unidade pode ser compatível com o pedido.",
                        },
                        "nao_confirmado": {
                            "type": "string",
                            "description": "O que os dados não permitem confirmar (especialidade, público, SUS...).",
                        },
                    },
                    "required": ["cnes", "nome", "relevancia", "nao_confirmado"],
                },
            }
        },
        "required": ["estabelecimentos"],
    },
}

CAMPOS_TEXTO_VERIFICAVEIS = ("cnes", "nome", "tipo", "endereco", "bairro", "municipio", "uf",
                             "telefone", "gestao", "atualizado_em")


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


@dataclass
class Evento:
    tipo: str  # "ferramenta", "resultado", "aviso"
    mensagem: str


@dataclass
class Resposta:
    texto: str
    cartoes: list[dict[str, Any]] = field(default_factory=list)
    chamadas: list[ResultadoFerramenta] = field(default_factory=list)
    descartados: list[str] = field(default_factory=list)


@dataclass
class EstadoConversa:
    """Tudo o que precisa sobreviver entre turnos (guardado no st.session_state)."""

    mensagens: list[dict[str, Any]] = field(default_factory=list)
    # Textos brutos devolvidos pelo servidor MCP, usados para conferir os cartões.
    evidencias: list[str] = field(default_factory=list)


class VerificadorEvidencias:
    """Confere se cada valor de um cartão aparece literalmente nas respostas do MCP."""

    def __init__(self, textos: list[str]):
        self._corpus = _normalizar("\n".join(textos))
        self._numeros = [float(n) for n in re.findall(r"-?\d+\.\d+", "\n".join(textos))]

    def contem(self, valor: str, exato: bool = False) -> bool:
        v = _normalizar(valor)
        if not v or v in ("—", "-"):
            return False
        if exato:  # códigos e telefones: não aceitar trecho de outro número
            return re.search(rf"(?<![\w]){re.escape(v)}(?![\w])", self._corpus) is not None
        return v in self._corpus

    def contem_numero(self, valor: float) -> bool:
        return any(abs(valor - n) < 1e-6 for n in self._numeros)

    def filtrar(self, cartoes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        aprovados, descartados = [], []
        for bruto in cartoes:
            cartao = {k: v for k, v in bruto.items() if v not in (None, "", "—")}
            if not (self.contem(str(cartao.get("cnes", "")), exato=True) and self.contem(str(cartao.get("nome", "")))):
                descartados.append(f"{cartao.get('nome', '?')} (CNES {cartao.get('cnes', '?')})")
                continue
            removidos = []
            for campo in CAMPOS_TEXTO_VERIFICAVEIS:
                exato = campo in ("cnes", "telefone", "uf")
                if campo in cartao and not self.contem(str(cartao[campo]), exato=exato):
                    removidos.append(campo)
                    cartao.pop(campo)
            for campo in ("latitude", "longitude"):
                if campo in cartao:
                    try:
                        ok = self.contem_numero(float(cartao[campo]))
                    except (TypeError, ValueError):
                        ok = False
                    if not ok:
                        removidos.append(campo)
                        cartao.pop(campo)
            if ("latitude" in cartao) != ("longitude" in cartao):
                cartao.pop("latitude", None)
                cartao.pop("longitude", None)
            cartao["campos_nao_conferidos"] = removidos
            aprovados.append(cartao)
        return aprovados, descartados


class ErroModelo(RuntimeError):
    """Falha ao falar com a API do modelo de linguagem (chave, limite, rede...)."""


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict[str, Any]
    erro_argumentos: str | None = None


@dataclass
class Passo:
    texto: str
    chamadas: list[ChamadaFerramenta]
    recusado: bool = False
    continuar: bool = False  # pause_turn (Claude)


class ProvedorGroq:
    """API da Groq (formato Chat Completions, compatível com OpenAI)."""

    nome = "groq"

    def __init__(self, modelo: str, esforco: str, system: str):
        import groq

        self._groq = groq
        self.modelo, self.esforco, self.system = modelo, esforco, system
        self.cliente = groq.AsyncGroq()  # lê GROQ_API_KEY do ambiente

    def converter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]

    async def passo(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Passo:
        params: dict[str, Any] = dict(
            model=self.modelo,
            messages=[{"role": "system", "content": self.system}, *mensagens],
            tools=tools,
            tool_choice="auto",
            temperature=0.2,  # a documentação da Groq recomenda 0.0 a 0.5 para tool calling
            max_completion_tokens=8192,
        )
        if self.modelo.startswith("openai/gpt-oss"):
            params["reasoning_effort"] = self.esforco
        ultimo_erro: Exception | None = None
        for _ in range(3):  # a Groq devolve 400 "tool_use_failed" quando a chamada sai malformada
            try:
                resp = await self.cliente.chat.completions.create(**params)
                break
            except self._groq.BadRequestError as exc:
                if "tool_use_failed" not in str(exc) and "failed_generation" not in str(exc):
                    raise ErroModelo(f"A Groq recusou a requisição: {exc}") from exc
                ultimo_erro = exc
            except self._groq.AuthenticationError as exc:
                raise ErroModelo("A GROQ_API_KEY do .env foi recusada pela Groq. Confira a chave.") from exc
            except self._groq.RateLimitError as exc:
                raise ErroModelo("Limite de uso da Groq atingido. Aguarde um pouco e tente de novo.") from exc
            except self._groq.APIError as exc:
                raise ErroModelo(f"Falha ao falar com a Groq: {exc}") from exc
        else:
            raise ErroModelo(f"O modelo gerou chamadas de ferramenta inválidas três vezes: {ultimo_erro}")

        msg = resp.choices[0].message
        chamadas: list[ChamadaFerramenta] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                erro = None if isinstance(args, dict) else "argumentos não são um objeto JSON"
            except json.JSONDecodeError as exc:
                args, erro = {}, f"JSON inválido nos argumentos: {exc}"
            chamadas.append(ChamadaFerramenta(tc.id, tc.function.name, args if isinstance(args, dict) else {}, erro))
        assistente: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistente["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in msg.tool_calls
            ]
        mensagens.append(assistente)
        return Passo(texto=(msg.content or "").strip(), chamadas=chamadas)

    def adicionar_resultados(self, mensagens: list[dict[str, Any]], resultados: list[tuple[ChamadaFerramenta, str, bool]]) -> None:
        for chamada, texto, erro in resultados:
            mensagens.append({"role": "tool", "tool_call_id": chamada.id, "name": chamada.nome,
                              "content": ("ERRO: " if erro else "") + texto})


class ProvedorAnthropic:
    """API do Claude (Messages API)."""

    nome = "anthropic"

    def __init__(self, modelo: str, esforco: str, system: str):
        import anthropic

        self._anthropic = anthropic
        self.modelo, self.esforco, self.system = modelo, esforco, system
        self.fallbacks = os.getenv("LLM_FALLBACKS", "default").strip()
        self.cliente = anthropic.AsyncAnthropic()  # lê ANTHROPIC_API_KEY do ambiente

    def converter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return tools

    async def passo(self, mensagens: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Passo:
        params: dict[str, Any] = dict(
            model=self.modelo, max_tokens=16000, system=self.system, tools=tools, messages=mensagens,
            thinking={"type": "adaptive"}, output_config={"effort": self.esforco},
        )
        try:
            if self.fallbacks and self.modelo in MODELOS_COM_FALLBACK:
                msg = await self.cliente.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks=self.fallbacks)
            else:
                msg = await self.cliente.messages.create(**params)
        except self._anthropic.AuthenticationError as exc:
            raise ErroModelo("A ANTHROPIC_API_KEY do .env foi recusada. Confira a chave.") from exc
        except self._anthropic.APIError as exc:
            raise ErroModelo(f"Falha ao falar com a API do Claude: {exc}") from exc
        mensagens.append({"role": "assistant", "content": msg.content})
        chamadas = [ChamadaFerramenta(b.id, b.name, dict(b.input or {}))
                    for b in msg.content if b.type == "tool_use"]
        texto = "\n".join(b.text for b in msg.content if b.type == "text").strip()
        return Passo(texto=texto, chamadas=chamadas, recusado=msg.stop_reason == "refusal",
                     continuar=msg.stop_reason == "pause_turn")

    def adicionar_resultados(self, mensagens: list[dict[str, Any]], resultados: list[tuple[ChamadaFerramenta, str, bool]]) -> None:
        mensagens.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": t, "is_error": e}
            for c, t, e in resultados]})


PROVEDORES = {"groq": ProvedorGroq, "anthropic": ProvedorAnthropic}


class AgenteSaudeConecta:
    def __init__(self, provedor: str | None = None, modelo: str | None = None, esforco: str | None = None):
        self.provedor = (provedor or os.getenv("LLM_PROVIDER") or PROVEDOR_PADRAO).strip().lower()
        if self.provedor not in PROVEDORES:
            raise ErroModelo(f"LLM_PROVIDER inválido: {self.provedor}. Use groq ou anthropic.")
        self.modelo = modelo or os.getenv("LLM_MODEL") or MODELO_PADRAO[self.provedor]
        self.esforco = esforco or os.getenv("LLM_EFFORT") or "medium"
        self.system = PROMPT_PATH.read_text(encoding="utf-8")
        self.llm = PROVEDORES[self.provedor](self.modelo, self.esforco, self.system)

    async def responder(
        self,
        estado: EstadoConversa,
        pergunta: str,
        mcp: ClienteMCP,
        ao_evento: Callable[[Evento], None] | None = None,
    ) -> Resposta:
        avisar = ao_evento or (lambda e: None)
        tools = self.llm.converter_tools(mcp.ferramentas_para_llm() + [FERRAMENTA_CARTOES])
        mensagens = estado.mensagens
        mensagens.append({"role": "user", "content": pergunta})
        resposta = Resposta(texto="")
        cartoes_propostos: list[dict[str, Any]] = []

        async def executar(ch: ChamadaFerramenta) -> tuple[ChamadaFerramenta, str, bool]:
            if ch.erro_argumentos:
                return ch, f"Chamada inválida: {ch.erro_argumentos}. Refaça a chamada.", True
            if ch.nome == FERRAMENTA_CARTOES["name"]:
                lista = ch.argumentos.get("estabelecimentos") or []
                cartoes_propostos[:] = [c for c in lista if isinstance(c, dict)]
                return ch, f"{len(cartoes_propostos)} cartões registrados.", False
            avisar(Evento("ferramenta", f"Consultando {ch.nome} {json.dumps(ch.argumentos, ensure_ascii=False)}"))
            r = await mcp.chamar(ch.nome, ch.argumentos)
            resposta.chamadas.append(r)
            if not r.erro:
                estado.evidencias.append(r.texto)
            avisar(Evento("resultado" if not r.erro else "aviso", f"{ch.nome}: {'erro' if r.erro else 'ok'}"))
            return ch, r.texto, r.erro

        for _ in range(MAX_ITERACOES):
            passo = await self.llm.passo(mensagens, tools)
            if passo.recusado:
                resposta.texto = ("Não consegui processar esse pedido. Posso ajudar a localizar "
                                  "estabelecimentos de saúde em um município.")
                break
            if passo.continuar:
                continue
            if not passo.chamadas:
                resposta.texto = passo.texto
                break
            resultados = await asyncio.gather(*(executar(c) for c in passo.chamadas))
            self.llm.adicionar_resultados(mensagens, list(resultados))
        else:
            resposta.texto = "A consulta ficou longa demais e foi interrompida. Tente uma pergunta mais específica."

        if cartoes_propostos:
            verificador = VerificadorEvidencias(estado.evidencias)
            resposta.cartoes, resposta.descartados = verificador.filtrar(cartoes_propostos)
        return resposta
