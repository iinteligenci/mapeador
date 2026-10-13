# Mapeador — Agente de Prospecção com Google Maps e IA

Base inicial em Python para pesquisar empresas, organizar informações públicas e preparar mensagens comerciais personalizadas com Gemini. O módulo de envio é **somente uma simulação**: nenhuma mensagem é enviada.

## Arquitetura

- `scraper/maps_scraper.py`: pesquisa um termo no Google Maps com Playwright e tenta extrair nome, link e categoria.
- `ai_agent/analyzer.py`: usa o Gemini para criar um rascunho de abordagem B2B.
- `outreach/sender.py`: exibe a mensagem e marca a ação como simulada.
- `main.py`: coordena pesquisa, geração e exibição dos resultados.

## Requisitos

- Python 3.10 ou superior
- Chave de API do Gemini, obtida no Google AI Studio
- Chromium instalado pelo Playwright

## Instalação

Linux/macOS:

```bash
git clone https://github.com/iinteligenci/mapeador.git
cd mapeador
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Windows PowerShell:

```powershell
git clone https://github.com/iinteligenci/mapeador.git
cd mapeador
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Edite o arquivo `.env` e substitua `cole_sua_chave_aqui` por sua chave real. **Nunca publique o arquivo `.env` nem inclua a chave no código ou no GitHub.**

## Executar

```bash
python main.py --termo "pizzarias em Vila Velha ES" --limite 10 --oferta "apresentar nosso serviço de presença digital"
```

Opções disponíveis:

- `--termo`: pesquisa a ser feita (padrão: restaurantes em Vitória ES).
- `--limite`: máximo de empresas a processar (padrão: 5).
- `--oferta`: contexto da abordagem comercial.
- `--verbose`: logs detalhados.

## Limitações e uso responsável

A estrutura e os seletores do Google Maps podem mudar; resultados podem vir vazios ou incompletos. O projeto não tenta contornar CAPTCHA, login ou bloqueios. Antes de automatizar coleta em produção, confira os termos e políticas aplicáveis do Google. Para aplicações comerciais robustas, considere a Google Maps Platform Places API, respeitando suas condições e cotas.

Revise todas as mensagens antes de usá-las. Faça contato apenas quando houver base legal e expectativa razoável de pertinência, respeite pedidos de não contato e as regras aplicáveis de privacidade e proteção de dados (incluindo a LGPD). Este projeto não implementa disparo de mensagens, enriquecimento de dados pessoais ou envio automático.

## Segurança

- `.env` contém segredos locais e não deve ser commitado.
- As mensagens geradas são sugestões, não afirmações verificadas sobre a empresa.
- A integração com Gemini pode gerar custos e está sujeita aos limites da sua conta.
