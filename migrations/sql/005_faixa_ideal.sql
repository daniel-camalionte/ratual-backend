-- Fase 2: faixa ideal por refrigerador (base dos alertas). Editada pelo master no app.
-- Padrão provisório -40 a 0 °C para todos (inclusive os novos que a coleta descobrir); calibrar depois.
-- Idempotente: pode rodar de novo (não sobrescreve faixas já calibradas).

ALTER TABLE dispositivo
    ADD COLUMN IF NOT EXISTS tipo           ENUM('congelado','resfriado') NULL AFTER marca,
    ADD COLUMN IF NOT EXISTS temp_min       DECIMAL(5,1) NOT NULL DEFAULT -40.0 COMMENT 'faixa ideal: mínima (°C)' AFTER tipo,
    ADD COLUMN IF NOT EXISTS temp_max       DECIMAL(5,1) NOT NULL DEFAULT 0.0   COMMENT 'faixa ideal: máxima (°C)' AFTER temp_min,
    ADD COLUMN IF NOT EXISTS tolerancia_min SMALLINT UNSIGNED NOT NULL DEFAULT 15 COMMENT 'minutos fora da faixa antes de virar alerta' AFTER temp_max;

-- tipo inicial (só onde ainda não foi definido); ajustável pelo app
UPDATE dispositivo SET tipo = 'resfriado'
 WHERE tipo IS NULL AND deviceid IN ('10028a1aa1', '10028a2b21', '10028a1b4d');  -- Sexto Sentido, Tô Tom Tim, Leiteria JLS
UPDATE dispositivo SET tipo = 'congelado' WHERE tipo IS NULL;
