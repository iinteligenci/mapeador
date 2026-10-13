# Mapeador — Agente de Prospecção com Google Maps e IA

Aplicação Python que tenta coletar dados comerciais públicos, evita duplicados em SQLite e usa Gemini para sugerir uma qualificação e uma mensagem B2B. O módulo de contato **apenas exibe rascunhos**: não envia WhatsApp, e-mail ou SMS.

## Estrutura

- `scraper/maps_scraper.py`: busca no Google Maps com Playwright; tenta extrair nome, categoria, telefone e site.
- `database/db.py`: banco SQLite local e deduplicação por link do local.
- `ai_agent/analyzer.py`: qualificação estimada e mensagem com Gemini.
- `outreach/sender.py`: exibe rascunhos para revisão humana.
- `main.py`: conecta os módulos.
- `data/mapeador.sqlite3`: criado automaticamente na primeira execução.

## Instalação para iniciantes (Windows)

1. Instale Python 3.11 ou 3.12 a partir do site oficial do Python. Durante a instalação, marque **Add Python to PATH**.
2. Instale Git, caso ainda não tenha.
3. Abra o PowerShell (menu Iniciar → escreva PowerShell).
4. Copie e execute, uma linha de cada vez:

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

5. Abra a pasta `mapeador` no Explorador de Arquivos. Abra o arquivo `.env` com o Bloco de Notas e substitua `cole_sua_chave_aqui` pela sua chave real do Gemini. Salve.
6. No PowerShell, execute:

```powershell
python main.py --termo "restaurantes em Vila Velha ES" --limite 5 --oferta "serviços de presença digital"
```

Na primeira execução, o programa cria a pasta `data` e o banco SQLite. O resultado aparece no terminal. Mensagens são rascunhos e exigem revisão humana.

### Se o PowerShell bloquear a ativação do ambiente

Pode executar diretamente sem ativar o ambiente, usando:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe main.py --termo "restaurantes em Vila Velha ES" --limite 5
```

## macOS/Linux

```bash
git clone https://github.com/iinteligenci/mapeador.git
cd mapeador
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
# Edite .env e configure GEMINI_API_KEY
python main.py --termo "restaurantes em Vila Velha ES" --limite 5
```

## Configuração

O arquivo local `.env` deve conter:

```dotenv
GEMINI_API_KEY=sua_chave_real
GEMINI_MODEL=gemini-2.0-flash
DATABASE_PATH=data/mapeador.sqlite3
```

Obtenha a chave no Google AI Studio. **Não publique `.env` nem compartilhe a chave.** O repositório inclui apenas `.env.example`.

## Banco de dados

Cada lead é identificado principalmente pelo link do local no Maps. Ao reencontrar o mesmo link, o banco atualiza campos disponíveis sem criar uma segunda linha. A análise mais recente e o rascunho também ficam associados ao registro.

## Limitações e uso responsável

- Os seletores do Google Maps podem mudar; telefone/site podem não estar disponíveis e os resultados podem ficar incompletos.
- Não há tentativa de contornar CAPTCHA, login, bloqueios ou limites. Para uso comercial contínuo, avalie a Google Maps Platform Places API e siga os seus termos e cotas.
- O score é uma estimativa gerada por IA com base nos poucos dados coletados, não uma verificação objetiva da qualidade da empresa.
- Revise a mensagem antes de entrar em contato. Respeite privacidade, LGPD, regras de contato comercial e pedidos de não contato. Não há disparo automático neste projeto.

## Diagnóstico

- `GEMINI_API_KEY` ausente: verifique se criou e editou o arquivo `.env` na pasta `mapeador`.
- Chromium ausente: execute `python -m playwright install chromium`.
- Nenhum resultado: teste outro termo, rode com `--verbose` e considere mudanças na página do Maps.
