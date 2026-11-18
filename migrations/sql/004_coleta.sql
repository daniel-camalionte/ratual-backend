-- Fase 1: estado atual do dispositivo (para o app ler do banco) e log de execuções da coleta.
-- Idempotente: pode rodar de novo.

-- Último estado conhecido, atualizado a cada coleta (o histórico continua na tabela leitura)
ALTER TABLE dispositivo
    ADD COLUMN IF NOT EXISTS temperatura  DECIMAL(5,1) NULL AFTER online,
    ADD COLUMN IF NOT EXISTS umidade      DECIMAL(5,1) NULL AFTER temperatura,
    ADD COLUMN IF NOT EXISTS rele         TINYINT(1)   NULL AFTER umidade,
    ADD COLUMN IF NOT EXISTS sinal        SMALLINT     NULL COMMENT 'RSSI do Wi-Fi em dBm' AFTER rele,
    ADD COLUMN IF NOT EXISTS limite_min   DECIMAL(5,1) NULL COMMENT 'limite inferior configurado no termostato' AFTER sinal,
    ADD COLUMN IF NOT EXISTS limite_max   DECIMAL(5,1) NULL COMMENT 'limite superior configurado no termostato' AFTER limite_min,
    ADD COLUMN IF NOT EXISTS data_leitura DATETIME     NULL COMMENT 'horário da última leitura (Brasília)' AFTER limite_max;

-- Uma linha por execução da coleta: permite saber se ela parou e quais horários ficaram sem dados
CREATE TABLE IF NOT EXISTS coleta_log (
    id_coleta     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    inicio        DATETIME     NOT NULL,
    fim           DATETIME     NULL,
    status        ENUM('ok','erro','ignorada') NOT NULL,
    dispositivos  INT UNSIGNED NOT NULL DEFAULT 0,
    leituras      INT UNSIGNED NOT NULL DEFAULT 0,
    chamadas_api  INT UNSIGNED NOT NULL DEFAULT 0,
    duracao_ms    INT UNSIGNED NULL,
    mensagem      TEXT         NULL,
    PRIMARY KEY (id_coleta),
    KEY idx_coleta_inicio (inicio),
    KEY idx_coleta_status (status, inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
