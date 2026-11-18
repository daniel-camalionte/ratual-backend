-- Central de serviços: planos, tipos de serviço, técnicos, grade de horários e ordens de serviço.
-- Idempotente: pode rodar de novo.

-- planos de assinatura; o desconto vale sobre a mão de obra de cada serviço
CREATE TABLE IF NOT EXISTS plano (
    id_plano                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome                    VARCHAR(60)  NOT NULL,
    descricao               VARCHAR(255) NULL,
    preco_mensal            DECIMAL(10,2) NULL COMMENT 'NULL = sob medida (sem preço público)',
    desconto_servico        DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '% de desconto na mão de obra de cada serviço',
    visitas_preventivas_ano SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    pontos_inclusos         SMALLINT UNSIGNED NULL COMMENT 'NULL = sob medida',
    ativo                   TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_plano),
    UNIQUE KEY uk_plano_nome (nome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO plano (nome, descricao, preco_mensal, desconto_servico, visitas_preventivas_ano, pontos_inclusos) VALUES
    ('Monitor',       'Monitoramento 24h com alertas', 99.00,  10.00, 0, 1),
    ('Prevenção',     'Monitoramento + visitas preventivas e prioridade', 199.00, 15.00, 2, 3),
    ('Personalizado', 'Proposta sob medida', NULL, 0.00, 0, NULL);

-- plano atual de cada cliente (o histórico de assinatura vem na fase de cobrança)
ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS id_plano INT UNSIGNED NULL AFTER tipo,
    ADD CONSTRAINT fk_empresa_plano FOREIGN KEY IF NOT EXISTS (id_plano) REFERENCES plano (id_plano);

-- catálogo de serviços com o valor cheio (o desconto do plano é aplicado em cada ordem)
CREATE TABLE IF NOT EXISTS tipo_servico (
    id_tipo_servico         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome                    VARCHAR(100) NOT NULL,
    descricao               VARCHAR(255) NULL,
    valor                   DECIMAL(10,2) NOT NULL DEFAULT 0,
    cliente_pode_solicitar  TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '0 = só a equipe agenda (ex.: instalação)',
    ativo                   TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_tipo_servico)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- técnicos de campo (sem login: só para atribuir visitas)
CREATE TABLE IF NOT EXISTS tecnico (
    id_tecnico      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome            VARCHAR(120) NOT NULL,
    telefone        VARCHAR(30)  NULL,
    ativo           TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_tecnico)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- grade semanal: janelas de atendimento e quantas visitas cabem em cada uma
CREATE TABLE IF NOT EXISTS agenda_janela (
    id_janela       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    dia_semana      TINYINT UNSIGNED NOT NULL COMMENT '0 = domingo ... 6 = sábado',
    hora_inicio     TIME         NOT NULL,
    hora_fim        TIME         NOT NULL,
    vagas           SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    ativo           TINYINT(1)   NOT NULL DEFAULT 1,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_janela),
    KEY idx_janela_dia (dia_semana, hora_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- dias sem atendimento (feriados, folgas)
CREATE TABLE IF NOT EXISTS agenda_bloqueio (
    id_bloqueio     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    data            DATE         NOT NULL,
    motivo          VARCHAR(120) NULL,
    criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_bloqueio),
    UNIQUE KEY uk_bloqueio_data (data)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- pedido do cliente ou agendamento da equipe; valores gravados no momento do pedido
CREATE TABLE IF NOT EXISTS ordem_servico (
    id_os                   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_empresa              INT UNSIGNED NOT NULL,
    id_dispositivo          INT UNSIGNED NULL COMMENT 'equipamento atendido (opcional)',
    id_tipo_servico         INT UNSIGNED NOT NULL,
    id_tecnico              INT UNSIGNED NULL,
    status                  ENUM('solicitado','confirmado','em_atendimento','concluido','cancelado') NOT NULL DEFAULT 'solicitado',
    origem                  ENUM('cliente','interno') NOT NULL DEFAULT 'cliente',
    data                    DATE         NOT NULL,
    hora_inicio             TIME         NOT NULL,
    hora_fim                TIME         NOT NULL,
    descricao               TEXT         NULL COMMENT 'o que o cliente relatou',
    valor_servico           DECIMAL(10,2) NOT NULL DEFAULT 0 COMMENT 'mão de obra, valor cheio',
    desconto_percentual     DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT 'do plano do cliente no momento do pedido',
    valor_desconto          DECIMAL(10,2) NOT NULL DEFAULT 0,
    valor_pecas             DECIMAL(10,2) NOT NULL DEFAULT 0,
    descricao_pecas         VARCHAR(500) NULL,
    valor_total             DECIMAL(10,2) NOT NULL DEFAULT 0,
    observacao_tecnica      TEXT         NULL COMMENT 'o que foi feito',
    motivo_cancelamento     VARCHAR(255) NULL,
    id_usuario_solicitante  INT UNSIGNED NULL,
    criado_em               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    concluido_em            DATETIME     NULL,
    PRIMARY KEY (id_os),
    KEY idx_os_data (data, hora_inicio),
    KEY idx_os_empresa (id_empresa, status),
    KEY idx_os_status (status),
    CONSTRAINT fk_os_empresa FOREIGN KEY (id_empresa) REFERENCES empresa (id_empresa),
    CONSTRAINT fk_os_dispositivo FOREIGN KEY (id_dispositivo) REFERENCES dispositivo (id_dispositivo),
    CONSTRAINT fk_os_tipo FOREIGN KEY (id_tipo_servico) REFERENCES tipo_servico (id_tipo_servico),
    CONSTRAINT fk_os_tecnico FOREIGN KEY (id_tecnico) REFERENCES tecnico (id_tecnico),
    CONSTRAINT fk_os_usuario FOREIGN KEY (id_usuario_solicitante) REFERENCES usuario (id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
