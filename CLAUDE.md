# ratual-backend

API (Flask, WSGI) do Ratual. Hospedada na KingHost **sem root**, **Python 3.9**, MySQL/MariaDB (em etapa
futura). Prioridades: **performance e segurança**. Base derivada do projeto-modelo investimentos-backend.

## Comandos

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; use bin/activate no Linux (Python 3.9!)
pip install -r requirements-dev.txt
python -m pytest                                     # testes
python -m ruff check . && python -m ruff format .    # lint + formatação
python wsgi.py                                       # servidor local em http://localhost:8000/api
python scripts/check_env.py                          # diagnóstico de ambiente
python scripts/package.py                            # gera dist/ para o FTP da KingHost
```

## Agente especializado

`.claude/agents/ratual-arquiteto.md`: arquitetura, segurança e especialista técnico. Use-o antes de criar
módulos/rotas/tabelas/dependências e para revisar diffs.

## Documentação

`docs/ARCHITECTURE.md` (camadas, decisões, roadmap), `docs/DEPLOY_KINGHOST.md` (passo a passo curto),
`docs/referencia/` (guias do modelo: banco, login, problemas conhecidos; **desenho-alvo**, nem tudo existe
ainda). Ao mudar a base, atualize o guia correspondente no mesmo commit; nunca coloque dados reais
(e-mails, usuários, senhas) em arquivos versionados.

## Documentos congelados (IMUTÁVEIS)

`docs/PLAYBOOK_NOVO_PROJETO_KINGHOST.md` (v1) é a **referência congelada** da base de projetos: **nunca
edite, renomeie nem apague**, nem para corrigir erro de digitação. Se algo estiver desatualizado, crie uma
nova versão (`..._v2.md`) e registre-a com `python scripts/check_frozen.py --add <arquivo>`, só quando o
dono pedir. A lista está em `docs/frozen.sha256`; `pytest` e o hook `.githooks/pre-commit`
(`git config core.hooksPath .githooks`) falham se algo mudar. Os guias continuam editáveis.

## Regras

- **Compatibilidade Python 3.9**: use `Optional[X]`, `list[str]`/`dict[str, X]` (ok), nada de
  `X | None`, `match`, nem `zip(strict=)`. Teste sempre com 3.9.
- **Dependências**: só pacotes com wheel pronto (sem compilar). Fixe versões em `requirements.txt` e valide
  a resolução em 3.9 (`uv pip install --dry-run --python-version 3.9 --python-platform
  x86_64-manylinux2014 --only-binary :all: -r requirements.txt`) antes de adicionar.
- **Camadas**: rotas em `app/api/v1/` ficam finas; regra de negócio em `services/` (sem Flask); dados em
  `repositories/`. Skills/agentes reutilizam `services/`.
- **Segurança**: valide toda entrada com Pydantic; nunca logue segredos/dados pessoais; erros 5xx
  genéricos; segredos só por variável de ambiente (`.env` nunca versionado); SQL sempre parametrizado.
- **Documentação da API**: toda rota declara `summary`, docstring e `responses={...}` com modelos Pydantic
  de `app/schemas/`. Swagger em `/api/docs/swagger` (off em produção). Rotas internas são `/v1/...`; o
  prefixo `/api` vem da montagem (KingHost/`wsgi.py`).
- **Banco (quando entrar)**: acesso só por sessão por requisição dentro de repositories; schema só por
  migração Alembic; **local = STG, produção = Master** (a app barra o contrário). Nunca escreva
  credenciais em código, docs, testes ou commits.
- **Dados por usuário (quando houver login)**: toda consulta filtra por `user_id`; recurso de outro
  usuário responde 404; todo recurso novo tem teste de isolamento entre usuários.
- **Testes**: toda rota nova vem com teste (caminho feliz + erro + autorização).
- **Deploy**: após mudar código que vai ao servidor, rode `python scripts/package.py` e informe a lista de
  arquivos novos/alterados que precisam ir por FTP (`dist/` não é versionado). Deploy manual (FTP/SSH).
- **Commits**: mensagens em português, no imperativo, escopo claro.
