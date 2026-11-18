# Deploy na KingHost (sem root, WSGI, Python 3.9) — hello world

Detalhes e problemas conhecidos: `docs/referencia/GUIA_BACKEND.md` §2, §8 e §11. Visão geral:
`docs/PLAYBOOK_NOVO_PROJETO_KINGHOST.md`. Substitua `<usuario>` pelo usuário do plano.

## 1. Painel (uma vez)

*Frameworks Python - WSGI* → nova aplicação: nome **`api`**, framework **\* Outros**, tipo **"Uma ou mais
aplicações"**. O painel cria `/apps_wsgi/api.wsgi` e a pasta `/apps_wsgi/api/`.
Nenhuma página do front pode usar `/api`.

## 2. Gerar o pacote (no PC)

```bash
python scripts/package.py
```

Cria `dist/api/` (para `/apps_wsgi/api/`), `dist/api.final.wsgi` e `dist/api.diagnostic.wsgi`, e lista o
que mudou desde o último pacote (envie só isso nas atualizações). Nunca inclui `.env`, `.venv`, `tests`.

## 3. Diagnóstico do Python (uma vez)

1. Substitua `/apps_wsgi/api.wsgi` por `dist/api.diagnostic.wsgi`.
2. Abra a URL da app: deve mostrar `python: 3.9...`. Se for outra versão, **pare**.

## 4. Ambiente no servidor (SSH, uma vez)

O venv **precisa ser criado no servidor**.

```bash
cd ~/apps_wsgi
python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip
# envie dist/api/ por FTP para /apps_wsgi/api/
cd ~/apps_wsgi/api
pip install -r requirements.txt
python scripts/check_env.py          # esperado: RESULTADO: tudo certo
```

## 5. `.env` no servidor

Crie `/apps_wsgi/api/.env` a partir de `.env.production.example` (valores reais **só no servidor**) e
`chmod 600 .env`. Gere a chave: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
Em produção a app **recusa iniciar** com `SECRET_KEY` fraca ou CORS `*`.

## 6. Ativar a API

Edite `dist/api.final.wsgi`: ajuste `BASE` para `/home/<usuario>/apps_wsgi`; copie para
`/apps_wsgi/api.wsgi` e reinicie pelo painel (ou salve o arquivo).

## 7. Verificar

```bash
curl -i https://<dominio>/api/v1/hello    # 200 {"message":"Hello, World!",...}
curl -i https://<dominio>/api/health      # 200
curl -i https://<dominio>/api/docs/swagger # 404 (Swagger desligado em produção)
```

Confira os cabeçalhos (HSTS, `X-Frame-Options`, CSP) e o `X-Build` (identifica o pacote no ar).

## 8. Atualizações

`python scripts/package.py` → FTP só dos NOVOS/ALTERADOS (apague os REMOVIDOS) → `pip install -r
requirements.txt` se mudou → salvar o `api.wsgi` ou reiniciar pelo painel (o `.env` só é lido na
inicialização). Reverter = reenviar os arquivos anteriores.
