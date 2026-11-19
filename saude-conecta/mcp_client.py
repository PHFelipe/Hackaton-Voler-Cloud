"""Cliente MCP do Saúde Conecta.

Conecta-se ao servidor externo MCP Brasil (https://github.com/Mcp-Brasil/mcp-brasil)
pelo transporte Streamable HTTP, descobre as ferramentas de saúde via `tools/list`
e executa as chamadas via `tools/call`.

Este módulo NÃO implementa um servidor MCP. Ele apenas consome o servidor externo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from ferramentas import FERRAMENTAS_SAUDE as FERRAMENTAS_PADRAO  # noqa: E402

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


class MCPConfigError(RuntimeError):
    """Configuração do servidor MCP ausente ou inválida."""


@dataclass
class ResultadoFerramenta:
    nome: str
    argumentos: dict[str, Any]
    texto: str
    erro: bool


@dataclass
class ConfigMCP:
    url: str
    token: str | None = None
    ferramentas: tuple[str, ...] = FERRAMENTAS_PADRAO
    timeout: float = 60.0

    @classmethod
    def do_ambiente(cls) -> "ConfigMCP":
        url = (os.getenv("MCP_SERVER_URL") or "").strip()
        if not url:
            raise MCPConfigError(
                "Defina MCP_SERVER_URL no arquivo .env com o endpoint do servidor MCP Brasil "
                "(por exemplo, https://seu-servidor/mcp ou http://localhost:8000/mcp)."
            )
        partes = urlparse(url)
        if partes.scheme not in ("http", "https") or not partes.netloc:
            raise MCPConfigError(f"MCP_SERVER_URL inválida: {url}")
        if partes.netloc.lower() in ("github.com", "www.github.com"):
            raise MCPConfigError(
                "MCP_SERVER_URL aponta para uma página do GitHub, que não é um endpoint MCP."
            )
        if partes.scheme == "http" and partes.hostname not in HOSTS_LOCAIS:
            raise MCPConfigError(
                "Para servidores remotos use HTTPS. HTTP só é aceito para localhost."
            )
        lista = os.getenv("MCP_FERRAMENTAS")
        ferramentas = (
            tuple(n.strip() for n in lista.split(",") if n.strip()) if lista else FERRAMENTAS_PADRAO
        )
        return cls(
            url=url,
            token=(os.getenv("MCP_AUTH_TOKEN") or "").strip() or None,
            ferramentas=ferramentas,
            timeout=float(os.getenv("MCP_TIMEOUT", "60")),
        )


@dataclass
class ClienteMCP:
    """Sessão com o servidor MCP Brasil. Use com `async with`."""

    config: ConfigMCP
    _client: Client | None = field(default=None, init=False)
    _http: httpx2.AsyncClient | None = field(default=None, init=False)
    ferramentas: list[Any] = field(default_factory=list, init=False)
    ausentes: list[str] = field(default_factory=list, init=False)
    total_no_servidor: int = field(default=0, init=False)

    async def __aenter__(self) -> "ClienteMCP":
        headers = {"Authorization": f"Bearer {self.config.token}"} if self.config.token else {}
        self._http = httpx2.AsyncClient(
            headers=headers, timeout=httpx2.Timeout(self.config.timeout, read=self.config.timeout)
        )
        transporte = streamable_http_client(self.config.url, http_client=self._http)
        self._client = Client(transporte, read_timeout_seconds=self.config.timeout)
        await self._client.__aenter__()
        await self._descobrir_ferramentas()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)
        if self._http is not None:
            await self._http.aclose()

    @property
    def nome_servidor(self) -> str:
        info = self._client.server_info if self._client else None
        return f"{info.name} {info.version}" if info else "desconhecido"

    async def _descobrir_ferramentas(self) -> None:
        """Lista todas as ferramentas do servidor (com paginação) e filtra as de saúde."""
        assert self._client is not None
        todas: list[Any] = []
        cursor: str | None = None
        while True:
            resp = await self._client.list_tools(cursor=cursor) if cursor else await self._client.list_tools()
            todas.extend(resp.tools)
            cursor = resp.next_cursor
            if not cursor:
                break
        self.total_no_servidor = len(todas)
        por_nome = {t.name: t for t in todas}
        self.ferramentas = [por_nome[n] for n in self.config.ferramentas if n in por_nome]
        self.ausentes = [n for n in self.config.ferramentas if n not in por_nome]
        if not self.ferramentas:
            raise MCPConfigError(
                "O servidor MCP respondeu, mas não expôs nenhuma ferramenta de saúde "
                f"({', '.join(self.config.ferramentas)}). Use o servidor_mcp/servidor_saude.py "
                "ou, no servidor completo, MCP_BRASIL_TOOL_SEARCH=none."
            )

    def ferramentas_para_llm(self) -> list[dict[str, Any]]:
        """Converte os esquemas descobertos para o formato de tools da API do Claude."""
        return [
            {
                "name": t.name,
                "description": (t.description or t.title or t.name)[:1024],
                "input_schema": t.input_schema or {"type": "object", "properties": {}},
            }
            for t in self.ferramentas
        ]

    async def chamar(self, nome: str, argumentos: dict[str, Any]) -> ResultadoFerramenta:
        assert self._client is not None
        permitidas = {t.name for t in self.ferramentas}
        if nome not in permitidas:
            return ResultadoFerramenta(nome, argumentos, f"Ferramenta não permitida: {nome}", True)
        try:
            r = await self._client.call_tool(nome, argumentos)
        except Exception as exc:  # erro de transporte ou de protocolo
            return ResultadoFerramenta(nome, argumentos, f"Falha ao chamar {nome}: {exc}", True)
        partes = [getattr(b, "text", None) for b in r.content]
        texto = "\n".join(p for p in partes if p) or "(resposta vazia)"
        return ResultadoFerramenta(nome, argumentos, texto, bool(r.is_error))
