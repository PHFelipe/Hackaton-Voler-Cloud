"""Inicializador único do Saúde Conecta.

    python run.py            instala o que faltar, sobe o servidor MCP Brasil e abre o chatbot
    python run.py testes     faz o mesmo, mas roda os 5 cenários de teste em vez do chatbot
    python run.py testes 3   só o cenário 3

Na primeira execução ele cria o ambiente virtual (.venv), instala as dependências
e pede a chave da API do provedor escolhido (Groq por padrão), que fica salva no .env.
Usa apenas a biblioteca padrão do Python, então roda com qualquer Python 3.11+.
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
REQS = RAIZ / "requirements.txt"
ENV = RAIZ / ".env"
ENV_EXEMPLO = RAIZ / ".env.example"
MARCA = VENV / ".requirements.sha256"
LOGS = RAIZ / "logs"
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
CHAVE_FALSA = {"", "sua-chave-aqui"}


def falar(msg: str) -> None:
    print(f"[Saúde Conecta] {msg}", flush=True)


def python_do_venv() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ---------------------------------------------------------------- instalação

def preparar_venv() -> None:
    if not python_do_venv().exists():
        falar("Criando o ambiente virtual em .venv (só na primeira vez)...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    hash_atual = hashlib.sha256(REQS.read_bytes()).hexdigest()
    if MARCA.exists() and MARCA.read_text().strip() == hash_atual:
        return
    falar("Instalando as dependências. Isso pode levar alguns minutos na primeira vez...")
    py = str(python_do_venv())
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    subprocess.check_call([py, "-m", "pip", "install", "-r", str(REQS), "-q"])
    MARCA.write_text(hash_atual)
    falar("Dependências instaladas.")


# ---------------------------------------------------------------- .env

def ler_env() -> dict[str, str]:
    valores: dict[str, str] = {}
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def gravar_chave(nome_var: str, chave: str) -> None:
    linhas = ENV.read_text(encoding="utf-8").splitlines()
    for i, linha in enumerate(linhas):
        if linha.strip().startswith(f"{nome_var}="):
            linhas[i] = f"{nome_var}={chave}"
            break
    else:
        linhas.insert(0, f"{nome_var}={chave}")
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")


CHAVES = {
    "groq": ("GROQ_API_KEY", "Groq", "https://console.groq.com/keys"),
    "anthropic": ("ANTHROPIC_API_KEY", "Claude (Anthropic)", "https://console.anthropic.com"),
}


def preparar_env() -> dict[str, str]:
    if not ENV.exists():
        ENV.write_text(ENV_EXEMPLO.read_text(encoding="utf-8"), encoding="utf-8")
        falar("Arquivo .env criado a partir do .env.example.")
    valores = ler_env()
    provedor = (valores.get("LLM_PROVIDER") or "groq").strip().lower()
    if provedor not in CHAVES:
        sys.exit(f"LLM_PROVIDER inválido no .env: {provedor}. Use groq ou anthropic.")
    nome_var, nome_servico, site = CHAVES[provedor]
    chave = valores.get(nome_var) or os.environ.get(nome_var, "")
    if chave in CHAVE_FALSA:
        if not sys.stdin.isatty():
            sys.exit(f"Coloque sua {nome_var} no arquivo .env e rode de novo.")
        print()
        print(f"Falta a chave da API da {nome_servico} (crie uma em {site}).")
        chave = input("Cole a chave aqui e tecle Enter: ").strip()
        if chave in CHAVE_FALSA:
            sys.exit(f"Nenhuma chave informada. Coloque {nome_var} no .env e rode de novo.")
        gravar_chave(nome_var, chave)
        falar("Chave salva no .env.")
        valores = ler_env()
    return valores


# ---------------------------------------------------------------- servidor MCP

def porta_livre(preferida: int) -> int:
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", preferida)) != 0:
            return preferida
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_porta(porta: int, processo: subprocess.Popen, limite: float = 120) -> bool:
    fim = time.time() + limite
    while time.time() < fim:
        if processo.poll() is not None:
            return False
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.5)
    return False


def subir_servidor_mcp(porta: int) -> subprocess.Popen:
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / "mcp-server.log", "w", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    falar(f"Iniciando o servidor MCP Brasil (só as ferramentas de saúde usadas) em http://127.0.0.1:{porta}/mcp ...")
    script = str(RAIZ / "servidor_mcp" / "servidor_saude.py")
    proc = subprocess.Popen([str(python_do_venv()), script, str(porta)], cwd=RAIZ, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    if not esperar_porta(porta, proc):
        proc.terminate()
        sys.exit(f"O servidor MCP não subiu. Veja o log em {LOGS / 'mcp-server.log'}")
    falar("Servidor MCP Brasil no ar.")
    return proc


def precisa_servidor_local(valores: dict[str, str]) -> bool:
    url = valores.get("MCP_SERVER_URL", "")
    return not url or urlparse(url).hostname in HOSTS_LOCAIS


# ---------------------------------------------------------------- principal

def main() -> None:
    if sys.version_info < (3, 11):
        sys.exit("O Saúde Conecta precisa do Python 3.11 ou mais novo.")
    os.chdir(RAIZ)
    preparar_venv()
    valores = preparar_env()

    env = dict(os.environ)
    servidor = None
    if precisa_servidor_local(valores):
        porta = porta_livre(int(urlparse(valores.get("MCP_SERVER_URL") or "http://x:8000").port or 8000))
        servidor = subir_servidor_mcp(porta)
        env["MCP_SERVER_URL"] = f"http://127.0.0.1:{porta}/mcp"
    else:
        falar(f"Usando o servidor MCP remoto: {valores['MCP_SERVER_URL']}")

    py = str(python_do_venv())
    args = sys.argv[1:]
    if args and args[0] == "testes":
        comando = [py, "testar_cenarios.py", *args[1:]]
    else:
        falar("Abrindo o chatbot em http://localhost:8501 (Ctrl+C para encerrar).")
        comando = [py, "-m", "streamlit", "run", "app.py", "--server.port", "8501"]
    processo = None
    try:
        processo = subprocess.Popen(comando, cwd=RAIZ, env=env)
        if comando[1] == "-m" and esperar_porta(8501, processo, limite=60):
            webbrowser.open("http://localhost:8501")
        codigo = processo.wait()
    except KeyboardInterrupt:
        if processo is not None:
            processo.terminate()
        codigo = 0
    finally:
        if servidor is not None:
            servidor.terminate()
            try:
                servidor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                servidor.kill()
            falar("Servidor MCP encerrado.")
    sys.exit(codigo)


if __name__ == "__main__":
    main()
