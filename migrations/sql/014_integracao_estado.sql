-- Estado de integrações (chave/valor): token OAuth da eWeLink (criptografado), state do OAuth em andamento
-- e pausa da coleta por limite da API. Substitui os arquivos storage/*.json do Brain. Idempotente.
CREATE TABLE IF NOT EXISTS integracao_estado (
    chave           VARCHAR(60)  NOT NULL,
    valor           TEXT         NULL,
    atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (chave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
