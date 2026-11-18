# Playbook: projeto novo na KingHost (backend + front + login)

> ## 🔒 VERSÃO CONGELADA — v1 (2026-11-14) — NÃO EDITAR
>
> Este documento é a **referência imutável** para construir a base de projetos futuros. Ele descreve a
> base exatamente como foi validada em produção. Por isso **não se corrige nem se atualiza aqui**.
>
> - **Para mudar algo:** crie `PLAYBOOK_NOVO_PROJETO_KINGHOST_v2.md` (copie este e edite a cópia), registre o
>   hash dele com `python scripts/check_frozen.py --add docs/PLAYBOOK_NOVO_PROJETO_KINGHOST_v2.md` e
>   mantenha este v1 intacto. Os **guias** (`GUIA_BACKEND`, `AUTENTICACAO`, `DEPLOY_KINGHOST`,
>   `ARCHITECTURE` e o `GUIA_FRONTEND` do repositório do front) continuam **vivos** e podem ser editados.
> - **Como é protegido:** hash em `docs/frozen.sha256` conferido por `tests/test_frozen_docs.py` (`pytest`)
>   e pelo hook `.githooks/pre-commit`; tag git `playbook-v1`; regra no `CLAUDE.md` para agentes.
> - **Projeto derivado que não quer congelar:** apague `docs/frozen.sha256`, `.githooks/` e o teste
>   `tests/test_frozen_docs.py`; o playbook passa a ser um documento comum.

Documento principal para repetir, em um projeto novo, tudo o que existe hoje: **API Flask (WSGI)**,
**front Next.js estático**, **banco MySQL (STG × Master)**, **login por código de e-mail**, Swagger,
segurança e deploy em hospedagem **sem root**. Siga os passos na ordem; cada um aponta para o guia com o
detalhe. Tempo estimado: **2 a 3 horas** se nada travar.

## 1. O resultado

```
Navegador ──HTTPS──▶ https://www.<dominio>/            front estático (www/)   Next.js export
                     https://www.<dominio>/api/...      API WSGI (mod_wsgi)     Flask + Pydantic
                                                          │  SMTP (smtp.kinghost.net)  ─▶ e-mail com o código
                                                          └─ MySQL/MariaDB  (local ▶ STG · produção ▶ Master)
```

- **Mesma origem** (front e API no mesmo domínio): cookie de sessão `HttpOnly`, sem CORS em produção.
- **Local = STG, produção = Master** (a aplicação recusa o contrário).
- Login sem senha: e-mail → código de 6 dígitos → sessão de 7 dias.
- Segurança embutida (headers/CSP, limites, hashes) e **testada** (74 testes no backend).

## 2. Mapa dos documentos

| Documento | Onde | Para quê |
|---|---|---|
| **Este playbook** | backend `docs/` | visão geral, ordem dos passos, checklist |
| Guia do backend | backend `docs/GUIA_BACKEND.md` | ambiente, banco, variáveis, deploy, segurança, problemas |
| Autenticação | backend `docs/AUTENTICACAO.md` | fluxo do login, tabelas, SMTP, diagnóstico |
| Deploy (roteiro curto) | backend `docs/DEPLOY_KINGHOST.md` | comandos do servidor, passo a passo |
| Arquitetura | backend `docs/ARCHITECTURE.md` | camadas e decisões |
| Guia do front | front `docs/GUIA_FRONTEND.md` | build estático, `.htaccess`, marca, simulação de produção |

## 3. Antes de começar (reunir)

- [ ] Acesso **SSH** e **FTP** do plano (usuário, host); a raiz do FTP é a `home` do usuário
- [ ] Domínio final (ex.: `www.meuprojeto.com.br`) e o **usuário** do plano (`/home/<usuario>`)
- [ ] Credenciais do MySQL das **duas bases**: STG e Master (host, usuário, senha, nome)
- [ ] Uma conta de e-mail do domínio para enviar os códigos (painel → Contas de e-mail)
- [ ] No PC: Git, Node 20+, Python qualquer (para o `uv`), Docker (opcional), Chrome (testes)

> Senhas **nunca** vão para chat, ticket, código ou commit: só no `.env` (ou digitadas no servidor).

## 4. A jornada

### Passo 1 — Criar os repositórios a partir dos modelos
Backend e front: no GitHub, **“Use this template”** (ou `git clone` + novo histórico). Depois:

```bash
# backend
python scripts/init_project.py --name "Meu Projeto" --slug meu-projeto \
       --domain www.meuprojeto.com.br --kinghost-user meuusuario --description "API do meu projeto."
# front
node scripts/init-project.mjs --name "Meu Projeto" --slug meu-projeto \
     --domain www.meuprojeto.com.br --tagline "Seu slogan" --description "Descrição do site"
```
Ambos têm `--dry-run` e são idempotentes. ✔ Verificação: `pytest` (backend) e `npm run build` (front) verdes.

