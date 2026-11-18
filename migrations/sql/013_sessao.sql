-- Sessão de login do Ratual (cookie httpOnly). No banco fica só o SHA-256 do token. Idempotente.
CREATE TABLE IF NOT EXISTS sessao (
    id_sessao       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario      INT UNSIGNED NOT NULL,
    token_hash      CHAR(64)     NOT NULL,
    expira_em       DATETIME     NOT NULL COMMENT 'UTC',
    revogada_em     DATETIME     NULL     COMMENT 'UTC',
    ip              VARCHAR(45)  NULL,
    user_agent      VARCHAR(255) NULL,
    criado_em       DATETIME     NOT NULL DEFAULT UTC_TIMESTAMP(),
    ultimo_uso_em   DATETIME     NULL     COMMENT 'UTC',
    PRIMARY KEY (id_sessao),
    UNIQUE KEY uk_sessao_token (token_hash),
    KEY idx_sessao_usuario (id_usuario),
    CONSTRAINT fk_sessao_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
