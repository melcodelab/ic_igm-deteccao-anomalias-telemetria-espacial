-- ==============================================================================
-- Arquitetura do Banco de Dados — ESA-ADB (MCP + Autoencoder)
-- Banco 2A: esa_m1.sqlite
-- Dados brutos e imutáveis da Mission1 (Canais 41 a 46).
-- ==============================================================================

-- Tabela larga de telemetria: uma linha por instante de amostragem
CREATE TABLE IF NOT EXISTS telemetry (
    ts          INTEGER PRIMARY KEY,               -- ms UTC (epoch)
    channel_41  REAL,
    channel_42  REAL,
    channel_43  REAL,
    channel_44  REAL,
    channel_45  REAL,
    channel_46  REAL
);

-- Execuções de telecomando
CREATE TABLE IF NOT EXISTS tc_executions (
    telecommand  TEXT    NOT NULL,                 -- 'telecommand_38'
    ts           INTEGER NOT NULL,                 -- ms UTC (epoch)
    PRIMARY KEY (telecommand, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_tc_ts ON tc_executions(ts, telecommand);

-- Metadados de auditoria e controle de carga
CREATE TABLE IF NOT EXISTS meta (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);
