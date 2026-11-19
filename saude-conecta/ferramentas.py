"""Lista única das ferramentas do MCP Brasil usadas pelo Saúde Conecta.

Usada pelo servidor (servidor_mcp/servidor_saude.py), que só expõe estas ferramentas,
e pelo cliente (mcp_client.py), que só as entrega ao modelo.
Os nomes foram conferidos em src/mcp_brasil/data/saude/server.py (prefixo "saude_" do namespace).
"""

FERRAMENTAS_SAUDE = (
    "saude_buscar_municipio_geocodigo",
    "saude_buscar_estabelecimentos",
    "saude_buscar_por_tipo",
    "saude_listar_tipos_estabelecimento",
    "saude_buscar_estabelecimento_por_cnes",
    "saude_buscar_por_coordenadas",
    "saude_resumo_rede_municipal",
    "saude_buscar_urgencias",
)
