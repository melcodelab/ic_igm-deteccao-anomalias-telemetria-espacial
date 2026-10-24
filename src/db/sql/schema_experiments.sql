-- ==============================================================================
-- Arquitetura do Banco de Dados — ESA-ADB (MCP + Autoencoder)
-- Banco 3: esa_experiments.sqlite
-- Repositório dinâmico para rastrear experimentos, scores, alertas e métricas.
-- ==============================================================================

PRAGMA foreign_keys = ON;

-- 1. Execuções do modelo (runs)
CREATE TABLE IF NOT EXISTS runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mission          TEXT NOT NULL,                -- 'M1' | 'M2'
    modelo           TEXT NOT NULL,                -- 'autoencoder_v1', 'baseline_mad'
    canais           TEXT NOT NULL,                -- lista JSON: ["channel_41", ...]
    split_id         TEXT NOT NULL,                -- referencia esa_catalog.splits
    janela_len       INTEGER NOT NULL,             -- nº de leituras por janela
    passo            INTEGER NOT NULL,             -- deslocamento entre janelas
    hiperparametros  TEXT,                         -- JSON: camadas, lr, épocas, batch_size...
    limiar_metodo    TEXT,                         -- 'p99_val', 'mad_3x'
    limiar_valor     REAL,
    seed             INTEGER,
    commit_git       TEXT,
    criado_em        TEXT NOT NULL,                -- ISO 8601
    observacao       TEXT
);

-- 2. Parâmetros de normalização calculados exclusivamente no treino
CREATE TABLE IF NOT EXISTS run_norm (
    run_id   INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    channel  TEXT    NOT NULL,
    mediana  REAL    NOT NULL,
    escala   REAL    NOT NULL,                     -- p.ex. MAD * 1.4826
    PRIMARY KEY (run_id, channel)
);

-- 3. Scores de anomalia calculados por janela
CREATE TABLE IF NOT EXISTS run_scores (
    run_id    INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ts_fim    INTEGER NOT NULL,                    -- ms UTC da última leitura da janela
    score     REAL    NOT NULL,
    PRIMARY KEY (run_id, ts_fim)
) WITHOUT ROWID;

-- 4. Episódios de alerta consolidados
CREATE TABLE IF NOT EXISTS alerts (
    alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    inicio_ts   INTEGER NOT NULL,                  -- ms UTC
    fim_ts      INTEGER NOT NULL,                  -- ms UTC
    pico_score  REAL    NOT NULL,
    n_janelas   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_run_tempo ON alerts(run_id, inicio_ts);

-- 5. Cruzamento entre alertas e eventos anotados conhecidos
CREATE TABLE IF NOT EXISTS alert_matches (
    alert_id         INTEGER NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    event_id         TEXT    NOT NULL,             -- referencia esa_catalog.events
    category         TEXT    NOT NULL,             -- Anomaly, Rare Event
    sobreposicao_s   REAL    NOT NULL,
    PRIMARY KEY (alert_id, event_id)
);

-- 6. Contexto de telecomandos que antecederam o alerta
CREATE TABLE IF NOT EXISTS alert_context (
    alert_id        INTEGER NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    telecommand     TEXT    NOT NULL,
    n_exec_antes    INTEGER NOT NULL,
    min_antes_s     REAL,
    janela_horas    INTEGER NOT NULL,
    PRIMARY KEY (alert_id, telecommand, janela_horas)
);

-- 7. Métricas de avaliação por run e escopo
CREATE TABLE IF NOT EXISTS metrics (
    run_id    INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    escopo    TEXT    NOT NULL,                    -- 'geral' | 'Anomaly' | 'Rare Event'
    metrica   TEXT    NOT NULL,                    -- 'recall_evento', 'n_alertas', 'alarming_precision'
    valor     REAL    NOT NULL,
    PRIMARY KEY (run_id, escopo, metrica)
);

-- 8. Auditoria das explicações produzidas pelo copiloto MCP
CREATE TABLE IF NOT EXISTS explanations (
    explanation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id        INTEGER,
    run_id          INTEGER REFERENCES runs(run_id) ON DELETE SET NULL,
    tool_name       TEXT NOT NULL,
    pacote_json     TEXT NOT NULL,
    resposta_bruta  TEXT NOT NULL,
    verificador_ok  INTEGER NOT NULL CHECK (verificador_ok IN (0,1)),
    regras_violadas TEXT NOT NULL DEFAULT '[]',
    modelo_llm      TEXT NOT NULL,
    temperatura     REAL,
    criado_em       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_explanations_alert ON explanations(alert_id);
CREATE INDEX IF NOT EXISTS idx_explanations_created ON explanations(criado_em);
