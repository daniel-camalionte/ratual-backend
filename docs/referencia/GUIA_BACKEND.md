> **Referência do projeto-modelo (investimentos-backend).** Descreve o desenho-alvo: banco, login e scripts como `check_db.py`, `create_user.py` e `init_project.py` **ainda não existem** no ratual-backend (ver `docs/ARCHITECTURE.md`, roadmap). Onde o texto citar o projeto de origem (domínio, usuário do plano), troque pelos valores do Ratual.

# Guia do backend (Flask/WSGI na KingHost)

Detalhe técnico do backend: ambiente local, banco, variáveis, deploy e segurança. A **visão geral e a ordem
dos passos** (backend + front) estão no **PLAYBOOK** (`docs/PLAYBOOK_NOVO_PROJETO_KINGHOST.md`); o login
está em `docs/AUTENTICACAO.md`; o passo a passo curto de deploy em `docs/DEPLOY_KINGHOST.md`.

---

## 0. Resumo da arquitetura

| Item | Escolha | Por quê |
|---|---|---|
| Servidor | Apache + **mod_wsgi**, Python **3.9** | É o que o plano oferece; sem root, sem ASGI/WebSocket |
| Framework | **Flask** + `flask-openapi3` | WSGI nativo; Swagger gerado dos schemas Pydantic |
| Validação/config | **Pydantic v2** + `pydantic-settings` | Config tipada que **falha ao iniciar** se insegura |
| JSON | `orjson` | Performance |
| Banco | **SQLAlchemy 2 + PyMySQL + Alembic** | PyMySQL é puro Python (sem compilar); migrações versionadas |
| Segurança | Headers, CORS restrito, rate limit, request-id, erros genéricos | Ver seção 9 |
| URL | `https://<dominio>/api/v1/...` | Front e API no mesmo domínio |

Regra de ouro: **só instale pacotes com wheel pronto** (sem compilar). Não há compilador nem root
no servidor.

---

## 1. Antes de começar: o que reunir

- [ ] Acesso **SSH** e **FTP** da hospedagem (usuário, host). FTP raiz = `home` do usuário.
- [ ] Domínio/URL final do front e da API (ex.: `https://www.exemplo.com.br` e `.../api`).
- [ ] Credenciais do MySQL: **duas bases** — STG e Master (host, usuário, senha, nome).
- [ ] Python do servidor: no SSH, `python3 --version` (aqui: 3.9.x).
- [ ] No seu PC: Git, Docker (opcional), Python qualquer (para instalar o `uv`, ver seção 4).

> Nunca cole senhas em chat, tickets, código ou commits. Elas vivem só no `.env` (seção 7).

---

## 2. Criar a aplicação no painel da KingHost

Painel → **Frameworks Python - WSGI** → *Criar uma nova aplicação*:

| Campo | Valor |
|---|---|
| Nome da aplicação | ex.: `api` (vira o **prefixo da URL**: `/api`) |
| Framework | `* Outros` (Flask não está na lista) |
| Tipo da aplicação | **"Uma ou mais aplicações"** → monta em `/<nome>`; ou a 1ª opção para a raiz do domínio |

O painel cria:
- `/apps_wsgi/<nome>.wsgi` — arquivo de entrada (vem com um exemplo web.py; será substituído);
- `/apps_wsgi/<nome>/` — pasta onde vai o código.

> **Conflito de URL:** se a app é montada em `/api`, **nenhuma página do front pode usar `/api`**
> (aqui a página de chaves virou `/api-keys`). O Apache manda tudo sob `/api` para o Flask.

---

## 3. Criar o projeto a partir deste template

```bash
git clone <este-repo> meu-projeto-backend && cd meu-projeto-backend
python scripts/init_project.py --name "Meu Projeto" --slug meu-projeto        --domain www.meuprojeto.com.br --kinghost-user meuusuario --description "API do meu projeto."
rm -rf .git && git init           # novo histórico (o do template não deve ir junto)
```

