# Porte do Brain para o Ratual — convenções

Origem: `C:\GIT\brain\brain-backend` (Flask-RESTful, camadas controller → rule → model, JWT). Destino: este repositório
(Flask-OpenAPI3, camadas `api/v1` → `services` → `repositories`, sessão em cookie httpOnly). O banco **já tem a
estrutura e os dados do Brain** (STG `ratual01`, PRD `ratual`); novas tabelas/colunas entram como arquivo novo em
`migrations/sql/NNN_nome.sql` (idempotente) e rodam com `RATUAL_ENV=stg python scripts/migrar.py`.

## De → para

| Brain | Ratual |
|---|---|
| `controller/X.py` (MethodView) | `app/api/v1/<modulo>.py` com `bp = APIBlueprint("<modulo>", __name__, url_prefix="/v1/<rota>", doc_ui=False, abp_tags=[Tag(name="...")])`; rotas finas |
| `rule/X.py` retornando `(dict, status)` | `app/services/<modulo>.py` **sem Flask**; retorna dados e **levanta `AppError(msg, status_code=, code=)`** nos erros |
| `model/X.py` + `BaseModel` | `app/repositories/<modulo>.py` com SQL explícito via `app.db` (`fetch_all`, `fetch_one`, `execute`, `insert`; placeholders `%s`, **sempre parametrizado**) |
| `schema/*.json` / `request.get_json()` | modelos Pydantic em `app/schemas/<modulo>.py` (corpo/query/path validados pelo flask-openapi3) |
| `@requer_login` / `requer_master` / `requer_admin` | `app.core.auth`: `login_required`, `master_required`, `admin_required`, `current_user()`, `is_master()`, `is_admin()`; em blueprint que exige login chame `require_login_for_blueprint(bp)` |
| `config.env as memory` | `current_app.extensions["settings"]` (`app/config.py`; já tem SMTP, CRYPTO_KEY, eWeLink, EZVIZ, etc.) |
| `library/Crypto.py` | `app/core/crypto.py` (`encrypt`/`decrypt`, mesmo formato) |
| `library/SMTP.py` | `app/integrations/email.py` (`enviar(para, assunto, html) -> bool`) |
| `AuditoriaModel().registrar(...)` | `app.repositories.auditoria.registrar(...)` |
| `library/Senha.py` | `app/core/senha.py` |
| `library/Ewelink.py`, `library/Ezviz.py`, `library/HttpClient.py` | `app/integrations/` (usa `requests`, com timeout) |

## Regras

- **Mesmo comportamento do Brain**: mesmas regras de negócio, mesmas permissões (master vê tudo; cliente só a própria
  empresa; admin gerencia usuários; operador/visualizador conforme o Brain), mesmos nomes de campos nas respostas.
  Rotas iguais às do Brain, com prefixo `/v1` (ex.: Brain `/dispositivos` → `/api/v1/dispositivos`).
- **Isolamento por empresa**: toda consulta de dados de cliente filtra por `id_empresa` do usuário (exceto master); recurso
  de outra empresa responde 404. Todo módulo traz teste de isolamento.
- Python **3.9** (`Optional[X]`, sem `X | None`, sem `match`). Só dependências já em `requirements.txt`.
- Datas: o banco guarda horário de Brasília (naive). O JSON sai em ISO 8601 (`2026-11-18T10:30:00`); `Decimal` vira número.
- Segredos só pelo `settings`; **nunca** logar tokens, senhas, códigos nem dados pessoais; 5xx genérico; sem SQL concatenado.
- Cada rota declara `summary`, docstring curta e `responses={...}` com modelos de `app/schemas/`.
- Não edite arquivos compartilhados (`app/__init__.py`, `app/api/__init__.py`, `app/api/v1/__init__.py`, `app/config.py`,
  `requirements.txt`, `docs/PLAYBOOK_*`): quem integra é o coordenador. Exponha `bp` no seu módulo e liste no relatório
  qualquer variável de ambiente ou dependência nova de que precisou.
- Testes em `tests/test_<modulo>.py`, sem banco real: troque as funções do repository por dublês com `monkeypatch`
  e use a fixture `login_as(tipo_empresa=..., perfil=..., id_empresa=...)` de `tests/conftest.py`. Cubra: caminho feliz, erro,
  401 sem login, 403 de perfil e isolamento entre empresas.
- Rode `RATUAL_ENV=` não é necessário nos testes. Valide com `.venv/Scripts/python.exe -m pytest -q` e
  `.venv/Scripts/python.exe -m ruff check app tests`.
- **Nada de escrita em PRD**. Para testar contra dados reais use só STG (`RATUAL_ENV=stg`), leitura de preferência.
