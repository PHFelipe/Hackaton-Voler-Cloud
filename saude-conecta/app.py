"""Interface Streamlit do Saúde Conecta."""

from __future__ import annotations

import asyncio
import html

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import AgenteSaudeConecta, ErroModelo, EstadoConversa, Evento  # noqa: E402
from mcp_client import ClienteMCP, ConfigMCP, MCPConfigError  # noqa: E402

st.set_page_config(page_title="Saúde Conecta", page_icon="🩺", layout="centered")

EXEMPLOS = [
    "Onde encontro atendimento com cardiologista pelo SUS em Campina Grande?",
    "Quais unidades oferecem fisioterapia em João Pessoa?",
    "Onde posso procurar atendimento psicológico na rede pública?",
    "Existe alguma unidade especializada em atendimento infantil?",
]

st.markdown(
    """
<style>
:root { --azul:#0b5394; --azul-claro:#e8f1fb; --verde:#1e8e5a; --verde-claro:#e7f6ee; }
.block-container { padding-top: 1.5rem; max-width: 860px; }
.sc-header { background: linear-gradient(135deg, var(--azul) 0%, #1a73c9 60%, var(--verde) 100%);
  color: #fff; border-radius: 18px; padding: 22px 26px; margin-bottom: 18px; }
.sc-header h1 { color:#fff; font-size: 1.9rem; margin: 0; }
.sc-header p { margin: 4px 0 0; opacity: .92; font-size: 1.02rem; }
.sc-card { border: 1px solid #d6e4f2; border-left: 5px solid var(--verde); border-radius: 12px;
  padding: 14px 16px; margin: 10px 0 4px; background: #fff; }
.sc-card h4 { margin: 0 0 4px; color: var(--azul); font-size: 1.05rem; }
.sc-tag { display:inline-block; background: var(--azul-claro); color: var(--azul); border-radius: 999px;
  padding: 2px 10px; font-size: .78rem; margin-right: 6px; }
.sc-linha { margin: 3px 0; font-size: .92rem; color: #233; }
.sc-rel { background: var(--verde-claro); border-radius: 8px; padding: 6px 10px; margin-top: 8px; font-size: .88rem; }
.sc-nc { color: #8a5a00; font-size: .84rem; margin-top: 6px; }
.sc-aviso { font-size: .82rem; color: #556; border-top: 1px dashed #c9d6e3; margin-top: 8px; padding-top: 6px; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sc-header"><h1>🩺 Saúde Conecta</h1>'
    "<p>Encontre serviços de saúde pública com mais facilidade.</p></div>",
    unsafe_allow_html=True,
)


def novo_estado() -> None:
    st.session_state.estado = EstadoConversa()
    st.session_state.exibicao = []
    st.session_state.pendente = None


if "estado" not in st.session_state:
    novo_estado()


def esc(v: object) -> str:
    return html.escape(str(v))


def render_cartao(c: dict, chave: str) -> None:
    linhas = []
    if c.get("endereco"):
        end = c["endereco"] + (f" — {c['bairro']}" if c.get("bairro") else "")
        linhas.append(f"📍 {esc(end)}")
    local = " / ".join(x for x in (c.get("municipio"), c.get("uf")) if x)
    if local:
        linhas.append(f"🏙️ {esc(local)}")
    if c.get("telefone"):
        linhas.append(f"📞 {esc(c['telefone'])}")
    if c.get("gestao"):
        linhas.append(f"🏛️ Gestão: {esc(c['gestao'])}")
    if c.get("atualizado_em"):
        linhas.append(f"🗓️ Cadastro atualizado em {esc(c['atualizado_em'])}")
    tags = f'<span class="sc-tag">CNES {esc(c["cnes"])}</span>'
    if c.get("tipo"):
        tags += f'<span class="sc-tag">{esc(c["tipo"])}</span>'
    nc = c.get("nao_confirmado")
    faltando = c.get("campos_nao_conferidos") or []
    st.markdown(
        f'<div class="sc-card"><h4>{esc(c["nome"])}</h4>{tags}'
        + "".join(f'<div class="sc-linha">{l}</div>' for l in linhas)
        + (f'<div class="sc-rel">✅ {esc(c["relevancia"])}</div>' if c.get("relevancia") else "")
        + (f'<div class="sc-nc">⚠️ Não confirmado: {esc(nc)}</div>' if nc else "")
        + (
            f'<div class="sc-nc">Campos omitidos por não conferirem com o CNES: {esc(", ".join(faltando))}</div>'
            if faltando else ""
        )
        + '<div class="sc-aviso">Dados cadastrais do CNES/DataSUS. Confirme o atendimento com a unidade '
        "ou com a Secretaria Municipal de Saúde antes de se deslocar.</div></div>",
        unsafe_allow_html=True,
    )
    if st.button("Ver detalhes desta unidade", key=chave):
        st.session_state.pendente = (
            f"Quero saber mais sobre a unidade {c['nome']} (CNES {c['cnes']})."
        )
        st.rerun()


def render_resultados(item: dict, idx: int) -> None:
    cartoes = item.get("cartoes") or []
    for j, c in enumerate(cartoes):
        render_cartao(c, f"det-{idx}-{j}")
    if len(cartoes) > 1:
        with st.expander("Comparar unidades"):
            st.dataframe(
                [
                    {
                        "Nome": c.get("nome"), "CNES": c.get("cnes"), "Tipo": c.get("tipo", "—"),
                        "Endereço": c.get("endereco", "—"), "Telefone": c.get("telefone", "—"),
                        "Gestão": c.get("gestao", "—"),
                    }
                    for c in cartoes
                ],
                hide_index=True,
                use_container_width=True,
            )
    com_coord = [c for c in cartoes if "latitude" in c and "longitude" in c]
    if com_coord:
        with st.expander(f"Ver no mapa ({len(com_coord)} com coordenadas no CNES)"):
            st.map([{"lat": c["latitude"], "lon": c["longitude"]} for c in com_coord])
    if item.get("descartados"):
        st.caption(
            "Unidades omitidas por não constarem nas respostas do servidor: "
            + ", ".join(item["descartados"])
        )
    if item.get("chamadas"):
        with st.expander("Consultas realizadas ao MCP Saúde"):
            for ch in item["chamadas"]:
                st.markdown(f"**{ch['nome']}** `{ch['args']}` {'❌ erro' if ch['erro'] else '✔️'}")


with st.sidebar:
    st.subheader("Conversa")
    if st.button("🆕 Nova conversa", use_container_width=True):
        novo_estado()
        st.rerun()
    st.subheader("Servidor MCP")
    try:
        cfg = ConfigMCP.do_ambiente()
        st.caption(f"Endpoint: `{cfg.url}`")
    except MCPConfigError as e:
        cfg = None
        st.error(str(e))
    st.caption(
        "Fonte: CNES/DataSUS via MCP Brasil. As informações são cadastrais e podem estar "
        "desatualizadas. Em emergência, ligue 192 (SAMU)."
    )
    st.subheader("Privacidade")
    st.caption(
        "O servidor MCP roda no seu computador. Suas mensagens, porém, são enviadas à API do "
        "modelo de linguagem (Groq, por padrão) para serem interpretadas. Não digite nome, CPF, "
        "diagnósticos ou outros dados pessoais: basta dizer o serviço e a cidade."
    )

for i, item in enumerate(st.session_state.exibicao):
    with st.chat_message(item["role"], avatar="🙂" if item["role"] == "user" else "🩺"):
        st.markdown(item["texto"])
        if item["role"] == "assistant":
            render_resultados(item, i)

if not st.session_state.exibicao:
    st.markdown("**Experimente perguntar:**")
    cols = st.columns(2)
    for k, ex in enumerate(EXEMPLOS):
        if cols[k % 2].button(ex, key=f"ex-{k}", use_container_width=True):
            st.session_state.pendente = ex
            st.rerun()

digitado = st.chat_input("Descreva o atendimento que procura e a cidade…")
pergunta = digitado or st.session_state.pendente
st.session_state.pendente = None


def causa_raiz(e: BaseException) -> BaseException:
    """O cliente MCP roda em um TaskGroup, que embrulha erros em ExceptionGroup."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


async def executar(pergunta: str, ao_evento) -> object:
    agente = AgenteSaudeConecta()
    async with ClienteMCP(cfg) as mcp:
        return await agente.responder(st.session_state.estado, pergunta, mcp, ao_evento)


if pergunta:
    st.session_state.exibicao.append({"role": "user", "texto": pergunta})
    with st.chat_message("user", avatar="🙂"):
        st.markdown(pergunta)
    with st.chat_message("assistant", avatar="🩺"):
        estado = st.session_state.estado
        tamanho_antes = len(estado.mensagens)
        item = {"role": "assistant", "texto": ""}
        with st.status("Consultando a rede de saúde no MCP Brasil…", expanded=False) as status:
            def ao_evento(ev: Evento) -> None:
                status.write(("⚠️ " if ev.tipo == "aviso" else "🔎 ") + ev.mensagem)
            try:
                if cfg is None:
                    raise MCPConfigError("Servidor MCP não configurado. Veja a barra lateral.")
                try:
                    r = asyncio.run(executar(pergunta, ao_evento))
                except BaseExceptionGroup as grupo:
                    raise causa_raiz(grupo) from grupo
                item.update(
                    texto=r.texto or "(sem resposta)",
                    cartoes=r.cartoes,
                    descartados=r.descartados,
                    chamadas=[{"nome": c.nome, "args": c.argumentos, "erro": c.erro} for c in r.chamadas],
                )
                status.update(label="Consulta concluída", state="complete")
            except MCPConfigError as e:
                del estado.mensagens[tamanho_antes:]
                item["texto"] = f"⚠️ {e}"
                status.update(label="Configuração do MCP", state="error")
            except ErroModelo as e:
                del estado.mensagens[tamanho_antes:]
                item["texto"] = f"⚠️ {e}"
                status.update(label="Erro no modelo", state="error")
            except Exception as e:  # conexão com o servidor MCP, rede etc.
                del estado.mensagens[tamanho_antes:]
                item["texto"] = (
                    "⚠️ Não consegui me conectar ao servidor MCP Brasil. Verifique se ele está no ar "
                    f"e se MCP_SERVER_URL está correto.\n\nDetalhe: `{type(e).__name__}: {e}`"
                )
                status.update(label="Servidor MCP indisponível", state="error")
        st.session_state.exibicao.append(item)
        st.rerun()