O script troca nome do serviço, título da API, domínio (CORS), caminhos do `api.wsgi`, nome da imagem
Docker e os testes que citam o nome; é idempotente e tem `--dry-run`. Depois dele a suíte continua
verde (testado). **A aplicação no painel deve se chamar `api`** (o prefixo `/api` é convenção do
template). O que o script **não** faz (criar `.env`, `SECRET_KEY`, usuários) está no PLAYBOOK, em
“O que não copiar”.

---

## 4. Ambiente local com a MESMA versão do Python do servidor

Testar em outra versão esconde erros (ex.: sintaxe `X | None` não existe no 3.9). Sem instalar
Python no sistema, use o `uv`:

```bash
py -3 -m pip install --user uv            # (Windows) qualquer Python serve para instalar o uv
py -3 -m uv venv --python 3.9 .venv       # baixa um CPython 3.9 isolado
.venv\Scripts\activate                    # Linux/Mac: source .venv/bin/activate
py -3 -m uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
```

Pegadinhas conhecidas:
- **Windows 32 bits:** `greenlet` (dependência do SQLAlchemy) tenta compilar e falha. Local, instale
  `SQLAlchemy` e `alembic` com `--no-deps` (greenlet só serve para async, que não usamos). No
  servidor Linux o wheel instala normalmente.
- **Porta 5000** costuma estar ocupada: o projeto usa **8000**.
- **Antes de fixar uma dependência nova**, confirme que existe wheel Linux para o servidor:
  ```bash
  uv pip install --dry-run --python-version 3.9 --python-platform x86_64-manylinux2014 \
      --only-binary :all: -r requirements.txt
  ```

---

## 5. Rodar e testar local

```bash
python -m pytest                       # testes (usam SQLite em memória, não tocam em banco real)
python -m ruff check . && python -m ruff format --check .
python wsgi.py                         # http://localhost:8000/api/v1/hello
```

Docker (opcional, simula o isolamento do servidor: usuário sem root, FS somente leitura):

```bash
docker build -t <projeto>-backend-api .
docker compose up -d --no-build        # http://localhost:8000
```
> `docker compose up --build` pode falhar com erro "bake" no Docker Desktop; use os dois passos acima.

Swagger local: `http://localhost:8000/api/docs/swagger`.

---

## 6. Banco de dados: STG × Master

**Regra:** `localhost`/desenvolvimento usa **sempre STG**; **produção** usa **Master**. O código
impõe isso: fora de produção, `DB_TARGET=master` impede a aplicação de iniciar; em produção o alvo
é derivado (`master`). Nunca testar local contra o Master.

```bash
python scripts/check_db.py            # só leitura; mostra alvo, versão, charset (nunca a senha)
python -m alembic revision --autogenerate -m "descricao"
python -m alembic upgrade head        # local => STG; no servidor => Master
```

Notas:
- A base vem com charset `latin1`; a conexão força **`utf8mb4`** (acentos/emoji).
- Pool conservador (3 + 2) por limite de conexões da hospedagem compartilhada.
- `GET /api/health/ready` valida o banco (200 ok / 503 indisponível, sem vazar detalhes).
- A KingHost permitiu conexão remota do PC ao MySQL; se o seu plano bloquear, libere o IP no painel.

---

## 7. Variáveis de ambiente

Arquivos (todos com **placeholders**, nunca valores reais): `.env.example` (local/STG) e
`.env.production.example` (servidor/Master). O `.env` real é ignorado pelo git.

| Variável | Local/STG | Produção |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `SECRET_KEY` | qualquer | **obrigatória**, 32+ chars aleatórios (a app recusa iniciar sem) |
| `CORS_ORIGINS` | `http://localhost:3000` | domínio do front (nunca `*`) |
| `DB_HOST/PORT/USER/PASSWORD/NAME` | base **STG** | base **Master** |
| `DOCS_ENABLED` | (ligado por padrão) | **desligado por padrão**; `true` só para diagnóstico |
| `PUBLIC_BASE_PATH` | `/api` | `/api` (= nome da app no painel) |

