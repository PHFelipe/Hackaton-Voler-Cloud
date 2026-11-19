"""Roda os 5 cenários obrigatórios contra o servidor MCP Brasil real e o modelo real.

Uso:  python testar_cenarios.py            (todos)
      python testar_cenarios.py 3          (só o cenário 3)

Grava o relatório em resultados_testes.md. Cada execução faz chamadas reais
(e cobradas) à API do modelo configurado no .env.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from agent import AgenteSaudeConecta, ErroModelo, EstadoConversa  # noqa: E402
from mcp_client import ClienteMCP, ConfigMCP  # noqa: E402

# Cada cenário é uma conversa; o 5 continua a conversa do 1.
CENARIOS = {
    1: ["Quero encontrar atendimento odontológico pelo SUS em Campina Grande."],
    2: ["Preciso encontrar atendimento neurológico infantil em Campina Grande."],
    3: ["Onde posso fazer fisioterapia?"],
    4: ["Quero encontrar atendimento de medicina hiperbárica em Cabaceiras, na Paraíba."],
    5: [
        "Quero encontrar atendimento odontológico pelo SUS em Campina Grande.",
        "Quero saber mais sobre essa unidade.",
    ],
}


def checar(n: int, respostas: list) -> list[str]:
    ult = respostas[-1]
    nomes = [c.nome for c in ult.chamadas]
    texto = ult.texto.lower()
    checks: list[tuple[str, bool]] = [
        ("orienta a confirmar antes de se deslocar", "confirm" in texto or n == 3),
        ("nenhum cartão descartado por falta de evidência", not ult.descartados),
    ]
    if n in (1, 2):
        checks.append(("consultou o CNES via MCP", any(x.startswith("saude_buscar") for x in nomes)))
    if n == 3:
        checks.append(("perguntou o local sem consultar o MCP", not nomes and ("munic" in texto or "cidade" in texto)))
    if n == 4:
        checks.append(("declarou ausência de resultado compatível", "não" in texto and ("encontr" in texto or "localiz" in texto)))
    if n == 5:
        checks.append(("detalhou pelo CNES", "saude_buscar_estabelecimento_por_cnes" in nomes))
    return [f"- {'✅' if ok else '❌'} {nome}" for nome, ok in checks]


async def rodar(selecionados: list[int]) -> None:
    cfg = ConfigMCP.do_ambiente()
    agente = AgenteSaudeConecta()
    linhas = [f"# Resultados dos testes — {datetime.now():%d/%m/%Y %H:%M}",
              f"Servidor MCP: {cfg.url} · Provedor: {agente.provedor} · Modelo: {agente.modelo} (esforço {agente.esforco})", ""]
    async with ClienteMCP(cfg) as mcp:
        linhas.append(f"Servidor: {mcp.nome_servidor} · {mcp.total_no_servidor} ferramentas no total · "
                      f"usadas: {', '.join(t.name for t in mcp.ferramentas)}")
        if mcp.ausentes:
            linhas.append(f"Ausentes no servidor: {', '.join(mcp.ausentes)}")
        for n in selecionados:
            estado = EstadoConversa()
            respostas = []
            linhas += ["", f"## Cenário {n}"]
            for pergunta in CENARIOS[n]:
                print(f"[{n}] {pergunta}")
                r = await agente.responder(estado, pergunta, mcp)
                respostas.append(r)
                linhas += ["", f"**Usuário:** {pergunta}", "", "**Ferramentas chamadas:**"]
                linhas += [f"- `{c.nome}` {c.argumentos} {'(erro: ' + c.texto[:150] + ')' if c.erro else ''}"
                           for c in r.chamadas] or ["- nenhuma"]
                linhas += ["", f"**Cartões:** {len(r.cartoes)} verificados, {len(r.descartados)} descartados"]
                linhas += [f"- {c['nome']} (CNES {c['cnes']})" for c in r.cartoes]
                linhas += ["", "**Resposta:**", "", r.texto]
            linhas += ["", "**Verificações automáticas:**"] + checar(n, respostas)
    with open("resultados_testes.md", "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print("\n".join(linhas))


if __name__ == "__main__":
    escolhidos = [int(a) for a in sys.argv[1:]] or sorted(CENARIOS)
    try:
        asyncio.run(rodar(escolhidos))
    except BaseException as erro:  # o cliente MCP embrulha erros em ExceptionGroup
        while isinstance(erro, BaseExceptionGroup) and erro.exceptions:
            erro = erro.exceptions[0]
        if isinstance(erro, KeyboardInterrupt):
            raise SystemExit(1)
        if isinstance(erro, ErroModelo):
            raise SystemExit(str(erro))
        raise SystemExit(f"Falha nos testes: {type(erro).__name__}: {erro}")
