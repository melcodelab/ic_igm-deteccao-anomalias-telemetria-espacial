-- ==============================================================================
-- Arquitetura do Banco de Dados — ESA-ADB (MCP + Autoencoder)
-- Banco 1: esa_catalog.sqlite
-- Catálogo centralizado, relacional e unificado para Mission1 e Mission2.
-- ==============================================================================

PRAGMA foreign_keys = ON;

-- 1. Missões cadastradas
CREATE TABLE IF NOT EXISTS missions (
    mission             TEXT PRIMARY KEY,          -- 'M1' ou 'M2'
    nome                TEXT NOT NULL,             -- 'ESA-Mission1'
    inicio_ts           INTEGER NOT NULL,          -- primeira leitura (ms UTC epoch)
    fim_ts              INTEGER NOT NULL,          -- última leitura (ms UTC epoch)
    n_leituras          INTEGER NOT NULL,
    cadencia_mediana_s  REAL,                      -- p.ex. 30.0 (M1), 18.0 (M2)
    observacao          TEXT
);

-- 2. Canais de telemetria (sensores)
CREATE TABLE IF NOT EXISTS channels (
    mission        TEXT NOT NULL REFERENCES missions(mission),
    channel        TEXT NOT NULL,                  -- 'channel_41', 'channel_18'
    subsystem      TEXT,
    physical_unit  TEXT,                           -- pode ser NULL
    grp            INTEGER,                        -- 'Group' do CSV original
    is_target      INTEGER NOT NULL CHECK (is_target IN (0,1)),
    no_recorte     INTEGER NOT NULL DEFAULT 0 CHECK (no_recorte IN (0,1)), -- 1 = canal com telemetria carregada
    PRIMARY KEY (mission, channel)
);

-- 3. Catálogo de tipos de telecomandos
CREATE TABLE IF NOT EXISTS telecommands (
    mission      TEXT NOT NULL REFERENCES missions(mission),
    telecommand  TEXT NOT NULL,                    -- 'telecommand_38', 'telecommand_57'
    priority     INTEGER,                          -- código Priority original
    PRIMARY KEY (mission, telecommand)
);

-- 4. Classificação dos eventos anotados
CREATE TABLE IF NOT EXISTS event_types (
    mission         TEXT NOT NULL REFERENCES missions(mission),
    event_id        TEXT NOT NULL,                 -- 'id_1', 'id_100'
    category        TEXT NOT NULL,                 -- 'Anomaly' | 'Rare Event' | 'Communication Gap'
    class           TEXT,
    subclass        TEXT,
    dimensionality  TEXT,                          -- calculada para a missão inteira
    locality        TEXT,
    length          TEXT,
    PRIMARY KEY (mission, event_id)
);

-- 5. Rótulos de eventos (intervalos anotados por canal)
CREATE TABLE IF NOT EXISTS labels (
    label_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    mission          TEXT NOT NULL,
    event_id         TEXT NOT NULL,
    channel          TEXT NOT NULL,
    start_ts         INTEGER,                      -- NULL se data original ilegível
    end_ts           INTEGER,                      -- NULL se data original ilegível
    start_raw        TEXT,                         -- valor original do CSV
    end_raw          TEXT,
    valido           INTEGER NOT NULL CHECK (valido IN (0,1)),
    motivo_invalido  TEXT,                         -- 'data_ilegivel' | 'fim_antes_do_inicio' | 'id_ausente' | NULL
    FOREIGN KEY (mission, event_id) REFERENCES event_types(mission, event_id),
    FOREIGN KEY (mission, channel)  REFERENCES channels(mission, channel)
);

CREATE INDEX IF NOT EXISTS idx_labels_canal_tempo ON labels(mission, channel, start_ts, end_ts);
CREATE INDEX IF NOT EXISTS idx_labels_evento      ON labels(mission, event_id);

-- 6. Eventos consolidados (derivada de labels nos canais do recorte)
CREATE TABLE IF NOT EXISTS events (
    mission                 TEXT NOT NULL,
    event_id                TEXT NOT NULL,
    category                TEXT NOT NULL,
    class                   TEXT,
    start_ts                INTEGER NOT NULL,      -- primeiro início entre canais do recorte (ms UTC)
    end_ts                  INTEGER NOT NULL,      -- último fim (ms UTC)
    n_canais                INTEGER NOT NULL,      -- canais distintos afetados
    n_intervalos            INTEGER NOT NULL,      -- total de linhas em labels
    PRIMARY KEY (mission, event_id),
    FOREIGN KEY (mission, event_id) REFERENCES event_types(mission, event_id)
);

CREATE INDEX IF NOT EXISTS idx_events_tempo ON events(mission, start_ts);
CREATE INDEX IF NOT EXISTS idx_events_cat   ON events(mission, category);

-- 7. Divisões formais de treino / validação / teste
CREATE TABLE IF NOT EXISTS splits (
    mission     TEXT NOT NULL REFERENCES missions(mission),
    split_id    TEXT NOT NULL,                     -- 'metade_temporal', 'balanceado_m2'
    papel       TEXT NOT NULL CHECK (papel IN ('train','val','test')),
    inicio_ts   INTEGER NOT NULL,                  -- intervalo [inicio_ts, fim_ts)
    fim_ts      INTEGER NOT NULL,
    descricao   TEXT,
    PRIMARY KEY (mission, split_id, papel, inicio_ts)
);

-- 8. Janelas contextuais anteriores e janelas de referência sem eventos
CREATE TABLE IF NOT EXISTS event_windows (
    mission     TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    horas       INTEGER NOT NULL,                  -- 1, 6 ou 24
    tipo        TEXT NOT NULL CHECK (tipo IN ('evento','referencia')),
    inicio_ts   INTEGER NOT NULL,
    fim_ts      INTEGER NOT NULL,
    PRIMARY KEY (mission, event_id, horas, tipo),
    FOREIGN KEY (mission, event_id) REFERENCES events(mission, event_id)
);

CREATE INDEX IF NOT EXISTS idx_windows_tempo ON event_windows(mission, inicio_ts, fim_ts);
