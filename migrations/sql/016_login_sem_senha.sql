-- Login sem senha (e-mail + código por e-mail): remove as colunas de senha. Idempotente.
-- Os hashes continuam existindo no banco original do Brain, caso seja preciso consultar.
ALTER TABLE usuario DROP COLUMN IF EXISTS senha_hash;
ALTER TABLE usuario DROP COLUMN IF EXISTS trocar_senha;