Gerar chave: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
No servidor: `chmod 600 .env`.

---

## 8. Deploy na KingHost (passo a passo)

Pasta de upload: gere o pacote com o script (nunca monte à mão):

```bash
python scripts/package.py
```

Ele cria `dist/api/` (para `/apps_wsgi/<nome>/`) e `dist/api.final.wsgi` (para `/apps_wsgi/<nome>.wsgi`),
sem `.venv`, `tests`, `.git`, `.env` nem `__pycache__`. A cada execução lista **o que mudou desde o
último pacote** (novos/alterados/removidos): envie só isso nas atualizações.

### 8.1 Diagnóstico (descobrir o Python real do servidor WSGI)
1. Substitua `/apps_wsgi/<nome>.wsgi` por `deploy/kinghost/api.diagnostic.wsgi`.
2. Abra a URL da app: deve mostrar `python: 3.9...`. Se for outra versão, **pare** (as libs do venv
   não carregariam).

### 8.2 Virtualenv e dependências (SSH)
O venv **precisa ser criado no servidor** (um venv do Windows não funciona no Linux).
```bash
cd ~/apps_wsgi
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```
Envie o pacote por FTP para `/apps_wsgi/<nome>/` e instale:
```bash
cd ~/apps_wsgi/<nome>
source ../venv/bin/activate
pip install -r requirements.txt
python scripts/check_env.py          # esperado: RESULTADO: tudo certo
```

### 8.3 `.env` no servidor
Crie `/apps_wsgi/<nome>/.env` a partir do `.env.production.example` (valores reais, só no servidor).
```bash
python scripts/check_db.py           # esperado: alvo: master / conexão OK
python -m alembic upgrade head       # aplica migrações na Master (quando houver)
```

### 8.4 Ativar a API
Substitua `/apps_wsgi/<nome>.wsgi` por `deploy/kinghost/api.wsgi` (ajuste `BASE`). Reinicie pelo painel.

### 8.5 Verificar
```bash
curl -i https://<dominio>/api/v1/hello       # 200
curl -i https://<dominio>/api/health         # 200
curl -i https://<dominio>/api/health/ready   # 200 {"database":"ok"}
```
Confira os headers (HSTS, `X-Frame-Options`, CSP) e que `/api/docs/swagger` dá **404** (a menos que
`DOCS_ENABLED=true`).

### 8.6 Atualizações futuras
`python scripts/package.py` → FTP dos arquivos que ele listar como novos/alterados → `pip install -r requirements.txt` (se mudou dependência) →
`alembic upgrade head` (se há migração) → **salvar o `.wsgi`** ou reiniciar pelo painel. O
`api.wsgi` limpa os módulos em cache, então salvar o arquivo recarrega código e `.env`. Se algo
não refletir, use o botão de reiniciar do painel.

---

## 9. Segurança embutida (conferir ao criar o projeto)

- Config falha na inicialização em produção com `SECRET_KEY` fraca, CORS `*` ou `DB_ECHO` ligado.
- Trava STG/Master (seção 6). Senhas como `SecretStr` (mascaradas em log/repr/erros).
- Headers: `nosniff`, `X-Frame-Options: DENY`, CSP `default-src 'none'`, `Referrer-Policy`,
  `Permissions-Policy`, `Cache-Control: no-store`, HSTS em produção.
- CORS só para `/v1/*` e origens listadas; rate limit global por IP; corpo máx. 1 MB.
- `X-Request-ID` aceito só se bem formado (evita log injection); erros 5xx genéricos.
- Swagger desligado em produção; sua CSP relaxada vale só nas páginas `/docs`.
- Limitação: rate limit `memory://` é **por processo** (vários workers multiplicam o limite).

**Checklist antes de ir ao ar:** remover `DOCS_ENABLED=true` · `SECRET_KEY` nova e forte ·
`CORS_ORIGINS` com o domínio real · senhas do banco rotacionadas se já circularam em chat ·
`.env` com `chmod 600` · nenhum `.env` no git.

