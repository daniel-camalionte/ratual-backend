-- Etapa 5: gestão de usuários/empresas pelo app, troca de senha e auditoria.
-- Idempotente: pode rodar de novo.

-- senha provisória (criada ou redefinida por outro usuário) obriga a troca no próximo acesso
ALTER TABLE usuario
    ADD COLUMN IF NOT EXISTS trocar_senha TINYINT(1) NOT NULL DEFAULT 0 AFTER senha_hash;

-- login passa a ser sempre e-mail
UPDATE usuario SET login = 'admin@admin.com.br' WHERE login = 'admin';

-- quem fez o quê na gestão (usuários, empresas, vínculo de refrigeradores, faixas)
CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario      INT UNSIGNED NOT NULL COMMENT 'quem executou',
    acao            VARCHAR(40)  NOT NULL COMMENT 'ex.: usuario_criado, senha_redefinida, dispositivo_vinculado',
    entidade        VARCHAR(20)  NOT NULL COMMENT 'usuario | empresa | dispositivo',
    id_entidade     VARCHAR(50)  NOT NULL,
    detalhe         TEXT         NULL COMMENT 'JSON com o que mudou (antes/depois)',
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_auditoria),
    KEY idx_auditoria_entidade (entidade, id_entidade),
    KEY idx_auditoria_data (criado_em),
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
