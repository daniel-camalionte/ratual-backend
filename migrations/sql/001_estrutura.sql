-- Estrutura inicial do SaaS (MariaDB 11.4)
-- empresa 1─N usuario | empresa 1─N dispositivo 1─N leitura

CREATE TABLE IF NOT EXISTS empresa (
    id_empresa      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome            VARCHAR(150) NOT NULL,
    documento       VARCHAR(20)  NULL,
    tipo            ENUM('master','cliente') NOT NULL DEFAULT 'cliente',
    ativo           TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_empresa),
    UNIQUE KEY uk_empresa_documento (documento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_empresa      INT UNSIGNED NOT NULL,
    nome            VARCHAR(150) NOT NULL,
    login           VARCHAR(150) NOT NULL,
    senha_hash      VARCHAR(255) NOT NULL,
    perfil          ENUM('admin','operador','visualizador') NOT NULL DEFAULT 'visualizador',
    ativo           TINYINT(1)   NOT NULL DEFAULT 1,
    ultimo_login    DATETIME     NULL,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_usuario),
    UNIQUE KEY uk_usuario_login (login),
    KEY idx_usuario_empresa (id_empresa),
    CONSTRAINT fk_usuario_empresa FOREIGN KEY (id_empresa) REFERENCES empresa (id_empresa)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dispositivo (
    id_dispositivo  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_empresa      INT UNSIGNED NULL COMMENT 'NULL = ainda não vinculado a um cliente',
    provedor        VARCHAR(20)  NOT NULL DEFAULT 'ewelink',
    deviceid        VARCHAR(50)  NOT NULL,
    nome            VARCHAR(150) NULL,
    modelo          VARCHAR(50)  NULL,
    marca           VARCHAR(50)  NULL,
    online          TINYINT(1)   NOT NULL DEFAULT 0,
    ativo           TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_dispositivo),
    UNIQUE KEY uk_dispositivo_provedor (provedor, deviceid),
    KEY idx_dispositivo_empresa (id_empresa),
    CONSTRAINT fk_dispositivo_empresa FOREIGN KEY (id_empresa) REFERENCES empresa (id_empresa)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Leituras coletadas periodicamente (base do gráfico). Datas em horário de Brasília.
CREATE TABLE IF NOT EXISTS leitura (
    id_leitura      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_dispositivo  INT UNSIGNED NOT NULL,
    temperatura     DECIMAL(5,1) NULL,
    umidade         DECIMAL(5,1) NULL,
    rele            TINYINT(1)   NULL,
    online          TINYINT(1)   NOT NULL DEFAULT 0,
    data_leitura    DATETIME     NOT NULL,
    PRIMARY KEY (id_leitura),
    KEY idx_leitura_dispositivo_data (id_dispositivo, data_leitura),
    CONSTRAINT fk_leitura_dispositivo FOREIGN KEY (id_dispositivo) REFERENCES dispositivo (id_dispositivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
