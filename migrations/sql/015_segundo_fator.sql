-- 2º fator por código de e-mail. Idempotente.
-- E-mail de verificação (opcional): se vazio, o código vai para o próprio login (que é um e-mail).
ALTER TABLE usuario
    ADD COLUMN IF NOT EXISTS email_verificacao VARCHAR(150) NULL COMMENT 'destino do código do 2o fator (vazio = login)' AFTER login;

-- Só o HMAC do código fica no banco (nunca o código).
CREATE TABLE IF NOT EXISTS codigo_login (
    id_codigo       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario      INT UNSIGNED NOT NULL,
    codigo_hash     CHAR(64)     NOT NULL,
    expira_em       DATETIME     NOT NULL COMMENT 'UTC',
    tentativas      TINYINT UNSIGNED NOT NULL DEFAULT 0,
    usado_em        DATETIME     NULL     COMMENT 'UTC',
    ip              VARCHAR(45)  NULL,
    criado_em       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    PRIMARY KEY (id_codigo),
    KEY idx_codigo_usuario (id_usuario, criado_em),
    CONSTRAINT fk_codigo_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
