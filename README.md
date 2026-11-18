# ratual-backend

API do Ratual.

**Stack:** Python 3.9 · Flask (WSGI) · Pydantic v2 · orjson · Flask-Limiter · flask-openapi3 (Swagger)
**Hospedagem:** KingHost (sem root, mod_wsgi). **Banco e login:** próximas etapas (ver `docs/ARCHITECTURE.md`).

## Rodando localmente

```bash
python -m venv .venv                 # use Python 3.9 (mesma versão do servidor)
.venv\Scripts\activate               # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env               # Linux: cp .env.example .env
python wsgi.py                       # http://localhost:8000
```

```bash
curl http://localhost:8000/api/v1/hello
# {"message":"Hello, World!","service":"ratual-backend","version":"0.1.0"}
```

Swagger (fora de produção): <http://localhost:8000/api/docs/swagger>

## Qualidade

```bash
python -m pytest
python -m ruff check . && python -m ruff format --check .
```

## Docker (opcional)

```bash
docker build -t ratual-backend-api .
docker compose up -d --no-build      # http://localhost:8000/api/v1/hello
```

## Rotas

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/v1/hello` | Hello world |
| GET | `/api/health` | Liveness (isenta de rate limit) |

Internamente a app serve `/v1/...`; quem a monta em `/api` é a hospedagem (produção) ou o `wsgi.py` (local).

## Deploy

`python scripts/package.py` e siga `docs/DEPLOY_KINGHOST.md`.

## Documentação

- [Arquitetura e roadmap](docs/ARCHITECTURE.md)
- [Deploy na KingHost](docs/DEPLOY_KINGHOST.md)
- [Playbook (congelado v1)](docs/PLAYBOOK_NOVO_PROJETO_KINGHOST.md)
- Guias do modelo (desenho-alvo): [`docs/referencia/`](docs/referencia/)
- [Convenções para agentes de código](CLAUDE.md) e agente [`ratual-arquiteto`](.claude/agents/ratual-arquiteto.md)

## Documentos congelados

O playbook v1 é imutável (hash em `docs/frozen.sha256`, conferido por `pytest` e por hook). Ative o hook
neste clone: `git config core.hooksPath .githooks`.
