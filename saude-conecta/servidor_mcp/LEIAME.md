# Servidor MCP Brasil (cópia local)

Esta pasta contém o código-fonte do servidor **MCP Brasil**, sem modificações, para que ele rode
inteiro na sua máquina. O `run.py` instala esta cópia no ambiente virtual `.venv` em vez de baixá-la do PyPI.

| Item | Valor |
|---|---|
| Projeto | https://github.com/Mcp-Brasil/mcp-brasil |
| Versão | 0.14.0 (fixada) |
| Origem | pacote de código-fonte `mcp_brasil-0.14.0.tar.gz` publicado no PyPI |
| SHA-256 do pacote original | `b8ea99d92de1aee9a5ce83df5bb47b664cd2389d7f946b806191dd2f71df5376` |
| Licença | MIT (arquivo `LICENSE`); escopo e avisos em `NOTICE`, `SOURCES.md` e `ACCEPTABLE_USE.md` |

O que foi retirado do pacote original, por não ser necessário para rodar: a pasta de testes,
a documentação, o Dockerfile e o `uv.lock`. Nenhum arquivo de código foi alterado.
`NOTICE`, `SOURCES.md` e `ACCEPTABLE_USE.md` não vêm no pacote do PyPI e foram copiados do repositório oficial.

As bibliotecas das quais o servidor depende (FastMCP, httpx, pydantic etc.) continuam sendo
instaladas pelo `pip` na primeira execução.

Para atualizar a versão: baixe o novo pacote de código-fonte do PyPI, substitua esta pasta e ajuste
o caminho em `requirements.txt`.

## Só as ferramentas usadas

O `servidor_saude.py` sobe o servidor importando apenas o módulo de saúde original
(`mcp_brasil.data.saude`), com o mesmo namespace e o mesmo ciclo de vida HTTP do servidor completo.
Ficam visíveis só as 8 ferramentas listadas em `../ferramentas.py`; recursos e prompts do módulo ficam ocultos,
e os outros 50+ módulos do MCP Brasil nem são carregados. Nenhuma ferramenta foi reescrita.
