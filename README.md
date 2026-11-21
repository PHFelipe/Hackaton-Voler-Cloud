Saúde Conecta
Agente conversacional que ajuda o cidadão a localizar estabelecimentos da rede pública de saúde. Ele entende o pedido em linguagem natural, consulta o CNES/DataSUS pelo servidor externo MCP Brasil e mostra as unidades encontradas em cartões, sempre com dados reais e com o aviso para confirmar o atendimento antes de se deslocar.

Usuário → Streamlit (app.py) → Agente com tool calling, Groq ou Claude (agent.py)
        → Cliente MCP Streamable HTTP (mcp_client.py) → Servidor MCP Brasil → CNES/DataSUS
O que foi verificado no MCP Brasil
Conferido no repositório Mcp-Brasil/mcp-brasil (pacote mcp-brasil 0.14.0, FastMCP) em 19/11/2026:

Não existe endpoint HTTPS público. A documentação só mostra https://<seu-fqdn>/mcp como modelo para quem implanta o próprio servidor (guia de Azure com OAuth em docs/deploy/). Para HTTP, o README indica rodar o servidor localmente, que fica em http://localhost:8000/mcp.
O transporte é Streamable HTTP, no caminho /mcp. O cliente deste projeto usa o streamable_http_client do MCP Python SDK.
O servidor completo carrega 317 ferramentas de mais de 50 módulos e não tem opção para escolher módulos. Por isso o projeto sobe o servidor com servidor_mcp/servidor_saude.py: ele importa só o módulo de saúde original, sem alterar nada, e deixa visíveis apenas as 8 ferramentas que o agente usa (listadas em ferramentas.py). Qualquer outra ferramenta é recusada pelo servidor.
As seis ferramentas prioritárias existem com esses nomes. O agente também usa saude_buscar_municipio_geocodigo (para obter o código IBGE do município) e saude_buscar_urgencias. Os esquemas são lidos do servidor em tempo de execução.
Limites dos dados: as ferramentas do CNES filtram só por município, UF e tipo de estabelecimento. Não há filtro por especialidade, serviço, faixa etária ou atendimento SUS, e o endpoint de profissionais foi descontinuado. Por isso o agente aproxima a especialidade pelo tipo de estabelecimento e diz explicitamente o que não pode confirmar.
As ferramentas do CNES usam o código IBGE de 6 dígitos (ex.: 250400 para Campina Grande), enquanto a busca de município devolve 7 dígitos (2504009). O prompt do agente trata essa conversão.
Como rodar (um comando)
Requer Python 3.11 ou mais novo (python.org; no Windows, marque "Add python.exe to PATH" na instalação).

