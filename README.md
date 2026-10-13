# Mapeador — pesquisa de negócios alimentícios

O Mapeador pesquisa estabelecimentos do setor alimentício no Google Maps, reúne informações comerciais públicas e gera um relatório para avaliar oportunidades para a 4K Food Service e para a empresa de presença digital. Não cruza nem precisa do catálogo da 4K.

## O relatório mostra

- Nome, categoria, telefone, endereço, site e link do Google Maps, quando disponíveis.
- Instagram e outros canais digitais encontrados em links públicos.
- Link de cardápio/catálogo, quando identificado.
- Itens ou produtos que aparecem como texto em páginas públicas do cardápio/site.
- Plataformas e ferramentas digitais identificadas publicamente, como canais de pedidos, delivery e algumas plataformas de gestão.
- Uma avaliação preliminar de adequação à oferta de presença digital.
- Fontes consultadas e limitações da pesquisa.

**Importante:** a pesquisa só informa o que consegue observar publicamente. Se um sistema de gestão de vendas não aparece no site ou em outra fonte pública examinada, o relatório diz que não foi identificado — não afirma que a empresa não usa. Cardápios em imagens, PDFs ou conteúdo carregado por JavaScript podem não ser lidos corretamente.

## Instalação — Windows

1. Instale Python 3.11 ou 3.12 e Git.
2. Abra o PowerShell e execute, uma linha de cada vez:

```powershell
git clone https://github.com/iinteligenci/mapeador.git
cd mapeador
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

3. Abra o arquivo `.env` e configure sua chave da Gemini API. Você pode criar/gerenciar a chave pelo Google AI Studio.
4. Execute, por exemplo:

```powershell
python main.py --termo "restaurantes em Vila Velha ES" --limite 5
```

O relatório será salvo em `reports/` no formato Markdown. O banco SQLite fica em `data/`.

Se a ativação do ambiente for bloqueada, use `.venv\Scripts\python.exe` no lugar de `python`.

## macOS/Linux

```bash
git clone https://github.com/iinteligenci/mapeador.git
cd mapeador
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
# Configure GEMINI_API_KEY no .env
python main.py --termo "restaurantes em Vila Velha ES" --limite 5
```

## Configuração

O arquivo local `.env` deve conter:

```dotenv
GEMINI_API_KEY=sua_chave_real
GEMINI_MODEL=gemini-3.8-flash
DATABASE_PATH=data/mapeador.sqlite3
```

Nunca publique o arquivo `.env` nem compartilhe a chave. O projeto usa o SDK atual `google-genai`, recomendado pelo Google, em vez do SDK legado `google-generativeai`.

## Limitações e uso responsável

- Os seletores do Google Maps podem mudar; telefone/endereço/site podem não estar disponíveis.
- A coleta do Maps e a consulta de sites são experimentais. Não há tentativa de contornar CAPTCHA, login, bloqueios ou limites.
- Para uso comercial contínuo, considere a Google Maps Platform Places API e siga seus termos e cotas.
- O enriquecimento contínuo depende de a aplicação local permanecer aberta e de o estabelecimento ter um site público; examina até dois registros por ciclo de 30 minutos.
- CNPJ só é preenchido quando aparece explicitamente em páginas públicas examinadas. Não é uma consulta oficial de situação cadastral.
- A fila de campanhas prepara links wa.me com texto pré-preenchido; o envio é manual e requer revisão/autorizações adequadas. Não há disparo automático de mensagens.
- A pesquisa de canais e ferramentas limita-se às páginas públicas examinadas; não confirma sistemas internos de gestão.
- Itens do cardápio são extraídos de textos visíveis, não de imagens/PDFs; confirme no link de origem.
- A qualificação por IA é uma hipótese para revisão humana. Mensagens comerciais ficam como rascunhos; nada é enviado automaticamente.
- Respeite a LGPD, os termos das plataformas e pedidos para não receber contato.

## Interface web local

A interface roda no computador e separa a prospecção em duas etapas:

1. **Buscar estabelecimentos:** digite a categoria/termo e a localidade (por exemplo, bares, restaurantes, açougues, padarias ou peixarias em uma cidade). A busca não chama a IA. Ela consulta resultados além dos que já estão no histórico e mostra apenas novos estabelecimentos.
2. **Gerar proposta por estabelecimento:** no cartão do negócio, escolha 4K Food Service, Presença digital ou ambas, personalize a oferta se quiser e clique em “Gerar proposta”. A consulta complementar ao site e a chamada ao Gemini acontecem só nesse momento.
3. **Campanhas:** abra “Campanhas”, escolha 4K Food Service ou Presença Digital e escreva a mensagem. A lista de contatos públicos fica preparada e cada conversa pode ser aberta no WhatsApp com o texto preenchido; o envio é manual, após confirmação de que há autorização apropriada. Você também pode preencher “Termo para continuar prospectando” (ex.: restaurantes em Vila Velha ES). Enquanto o app local estiver rodando, ele pesquisa até três novos estabelecimentos a cada 30 minutos e os adiciona à fila para revisão. O sistema não dispara mensagens em massa nem envia sem revisão.
4. **Pesquisa contínua:** enquanto `py web_app.py` estiver rodando, um processo local revisa até dois cadastros por ciclo (a cada 30 minutos) que tenham site, procurando contatos comerciais e CNPJ explicitamente publicados. O processo respeita limites modestos, não contorna bloqueios e não garante que toda empresa publique esses dados. Se uma campanha tiver termo de prospecção, a mesma rotina também tenta encontrar até três novos estabelecimentos por ciclo e adicioná-los à fila da campanha; isso prepara contatos, não envia mensagens.
5. **Encontrar responsável e contatos públicos:** em cada estabelecimento, clique em “Encontrar responsável e contatos públicos”. O Mapeador examina até seis páginas públicas do site da própria empresa à procura de nomes/cargos explicitamente publicados, telefone comercial e link de WhatsApp. O resultado é salvo no histórico com fonte e indicação de confiança. Não adivinha números nem atribui um telefone comercial ao dono sem evidência.
6. **Estabelecimentos encontrados:** a aba guarda todos os negócios já descobertos e permite organizar a etapa comercial: para visitar, visitado ou cliente.

Para iniciar no Windows, atualize com GitHub Desktop (Fetch origin e Pull origin), instale as dependências com `py -m pip install -r requirements.txt` e execute `py web_app.py`. Abra `http://127.0.0.1:5000`. O banco SQLite fica em `data/`; não o apague ao atualizar o código.

A busca depende do carregamento de resultados do Google Maps e pode encontrar menos negócios que o solicitado se o Maps não apresentar mais resultados. A aplicação não contorna bloqueios e não envia mensagens automaticamente.
