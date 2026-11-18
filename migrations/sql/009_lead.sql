-- Fase 1: contatos que chegam pelo formulário da landing page.
-- Idempotente: pode rodar de novo.

CREATE TABLE IF NOT EXISTS lead (
    id_lead         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome            VARCHAR(120) NOT NULL,
    empresa         VARCHAR(150) NOT NULL,
    telefone        VARCHAR(30)  NOT NULL,
    cidade          VARCHAR(100) NULL,
    negocio         VARCHAR(60)  NULL COMMENT 'tipo de negócio escolhido no formulário',
    quantidade      VARCHAR(30)  NULL COMMENT 'quantos equipamentos de frio',
    plano           VARCHAR(40)  NULL COMMENT 'plano de interesse',
    origem          VARCHAR(30)  NOT NULL DEFAULT 'site',
    status          VARCHAR(20)  NOT NULL DEFAULT 'novo' COMMENT 'novo | contatado | visita | fechado | perdido',
    ip              VARCHAR(45)  NULL,
    email_enviado   TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'aviso por e-mail entregue ao SMTP',
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_lead),
    KEY idx_lead_status (status),
    KEY idx_lead_data (criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
