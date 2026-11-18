-- Câmeras EZVIZ: cadastro, vínculo com o refrigerador vigiado e alarmes (pessoa/movimento).
-- Idempotente: pode rodar de novo.

-- Câmera da conta EZVIZ. A empresa vem do refrigerador vinculado (mesmo controle de acesso).
CREATE TABLE IF NOT EXISTS camera (
    id_camera        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    deviceserial     VARCHAR(20)  NOT NULL,
    canal            SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    nome             VARCHAR(150) NULL,
    modelo           VARCHAR(60)  NULL,
    id_dispositivo   INT UNSIGNED NULL COMMENT 'refrigerador vigiado; NULL = ainda não vinculada',
    criptografada    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'criptografia de vídeo ligada na câmera',
    codigo_cifrado   TEXT         NULL COMMENT 'código de verificação (etiqueta) cifrado com library/Crypto',
    online           TINYINT(1)   NOT NULL DEFAULT 0,
    data_status      DATETIME     NULL COMMENT 'última verificação de status pela coleta',
    ultimo_alarme_em DATETIME     NULL COMMENT 'horário do alarme mais recente já importado',
    ativo            TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_camera),
    UNIQUE KEY uk_camera_serial_canal (deviceserial, canal),
    KEY idx_camera_dispositivo (id_dispositivo),
    CONSTRAINT fk_camera_dispositivo FOREIGN KEY (id_dispositivo) REFERENCES dispositivo (id_dispositivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Alarmes importados da EZVIZ (a nuvem dela guarda por poucos dias: importamos e guardamos a foto).
CREATE TABLE IF NOT EXISTS camera_alarme (
    id_alarme        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_camera        INT UNSIGNED NOT NULL,
    alarm_id         VARCHAR(80)  NOT NULL COMMENT 'id do alarme na EZVIZ (deduplicação)',
    tipo             INT          NULL COMMENT 'alarmType da EZVIZ',
    data_alarme      DATETIME     NOT NULL COMMENT 'horário de Brasília',
    foto_arquivo     VARCHAR(255) NULL COMMENT 'caminho relativo em storage/ (NULL = não baixada)',
    foto_criptografada TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'foto cifrada pela câmera (criptografia ligada)',
    criado_em        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_alarme),
    UNIQUE KEY uk_camera_alarme (alarm_id),
    KEY idx_camera_alarme_data (id_camera, data_alarme),
    CONSTRAINT fk_camera_alarme_camera FOREIGN KEY (id_camera) REFERENCES camera (id_camera)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Linha do tempo do refrigerador passa a mostrar os eventos da câmera que o vigia
ALTER TABLE evento
    MODIFY COLUMN tipo ENUM('offline','fora_faixa','subida_rapida','rele_ligado','rele_desligado',
                            'camera_deteccao','camera_offline') NOT NULL;

-- Log de execução: a coleta da câmera tem a própria cron, separada da eWeLink
ALTER TABLE coleta_log
    ADD COLUMN IF NOT EXISTS fonte ENUM('ewelink','ezviz') NOT NULL DEFAULT 'ewelink' AFTER id_coleta,
    ADD KEY IF NOT EXISTS idx_coleta_fonte (fonte, status, inicio);