### Passo 2 — Ambiente local
Backend com **Python 3.9** (a versão do servidor) via `uv`, sem instalar nada no sistema; front com Node.
Detalhes e pegadinhas (Windows 32 bits, `greenlet`, porta 5000): `GUIA_BACKEND.md` §4.

### Passo 3 — Aplicação no painel da KingHost
Painel → *Frameworks Python - WSGI*: nome **`api`**, framework **\* Outros**, tipo **“Uma ou mais
aplicações”**. O painel cria `/apps_wsgi/api.wsgi` e a pasta `/apps_wsgi/api/`. (`GUIA_BACKEND.md` §2)

### Passo 4 — Banco STG (local)
`.env` local com `DB_*` do **STG** → `python scripts/check_db.py` → `python -m alembic upgrade head` →
`python scripts/create_user.py voce@email.com --name "Você"`. (`GUIA_BACKEND.md` §6, `AUTENTICACAO.md` §6)

### Passo 5 — E-mail (SMTP)
Crie a conta de envio no painel e descubra o SMTP **testando login sem enviar nada**. Neste plano:
`smtp.kinghost.net:587` + STARTTLS (os nomes `smtp.<dominio>`/`mail.<dominio>` falham no certificado).
Coloque `SMTP_*` no `.env`. (`AUTENTICACAO.md` §7)

### Passo 6 — Rodar tudo local e testar o login
```bash
python wsgi.py                       # backend: http://localhost:8000/api  (mesmo formato da produção)
npm run dev                          # front:   http://localhost:3000
```
Sem backend? `NEXT_PUBLIC_API_MOCK=1` (login simulado). ✔ Verificação: logar de ponta a ponta com o
código recebido por e-mail.

### Passo 7 — Testar como produção (antes de publicar)
`npm run build` e `npm run prod:sim` (front + `/api` na **mesma origem**, com a CSP do `.htaccess`).
Abra o DevTools: sem violação de CSP, sem 404, sem chamada a outro domínio. (`GUIA_FRONTEND.md` §7)

### Passo 8 — Backend em produção
```bash
python scripts/package.py            # gera dist/ e lista o que mudou desde o último pacote
```
1. Substitua `/apps_wsgi/api.wsgi` por `dist/api.diagnostic.wsgi`; abra a URL e confirme **Python 3.9**.
2. SSH: crie o venv **no servidor** (`python3 -m venv ../venv`), envie `dist/api/` para `/apps_wsgi/api/`,
   `pip install -r requirements.txt`, `python scripts/check_env.py`.
3. Crie o `.env` **no servidor** (modelo: `.env.production.example`; `chmod 600`), depois
   `python scripts/check_db.py` (deve mostrar `master`), `python -m alembic upgrade head`,
   `python scripts/create_user.py voce@email.com --name "Você"`.
4. Troque `/apps_wsgi/api.wsgi` por `dist/api.final.wsgi` (ajuste `BASE`) e reinicie pelo painel.

✔ Verificação: `/api/v1/hello` e `/api/health` = 200; `/api/health/ready` = `database: ok`;
`/api/v1/auth/me` = 401 em JSON. (`GUIA_BACKEND.md` §8, `DEPLOY_KINGHOST.md`)

### Passo 9 — Front em produção
`npm run build` → envie o **conteúdo de `out/`** para `www/`, **incluindo arquivos ocultos**
(`.htaccess`) e as pastas `__next.!…`. (`GUIA_FRONTEND.md` §5)

✔ Verificação: `http://` e o domínio sem `www` redirecionam para `https://www…`; `/login/` abre; logar de
verdade; navegar sem 404; se der **500**, apagar o `.htaccess`.

### Passo 10 — Endurecimento final
Remover `DOCS_ENABLED=true` do `.env` (Swagger público), `CORS_ORIGINS` = domínio canônico, **trocar as
senhas** que tenham circulado (banco, conta de e-mail), conferir os cabeçalhos de segurança.

### Passo 11 — Registrar e proteger
Commit/push dos dois repositórios (conferir que `.env`, `dist/`, `out/` e senhas **não** entram no git).

## 5. O que NÃO copiar do projeto-modelo

| Item | Por quê / o que fazer |
|---|---|
| `.env`, `dist/`, `out/`, `.venv`, `node_modules`, `.next` | locais e/ou sensíveis; nunca versionados |
| Senhas e `SECRET_KEY` | gerar **uma nova por projeto e por ambiente** |
| Usuários cadastrados (seed) | cada ambiente cria os seus com `create_user.py` |
| Nome, domínio, usuário do plano, conta de e-mail | os scripts `init` trocam o que dá; conferir o resto |
| Logo, favicon, textos em inglês e dados fictícios (`src/data/mock`) | marca própria; ver `GUIA_FRONTEND.md` §6 |
| Tabelas de negócio | o modelo só traz as de autenticação (a migração de auth **fica**) |
| Histórico do git do modelo | `rm -rf .git && git init` (ou “Use this template”) |
| Valores do modelo nos docs | os guias citam o projeto de origem como exemplo |