Descompacte a pasta.
Rode o inicializador:
Windows: clique duas vezes em iniciar.bat
Linux/macOS: ./iniciar.sh (ou python3 run.py)
Na primeira vez, cole a sua chave da Groq quando for pedida (crie em https://console.groq.com/keys). Ela fica salva no .env.
O run.py faz o resto sozinho: cria o ambiente virtual .venv, instala as dependências e o servidor MCP Brasil a partir da cópia que vem na pasta servidor_mcp/, sobe o servidor MCP em http://127.0.0.1:8000/mcp só com as 8 ferramentas de saúde que o agente usa, abre o chatbot em http://localhost:8501 e desliga o servidor quando você fecha com Ctrl+C. A primeira execução demora alguns minutos por causa da instalação; as seguintes abrem em segundos. O log do servidor fica em logs/mcp-server.log.

Rodar os 5 cenários de teste
Windows: iniciar.bat testes
Linux/macOS: ./iniciar.sh testes (ou ./iniciar.sh testes 2 5 para alguns)
O resultado vai para resultados_testes.md, com as ferramentas MCP chamadas, os cartões, as respostas e verificações automáticas (por exemplo, no cenário 3 o agente não pode consultar o MCP antes de perguntar a cidade; no 5 ele precisa chamar saude_buscar_estabelecimento_por_cnes). Cada execução consome a sua cota da API do modelo.

Usar um servidor MCP Brasil remoto
Se você tiver uma implantação HTTPS do MCP Brasil, coloque a URL em MCP_SERVER_URL no .env (terminando em /mcp) e, se ela exigir, o token em MCP_AUTH_TOKEN. Nesse caso o run.py não sobe o servidor local. O cliente recusa HTTP para hosts que não sejam localhost e recusa URLs do GitHub.

Privacidade e LGPD: o que fica na sua máquina e o que sai
O servidor MCP Brasil vem dentro desta pasta (servidor_mcp/, versão 0.14.0, licença MIT; detalhes em servidor_mcp/LEIAME.md) e roda no seu computador, assim como o chatbot. Nenhum dos dois manda dados para um servidor intermediário nosso ou do projeto MCP Brasil.

O quê	Para onde vai	O que é enviado
Chatbot (Streamlit) e servidor MCP	Ficam no seu computador, acessíveis só por localhost	Nada sai daqui
Consultas ao CNES	API pública do Ministério da Saúde (apidadosabertos.saude.gov.br)	Só código do município, código do tipo de unidade ou código CNES. Nenhum dado do usuário
Interpretação das mensagens	API da Groq (ou da Anthropic, se escolhida), fora do Brasil	O texto que o usuário digita e os resultados das consultas ao CNES
Instalação (só na primeira vez)	PyPI	Download das bibliotecas
Ou seja: o único ponto em que algo que o usuário escreve sai da máquina é o modelo de linguagem. Por isso a interface avisa para não digitar nome, CPF ou diagnósticos, e o agente é instruído a não repetir dados pessoais. Se o projeto for usado com pacientes reais, avalie com quem cuida da LGPD na sua instituição o contrato e a política de dados do provedor do modelo, ou troque por um modelo que rode localmente.

O Streamlit está configurado para não enviar estatísticas de uso e para aceitar conexões só de localhost.

Como o agente evita inventar dados
O prompt de sistema (prompts/system_prompt.txt) proíbe afirmar especialidade, público infantil, atendimento SUS ou vagas sem evidência, e explica os limites do CNES.
Os cartões só são exibidos depois de uma checagem no código: cada CNES, nome, endereço, telefone e coordenada precisa aparecer literalmente nas respostas do servidor MCP naquela conversa. Unidades que não conferem são descartadas e campos que não conferem são omitidos, com aviso na tela.
O mapa só aparece quando o detalhe do CNES traz coordenadas.
Cada resposta mostra quais ferramentas MCP foram chamadas.
Arquivos
Arquivo	Função
app.py	Interface Streamlit: cabeçalho, chat, exemplos, indicador de consulta, cartões, comparação, mapa, nova conversa
agent.py	Laço de tool calling (Groq ou Claude), histórico da conversa e verificação dos cartões
mcp_client.py	Conexão Streamable HTTP, descoberta das ferramentas (tools/list) e execução (tools/call)
prompts/system_prompt.txt	Regras de comportamento e segurança
run.py, iniciar.bat, iniciar.sh	Inicializador: instala, sobe o servidor MCP e abre o chatbot
testar_cenarios.py	Os 5 cenários obrigatórios
servidor_mcp/	Código-fonte do servidor MCP Brasil 0.14.0 (MIT), sem modificações, e servidor_saude.py, que o sobe só com as ferramentas usadas
ferramentas.py	Lista única das ferramentas usadas, lida pelo servidor e pelo cliente
.streamlit/config.toml	Tema azul e branco e execução só em localhost
.env.example	Variáveis de ambiente
Configuração do modelo
O provedor é escolhido no .env com LLM_PROVIDER:

groq (padrão): usa a API da Groq com o modelo openai/gpt-oss-120b, que a documentação de tool use da Groq usa nos exemplos de chamada de ferramentas locais e que está entre os modelos de produção. A chave fica em GROQ_API_KEY. Para trocar de modelo, defina LLM_MODEL (por exemplo llama-3.3-70b-versatile). LLM_EFFORT controla o raciocínio dos modelos gpt-oss (low, medium, high).
anthropic: usa a API do Claude, com claude-opus-5-5 como padrão. A chave fica em ANTHROPIC_API_KEY.
O inicializador pede a chave do provedor escolhido. Nenhuma chave vem no código nem no zip.
