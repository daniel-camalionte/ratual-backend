-- Auditoria de comandos enviados aos dispositivos (liga/desliga etc.)
CREATE TABLE IF NOT EXISTS comando (
    id_comando      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_dispositivo  INT UNSIGNED NOT NULL,
    id_usuario      INT UNSIGNED NOT NULL,
    acao            VARCHAR(30)  NOT NULL,
    parametros      TEXT         NULL,
    sucesso         TINYINT(1)   NOT NULL DEFAULT 0,
    resposta        TEXT         NULL,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_comando),
    KEY idx_comando_dispositivo (id_dispositivo, criado_em),
    CONSTRAINT fk_comando_dispositivo FOREIGN KEY (id_dispositivo) REFERENCES dispositivo (id_dispositivo),
    CONSTRAINT fk_comando_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
