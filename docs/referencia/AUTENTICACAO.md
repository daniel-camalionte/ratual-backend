> **Referência do projeto-modelo (investimentos-backend).** Descreve o desenho-alvo: banco, login e scripts como `check_db.py`, `create_user.py` e `init_project.py` **ainda não existem** no ratual-backend (ver `docs/ARCHITECTURE.md`, roadmap). Onde o texto citar o projeto de origem (domínio, usuário do plano), troque pelos valores do Ratual.

# Autenticação por código de e-mail (sem senha)

Como funciona, por que foi desenhada assim e como operar (cadastrar usuário, configurar o e-mail,
diagnosticar problemas). Vale para qualquer projeto criado a partir deste template.

## 1. Fluxo

```
Front                          API (/api/v1/auth)                    Banco / E-mail
  | POST request-code {email}    |                                          |
  |----------------------------->| usuário existe e está ativo? (404 se não)|
  |                              | respeita intervalo e teto por hora       |
  |                              | gera código (CSPRNG), grava só o HMAC -> |  login_codes
  |                              | envia o código por SMTP ---------------> |  e-mail do usuário
  |<-- 200 {expires_in,resend_in}|                                          |
  | POST verify-code {email,code}|                                          |
  |----------------------------->| código vigente? tentativas? compara HMAC |
  |                              | marca como usado; cria sessão ---------> |  sessions (SHA-256)
  |<-- 200 {user} + Set-Cookie   |                                          |
  | GET me (cookie)              | resolve o cookie -> usuário              |
  | POST logout                  | revoga a sessão e apaga o cookie         |
```

Só entra quem já está em `users` (**sem cadastro público**). E-mail desconhecido responde 404
`user_not_found` ("Usuário inválido"), por pedido do produto; isso revela quais e-mails existem, o que é
aceitável em uso pessoal. Em produto público, troque por uma resposta neutra.

## 2. Rotas

| Método | Rota | Corpo | Sucesso | Erros |
|---|---|---|---|---|
| POST | `/v1/auth/request-code` | `{email}` | 200 `{expires_in, resend_in}` | 404 `user_not_found`, 422, 429 `rate_limited`, 503 `email_unavailable` |
| POST | `/v1/auth/verify-code` | `{email, code}` (6 dígitos) | 200 `{user}` + cookie | 400 `invalid_code` (`details.attempts_left`), 400 `code_expired`, 404, 429 `too_many_attempts` |
| GET | `/v1/auth/me` | — | 200 `{user}` | 401 `unauthenticated` |
| POST | `/v1/auth/logout` | — | 204 | — |

Em produção as URLs têm o prefixo `/api` (ex.: `https://dominio/api/v1/auth/me`). Respostas 429 trazem
o cabeçalho `Retry-After` e `details.retry_after` (segundos). Rotas protegidas usam `@login_required`
(`app/core/auth.py`).

## 3. Tabelas (migração `migrations/versions/…usuarios_codigos_de_login_e_sessoes.py`)

| Tabela | Colunas principais |
|---|---|
| `users` | `id`, `email` (único, minúsculo), `name`, `is_active`, `created_at`, `updated_at`, `last_login_at` |
| `login_codes` | `user_id`, `code_hash` (HMAC-SHA256), `expires_at`, `attempts`, `consumed_at`, `ip`, `created_at` |
| `sessions` | `user_id`, `token_hash` (SHA-256), `expires_at`, `revoked_at`, `ip`, `user_agent`, `last_seen_at` |

Todas `InnoDB` + `utf8mb4_unicode_ci` (a base do servidor vem em `latin1`). Datas em UTC, sem fuso.
Defaults existem também no banco (`is_active`, `attempts`), para `INSERT` manuais não falharem.

## 4. Segurança (o que está implementado e por quê)

| Proteção | Detalhe |
|---|---|
| Código forte | 6 dígitos de `secrets.randbelow` (CSPRNG) |
| Código nunca em texto | só o HMAC com `SECRET_KEY` + `user_id`: um vazamento só do banco não revela os códigos (o espaço é de 10⁶) |
| Uso único, expira, limita tentativas | 10 min, 1 uso, 5 tentativas contadas com **lock de linha** (sem corrida); esgotado, o código morre mesmo que acertem depois |
| Pedir outro código invalida os anteriores | evita vários códigos válidos ao mesmo tempo |
| Intervalo e teto | 60 s entre envios e 10 códigos/hora por usuário |
| Limite por IP | `10 per minute` nos POSTs de `/auth` (Flask-Limiter; **por processo**, ver nota) |
| Sessão opaca | token de 256 bits; só o SHA-256 fica no banco; revogável (logout, usuário desativado) |
| Cookie | `HttpOnly` (JS não lê), `SameSite=Lax`, `Secure` em produção, `Path=/api` |
| CSRF | `SameSite=Lax` + checagem de `Origin` em POST/PUT/PATCH/DELETE (403 `forbidden_origin`) + CORS por lista |
| E-mail seguro | SMTP com STARTTLS/SSL **verificando o certificado**; barra injeção de cabeçalho; erros não vazam senha |
| Sem vazamento em produção | sem SMTP configurado o login responde 503; o código **nunca** vai ao log em produção |

