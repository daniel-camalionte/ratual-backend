-- Telefone (WhatsApp) do usuário, só dígitos com DDI/DDD. Idempotente: pode rodar de novo.

ALTER TABLE usuario
    ADD COLUMN IF NOT EXISTS telefone VARCHAR(20) NULL COMMENT 'só dígitos, com DDD' AFTER login;
