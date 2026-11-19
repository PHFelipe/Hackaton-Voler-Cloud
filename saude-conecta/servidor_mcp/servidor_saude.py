"""Sobe o servidor MCP Brasil só com as ferramentas de saúde usadas pelo Saúde Conecta.

O mcp-brasil original (mcp_brasil/server.py) carrega todos os seus 50+ módulos e 317 ferramentas
e não tem opção para escolher módulos. Este arquivo não altera nem reescreve nenhuma ferramenta:
ele importa apenas o módulo de saúde original (mcp_brasil.data.saude), monta-o com o mesmo
namespace "saude" e o mesmo ciclo de vida HTTP usados pelo servidor completo, e deixa visíveis
somente as ferramentas listadas em ferramentas.py. Os demais módulos nem são importados.

Uso:  python servidor_mcp/servidor_saude.py [porta]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastmcp import FastMCP
from mcp_brasil._shared.lifespan import http_lifespan
from mcp_brasil.data.saude.server import mcp as modulo_saude

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ferramentas import FERRAMENTAS_SAUDE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

servidor = FastMCP("mcp-brasil-saude (Saúde Conecta)", lifespan=http_lifespan)
servidor.mount(modulo_saude, namespace="saude")
# Só as ferramentas usadas; recursos e prompts do módulo também ficam ocultos.
servidor.enable(names=set(FERRAMENTAS_SAUDE), components={"tool"}, only=True)
servidor.disable(components={"resource", "template", "prompt"})

if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    servidor.run(transport="streamable-http", host="127.0.0.1", port=porta)