## 6. Ordem de deploy e reversão

1. **Backend antes do front** (o front depende de `/api/v1/auth/*`).
2. Nova versão: `package.py` → FTP só do que ele listou → `pip install` (se `requirements.txt` mudou) →
   `alembic upgrade head` (se há migração) → salvar o `api.wsgi` (ou reiniciar pelo painel).
3. **Reverter:** reenviar a versão anterior dos arquivos; migrações **não** voltam sozinhas
   (`alembic downgrade -1` só se a migração tiver `downgrade` correto — teste no STG antes).
4. Front: reenviar o `out/` anterior; se o `.htaccess` quebrar o site (500), apagá-lo.

## 7. Segurança — checklist antes de ir ao ar

- [ ] `APP_ENV=production`, `SECRET_KEY` forte, `CORS_ORIGINS` exato (sem `*`) — a app **recusa iniciar** se não
- [ ] Banco: produção usa **Master**; local nunca toca a Master (trava no código)
- [ ] Swagger desligado (`DOCS_ENABLED` removido); `DB_ECHO` desligado
- [ ] SMTP com certificado verificado (STARTTLS/SSL); nunca `none`
- [ ] Cookie `HttpOnly` + `Secure` + `SameSite=Lax`; HTTPS e `www` forçados; HSTS
- [ ] Headers/CSP no front (`.htaccess`) e na API; `robots.txt` + `noindex`
- [ ] Bundle de produção **sem** simulação, e-mails de teste, `localhost` ou senhas (`grep` no `out/`)
- [ ] Senhas que circularam em conversa **trocadas**; `.env` com `chmod 600`; nada sensível no git

## 8. Lições aprendidas (o que mais custou tempo)

- **Servidor:** mod_wsgi + Python 3.9 + sem root ⇒ Flask, só pacotes com wheel, venv criado **no servidor**.
  Pacotes antigos do sistema vencem o venv (`api.wsgi` põe o venv no início) e o mod_wsgi **reaproveita o
  processo** (o `api.wsgi` limpa os módulos; reiniciar pelo painel resolve o resto).
- **URLs:** a app é montada em `/api` pelo servidor, então as rotas internas são `/v1/...`; o front chama
  `/api` **relativo**; nenhuma página do front começa com `/api`.
- **Cache e identidade visual:** ícone com mesmo nome de arquivo fica em cache; use a convenção do Next
  (versão na URL).
- **Windows:** `.htaccess` com CRLF pode dar 500 (LF via `.gitattributes`); `rmdir` em atalho
  (junction) para não apagar `node_modules`; fonte Google no build depende de rede (usar fonte local).
- **Como evitar retrabalho:** testar o **build de produção** e a simulação de produção *antes* de enviar
  (achou URL absoluta, 404 de navegação, redirecionamento HTTPS ausente e vestígios da simulação no bundle).
- **Processo:** senhas coladas no chat precisam ser trocadas depois; peça os dados **não secretos** e
  deixe o segredo só no `.env`.

## 9. Manter estes modelos em dia

1. Marque os dois repositórios como modelo: GitHub → *Settings* → **Template repository**.
2. Ao mudar a base, atualize o **guia** correspondente no mesmo commit (os guias são parte do produto).
   **Este playbook é a exceção: está congelado (v1)** — mudanças entram numa nova versão (v2), nunca aqui.
3. Antes de publicar uma mudança no modelo, prove que ele ainda inicializa: copie o repositório limpo,
   rode o `init`, e execute os testes/build:
   ```bash
   git archive HEAD | tar -x -C /tmp/teste && cd /tmp/teste
   python scripts/init_project.py --name Teste --slug teste --domain www.teste.com.br --kinghost-user teste1
   python -m pytest
   ```
4. Evite usar o modelo para guardar dados reais (e-mails, usuários, senhas): só placeholders.

## 10. Checklist final (copie para cada projeto)

- [ ] Repositórios criados dos modelos; scripts `init` rodados; novo histórico git
- [ ] Python 3.9 local; `pytest`/`ruff`/`npm run lint`/`npm run build` verdes
- [ ] App `api` criada no painel (Outros / “Uma ou mais aplicações”)
- [ ] STG: `check_db.py` OK, migração aplicada, usuário criado
- [ ] SMTP descoberto e configurado; login testado de ponta a ponta no local
- [ ] `prod:sim` sem violações; bundle sem vestígios de simulação
- [ ] Servidor: diagnóstico (Python 3.9), venv, `check_env.py`, `.env`, `check_db.py` = master, `alembic`, `create_user`
- [ ] `api.final.wsgi` ativo; `/api/health/ready` ok; `/api/v1/auth/me` = 401
- [ ] Front publicado (com `.htaccess`); HTTPS/`www` redirecionam; login real funcionando
- [ ] `DOCS_ENABLED` removido; senhas trocadas; nada sensível no git
- [ ] Logo, favicon e textos da marca próprios