Nota: o limite por IP em memória é por processo; com vários workers o limite efetivo multiplica. Os
limites por usuário (intervalo, teto por hora, tentativas) ficam no banco e valem sempre.

## 5. Configuração (variáveis de ambiente)

| Variável | Padrão | Observação |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` | —, 587, `starttls` | `starttls` (587), `ssl` (465) ou `none` |
| `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | — | `SMTP_FROM` precisa ser a conta autenticada |
| `AUTH_CODE_TTL_SECONDS` | 600 | validade do código |
| `AUTH_RESEND_SECONDS` | 60 | intervalo entre envios |
| `AUTH_MAX_ATTEMPTS` | 5 | tentativas por código |
| `AUTH_MAX_CODES_PER_HOUR` | 10 | envios por usuário/hora |
| `AUTH_SESSION_DAYS` | 7 | duração da sessão |
| `AUTH_RATE_LIMIT` | `10 per minute` | POSTs de `/auth` por IP |

Sem `SMTP_*`: **local/STG** imprime o código no log (somente desenvolvimento); **produção** responde 503.

## 6. Operação

```bash
python scripts/create_user.py voce@exemplo.com --name "Seu Nome"   # cadastra/ativa (local => STG; servidor => Master)
python scripts/create_user.py voce@exemplo.com --deactivate         # bloqueia (a sessão cai na hora)
python -m alembic upgrade head                                      # cria as tabelas
```

O seed de usuário **não** vai em migração nem no repositório: cada ambiente cadastra o seu.

## 7. Configurar o e-mail na KingHost (como descobrimos)

1. Painel → **Contas de e-mail** do domínio → crie uma conta só para o envio (ex.: `contato@…` ou
   `no-reply@…`; use uma senha dedicada, que possa ser trocada sem afetar a caixa principal).
2. O servidor SMTP não estava claro na documentação, então testamos por tentativa (conexão + login, sem
   enviar nada). Resultado neste plano: **`smtp.kinghost.net`, porta 587, STARTTLS**, com certificado
   válido. Os nomes `smtp.<dominio>` e `mail.<dominio>` conectam, mas o certificado **não confere**
   (é de `*.kinghost.net`), então a verificação TLS falha — não desligue a verificação, use `smtp.kinghost.net`.
3. A porta 465 (SSL) também funciona; a 25 expira. **Nunca** use `none` (envia a senha em texto puro),
   mesmo que o servidor aceite.
4. Coloque as variáveis no `.env` (local e servidor) e teste: `request-code` para o seu e-mail; confira
   também a pasta de spam na primeira vez (remetente `…kinghost.net` costuma cair lá no início).

## 8. Diagnóstico

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| 503 `email_unavailable` | SMTP ausente/errado ou fora do ar | conferir `SMTP_*`; log mostra `smtp_send_failed` + tipo do erro (nunca a senha) |
| 429 `rate_limited` ao pedir de novo | intervalo de 60 s | esperar `retry_after`; o front já mostra a contagem |
| 403 `forbidden_origin` | origem fora de `CORS_ORIGINS` (ex.: `http://` ou sem `www`) | acessar pelo domínio canônico; ajustar `CORS_ORIGINS` |
| 404 `user_not_found` | e-mail não cadastrado naquela base | `create_user.py` na base certa (STG ≠ Master) |
| 400 `code_expired` logo após pedir | código usado, invalidado por outro pedido ou expirado | pedir um novo |
| Cookie não chega em `/me` | `Path=/api` e o front chamando outro caminho, ou `Secure` em `http` | usar o prefixo `/api` e HTTPS |

## 9. Testes

`tests/test_auth.py` e `tests/test_email.py` (relógio injetável, SMTP simulado) cobrem: usuário
inexistente/inativo, envio, hash no banco, intervalo e teto, tentativas e bloqueio, expiração, uso único,
cookie e sessão, logout/revogação, CSRF, CORS, limite por IP e falha de e-mail sem “queimar” o intervalo.
