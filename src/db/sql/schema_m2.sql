-- ==============================================================================
-- Arquitetura do Banco de Dados — ESA-ADB (MCP + Autoencoder)
-- Banco 2B: esa_m2.sqlite
-- Dados brutos e imutáveis da Mission2 (Canais 18 a 28).
-- ==============================================================================

-- Tabela larga de telemetria: uma linha por instante de amostragem
CREATE TABLE IF NOT EXISTS telemetry (
    ts          INTEGER PRIMARY KEY,               -- ms UTC (epoch)
    channel_18  REAL,
    channel_19  REAL,
    channel_20  REAL,
    channel_21  REAL,
    channel_22  REAL,
    channel_23  REAL,
    channel_24  REAL,
    channel_25  REAL,
    channel_26  REAL,
    channel_27  REAL,
    channel_28  REAL
);

-- Execuções de telecomando
CREATE TABLE IF NOT EXISTS tc_executions (
    telecommand  TEXT    NOT NULL,                 -- 'telecommand_57'
    ts           INTEGER NOT NULL,                 -- ms UTC (epoch)
    PRIMARY KEY (telecommand, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_tc_ts ON tc_executions(ts, telecommand);

-- Metadados de auditoria e controle de carga
CREATE TABLE IF NOT EXISTS meta (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);
