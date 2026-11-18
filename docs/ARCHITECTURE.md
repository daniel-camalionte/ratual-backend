# Arquitetura

## Restrições que moldam as decisões

| Restrição | Consequência |
|---|---|
| KingHost, sem root, Python 3.9 | Só pacotes com wheel; sem serviços de sistema; código compatível com 3.9 |
| Servidor WSGI (mod_wsgi) | Flask (WSGI nativo) em vez de FastAPI/ASGI; sem WebSocket nativo |
| MySQL/MariaDB (próxima etapa) | SQLAlchemy 2 + PyMySQL (puro Python) + Alembic |
| Performance e segurança | orjson, limites de taxa, cabeçalhos de segurança, validação estrita de config |

## Estado atual (etapa 0: hello world)

```
app/
  __init__.py        create_app() — application factory
  config.py          Settings (pydantic-settings), validação rígida em produção
  extensions.py      CORS e rate limiter
  version.py         SERVICE_NAME, versão, X-Build
  core/
    http.py          request id, cabeçalhos de segurança, JSON (orjson), log de requisição
    errors.py        AppError + handlers globais (nunca vazam detalhes internos)
    logging.py       logs JSON estruturados com request_id
  api/
    health.py        /health (liveness)
    v1/hello.py      /v1/hello
  schemas/           modelos Pydantic (entrada/saída) — também geram o OpenAPI/Swagger
wsgi.py              entrada WSGI local (emula a montagem em /api)
deploy/kinghost/     api.wsgi (definitivo) e api.diagnostic.wsgi (descobre o Python do servidor)
scripts/             check_env, package, check_frozen
tests/               pytest (26 testes)
```

Rotas públicas: `GET /api/v1/hello`, `GET /api/health`. Swagger em `/api/docs/swagger` (somente fora de
produção).

## Segurança já implementada

- Config falha na inicialização em produção com `SECRET_KEY` fraca ou CORS `*`.
- Cabeçalhos: `nosniff`, `X-Frame-Options`, CSP `default-src 'none'`, `Referrer-Policy`,
  `Permissions-Policy`, `Cache-Control: no-store`, HSTS em produção.
- CORS com lista explícita de origens, só em `/v1/*`.
- Rate limit global por IP (`memory://` = por processo); corpo limitado a 1 MB.
- `X-Request-ID` só é aceito se bem formado (evita log injection).
- Erros 5xx genéricos para o cliente; detalhe só no log.
- Swagger desligado por padrão em produção.

## Camadas (regra)

```
api/v1/<recurso>.py   HTTP: valida entrada (Pydantic), chama o serviço, serializa
services/             regras de negócio — sem Flask
repositories/         acesso a dados (SQLAlchemy)
models/               entidades ORM
schemas/              modelos Pydantic de entrada/saída
integrations/         provedores externos atrás de interfaces
```

`services/` não importa Flask: a mesma lógica serve a API, a tarefas agendadas e a agentes.

## Roadmap sugerido (cada etapa com testes e guia atualizado)

1. **Banco**: SQLAlchemy + PyMySQL + Alembic, trava STG × Master, `/health/ready`, `scripts/check_db.py`.
2. **Autenticação**: código por e-mail + sessão em cookie `HttpOnly` (desenho em
   `docs/referencia/AUTENTICACAO.md`), `@login_required`, isolamento por `user_id`.
3. **Domínio do Ratual**: definir módulos a partir do mapeamento do produto.
4. **Endurecimento de produção**: exposição externa restrita, auditoria, rotação de segredos, LGPD.

## Decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-11-18 | Base derivada do projeto-modelo investimentos-backend, só com o necessário para o hello world | Reaproveita o que já foi validado na KingHost sem trazer domínio de outro produto |
| 2026-11-18 | Banco e autenticação ficam para as próximas etapas | Hello world não precisa; evita código morto e superfície de ataque |
