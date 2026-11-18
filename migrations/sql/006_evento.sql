-- Fase 3: linha do tempo de cada refrigerador (base dos alertas e do log de comandos).
-- Idempotente: pode rodar de novo.

-- Um evento com fim NULL está acontecendo agora (ex.: offline, fora da faixa = alerta ativo).
-- Eventos instantâneos (relé, subida rápida) já nascem com fim = inicio.
CREATE TABLE IF NOT EXISTS evento (
    id_evento       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_dispositivo  INT UNSIGNED NOT NULL,
    tipo            ENUM('offline','fora_faixa','subida_rapida','rele_ligado','rele_desligado') NOT NULL,
    origem          ENUM('sistema','app','externo') NOT NULL COMMENT 'app = usuário do nosso app; externo = app eWeLink/temporizador; sistema = detectado pela coleta',
    id_usuario      INT UNSIGNED NULL COMMENT 'quem executou (origem app)',
    id_comando      BIGINT UNSIGNED NULL,
    inicio          DATETIME NOT NULL,
    fim             DATETIME NULL,
    valor           DECIMAL(5,1) NULL COMMENT 'temperatura relevante (no fora_faixa: o pico)',
    detalhe         TEXT NULL COMMENT 'JSON com contexto (faixa da época, temperatura anterior etc.)',
    criado_em       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_evento),
    KEY idx_evento_dispositivo (id_dispositivo, inicio),
    KEY idx_evento_aberto (fim),
    KEY idx_evento_tipo (tipo, inicio),
    CONSTRAINT fk_evento_dispositivo FOREIGN KEY (id_dispositivo) REFERENCES dispositivo (id_dispositivo),
    CONSTRAINT fk_evento_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario),
    CONSTRAINT fk_evento_comando FOREIGN KEY (id_comando) REFERENCES comando (id_comando)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- desde quando a temperatura está fora da faixa (para aplicar a tolerância antes de abrir o alerta)
ALTER TABLE dispositivo
    ADD COLUMN IF NOT EXISTS fora_faixa_desde DATETIME NULL AFTER tolerancia_min;