---

## 10. Front-end no mesmo domínio

O front (Next.js estático em `www/`) tem guia próprio no repositório do front:
`docs/GUIA_FRONTEND.md`. Pontos que afetam o backend: a API fica em `/api` na **mesma origem** do front
(`NEXT_PUBLIC_API_URL=/api`), `CORS_ORIGINS` deve ser exatamente `https://<dominio-canonico>` e nenhuma
rota do front pode começar com `/api`.

---

## 11. Problemas conhecidos e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| `ImportError: cannot import name 'Sentinel' from 'typing_extensions'` | Pacotes antigos do **sistema** (`/usr/local/lib/python3.9`) vencem os do venv | `api.wsgi` coloca o venv **no início** do `sys.path` (já incluído) |
| Corrigiu o `.wsgi` mas o erro persiste | mod_wsgi **reaproveita o processo**; `sys.path`/módulos da tentativa anterior ficam | `api.wsgi` remove/reinsere o path e limpa módulos (já incluído); reinicie pelo painel se preciso |
| Mudei `.env`/código e nada mudou | `Settings` em cache e módulos `app.*` já importados | `api.wsgi` limpa `app.*` ao ser salvo; senão reiniciar pelo painel |
| `/api/api/v1/hello` (prefixo duplicado) | Rotas internas com `/api` + montagem em `/api` | Rotas internas são `/v1/...`; o prefixo vem da montagem |
| Swagger "Try it out" dá 404 | OpenAPI não sabia do prefixo de montagem | `PUBLIC_BASE_PATH=/api` (padrão) preenche `servers` |
| `/api/docs/swagger` dá 404 em produção | Swagger desligado por padrão | `DOCS_ENABLED=true` + reiniciar (temporário) |
| Log `ModSecurity: Audit log ... Permission denied` | Firewall da hospedagem | Ruído; ignorar |
| App não inicia: "SECRET_KEY inválida" / "proibido usar a base 'master'" | Travas de segurança | Corrigir `.env` (é o comportamento desejado) |
| `pip` tenta compilar e falha | Pacote sem wheel para o servidor | Escolher versão/pacote com wheel (seção 4, `--dry-run`) |
| Acentos quebrados no banco | Base em `latin1` | Conexão já usa `utf8mb4`; criar tabelas com `utf8mb4` |
| `Failed to fetch` no front chamando a API | CORS só vale para `/v1/*` e origens listadas | Ajustar `CORS_ORIGINS` e chamar `/api/v1/...` |
| Login 403 `forbidden_origin` | acesso por `http://` ou sem `www` (origem fora do CORS) | forçar HTTPS/`www` no `.htaccess` do front |
| Login 503 `email_unavailable` | SMTP ausente ou errado | ver `docs/AUTENTICACAO.md` (seção 7 e 8) |
| 422 em vez de 401 para visitante sem login | validação do corpo roda antes do `@login_required` | `require_login_for_blueprint(bp)` no blueprint |
| `ModuleNotFoundError` de pacote novo após o deploy | falta `pip install -r requirements.txt` no servidor | rodar o pip no venv do servidor |
| `alembic upgrade` conecta na base errada | `APP_ENV` do shell/.env | local => STG, servidor => Master; `check_db.py` mostra o alvo |

---

## 12. Checklist

O checklist consolidado (backend + front) está no PLAYBOOK. Específico do backend:

- [ ] `init_project.py` executado, novo histórico git, `pytest` e `ruff` verdes
- [ ] `.env` local aponta para **STG**; `check_db.py` OK; `alembic upgrade head` aplicado no STG
- [ ] Diagnóstico mostrou Python 3.9 no servidor; venv criado **no servidor**; `check_env.py` OK
- [ ] `.env` de produção (Master + SMTP); `alembic upgrade head` e `create_user.py` na Master
- [ ] `/api/v1/hello`, `/api/health`, `/api/health/ready` = 200; Swagger desligado (`DOCS_ENABLED` removido)
