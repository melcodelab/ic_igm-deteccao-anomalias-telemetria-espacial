"""
ETL de Construção do Catálogo Unificado: esa_catalog.sqlite
Centraliza metadados, canais, telecomandos, auditoria de rótulos,
derivação de envelopes de eventos, janelas de referência e splits.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .connection import get_connection, get_db_path, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_catalog")

# Configuração dos canais do recorte oficial
CHANNELS_RECORTE = {
    "M1": [f"channel_{i}" for i in range(41, 47)],      # channel_41 a channel_46
    "M2": [f"channel_{i}" for i in range(18, 29)],      # channel_18 a channel_28
}

MISSION_DEFAULTS = {
    "M1": {
        "nome": "ESA-Mission1",
        "inicio_iso": "2000-01-01T00:00:00Z",
        "fim_iso": "2013-12-31T23:59:30Z",
        "n_leituras": 15381169,
        "cadencia_mediana_s": 30.0,
        "observacao": "Séries dos canais 41 a 46 carregadas (6 de 76 canais totais).",
    },
    "M2": {
        "nome": "ESA-Mission2",
        "inicio_iso": "2000-01-01T00:00:00Z",
        "fim_iso": "2003-06-30T23:59:42Z",
        "n_leituras": 7387262,
        "cadencia_mediana_s": 18.0,
        "observacao": "Séries dos canais 18 a 28 carregadas (11 de 100 canais totais).",
    },
}


def iso_to_ms(iso_str: str) -> Optional[int]:
    """Converte string ISO 8601 (UTC) para timestamp epoch inteiro em milissegundos."""
    if not isinstance(iso_str, str) or not iso_str.strip():
        return None
    try:
        dt = pd.to_datetime(iso_str, utc=True)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def populate_missions(conn: sqlite3.Connection) -> None:
    """Insere os registros mestre de cada missão."""
    logger.info("Populando tabela 'missions'...")
    sql = """
    INSERT OR REPLACE INTO missions (mission, nome, inicio_ts, fim_ts, n_leituras, cadencia_mediana_s, observacao)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    for code, m in MISSION_DEFAULTS.items():
        inicio_ts = iso_to_ms(m["inicio_iso"])
        fim_ts = iso_to_ms(m["fim_iso"])
        conn.execute(
            sql,
            (
                code,
                m["nome"],
                inicio_ts,
                fim_ts,
                m["n_leituras"],
                m["cadencia_mediana_s"],
                m["observacao"],
            ),
        )


def load_channels(conn: sqlite3.Connection, mission: str, channels_csv_path: Path) -> int:
    """Carrega o catálogo completo de canais e marca no_recorte."""
    logger.info(f"[{mission}] Carregando canais de: {channels_csv_path}")
    df = pd.read_csv(channels_csv_path)
    
    recorte_set = set(CHANNELS_RECORTE.get(mission, []))
    records = []
    
    for _, row in df.iterrows():
        channel = str(row["Channel"]).strip()
        subsystem = str(row["Subsystem"]).strip() if pd.notna(row.get("Subsystem")) else None
        phys_unit = str(row["PhysicalUnit"]).strip() if pd.notna(row.get("PhysicalUnit")) else None
        grp = int(row["Group"]) if pd.notna(row.get("Group")) else None
        target_str = str(row.get("Target", "")).strip().upper()
        is_target = 1 if target_str == "YES" else 0
        no_recorte = 1 if channel in recorte_set else 0
        
        records.append((mission, channel, subsystem, phys_unit, grp, is_target, no_recorte))
        
    sql = """
    INSERT OR REPLACE INTO channels (mission, channel, subsystem, physical_unit, grp, is_target, no_recorte)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    conn.executemany(sql, records)
    logger.info(f"[{mission}] {len(records)} canais inseridos (no_recorte=1: {len(recorte_set)}).")
    return len(records)


def load_telecommands(conn: sqlite3.Connection, mission: str, tc_csv_path: Path) -> int:
    """Carrega catálogo de telecomandos."""
    logger.info(f"[{mission}] Carregando metadados de telecomandos de: {tc_csv_path}")
    df = pd.read_csv(tc_csv_path)
    
    records = []
    for _, row in df.iterrows():
        tc_name = str(row["Telecommand"]).strip()
        prio = int(row["Priority"]) if pd.notna(row.get("Priority")) else None
        records.append((mission, tc_name, prio))
        
    sql = """
    INSERT OR REPLACE INTO telecommands (mission, telecommand, priority)
    VALUES (?, ?, ?);
    """
    conn.executemany(sql, records)
    logger.info(f"[{mission}] {len(records)} tipos de telecomando inseridos.")
    return len(records)


def load_event_types(conn: sqlite3.Connection, mission: str, anomaly_types_csv_path: Path) -> int:
    """Carrega as categorias e tipos de eventos anotados."""
    logger.info(f"[{mission}] Carregando anomaly_types de: {anomaly_types_csv_path}")
    df = pd.read_csv(anomaly_types_csv_path)
    
    records = []
    for _, row in df.iterrows():
        event_id = str(row["ID"]).strip()
        category = str(row["Category"]).strip()
        cls = str(row["Class"]).strip() if pd.notna(row.get("Class")) else None
        subcls = str(row["Subclass"]).strip() if pd.notna(row.get("Subclass")) else None
        dim = str(row["Dimensionality"]).strip() if pd.notna(row.get("Dimensionality")) else None
        loc = str(row["Locality"]).strip() if pd.notna(row.get("Locality")) else None
        length = str(row["Length"]).strip() if pd.notna(row.get("Length")) else None
        
        records.append((mission, event_id, category, cls, subcls, dim, loc, length))
        
    sql = """
    INSERT OR REPLACE INTO event_types (mission, event_id, category, class, subclass, dimensionality, locality, length)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """
    conn.executemany(sql, records)
    logger.info(f"[{mission}] {len(records)} tipos de evento inseridos.")
    return len(records)


def load_and_audit_labels(conn: sqlite3.Connection, mission: str, labels_csv_path: Path) -> Tuple[int, int]:
    """
    Carrega labels.csv com auditoria rigorosa:
    - Nenhuma linha é descartada.
    - Campos brutos são preservados em start_raw e end_raw.
    - valido = 1 ou 0 com motivo_invalido preenchido.
    """
    logger.info(f"[{mission}] Carregando e auditando rótulos de: {labels_csv_path}")
    df = pd.read_csv(labels_csv_path)
    
    records = []
    n_validos = 0
    n_invalidos = 0
    
    for _, row in df.iterrows():
        raw_id = row.get("ID")
        event_id = str(raw_id).strip() if pd.notna(raw_id) else None
        raw_ch = row.get("Channel")
        channel = str(raw_ch).strip() if pd.notna(raw_ch) else None
        
        start_raw = str(row.get("StartTime", ""))
        end_raw = str(row.get("EndTime", ""))
        
        start_ts = iso_to_ms(start_raw)
        end_ts = iso_to_ms(end_raw)
        
        # Auditoria
        if not event_id:
            valido = 0
            motivo = "id_ausente"
        elif start_ts is None or end_ts is None:
            valido = 0
            motivo = "data_ilegivel"
        elif end_ts < start_ts:
            valido = 0
            motivo = "fim_antes_do_inicio"
        else:
            valido = 1
            motivo = None
            
        if valido == 1:
            n_validos += 1
        else:
            n_invalidos += 1
            
        records.append((mission, event_id, channel, start_ts, end_ts, start_raw, end_raw, valido, motivo))
        
    sql = """
    INSERT INTO labels (mission, event_id, channel, start_ts, end_ts, start_raw, end_raw, valido, motivo_invalido)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    conn.executemany(sql, records)
    logger.info(f"[{mission}] {len(records)} linhas de labels inseridas (Válidas: {n_validos}, Inválidas: {n_invalidos}).")
    return n_validos, n_invalidos


def derive_events(conn: sqlite3.Connection, mission: str) -> int:
    """
    Deriva a tabela 'events' agregando os envelopes temporais
    apenas dos rótulos válidos pertencentes aos canais do recorte.
    """
    logger.info(f"[{mission}] Derivando tabela 'events' a partir dos rótulos válidos no recorte...")
    sql = """
    INSERT OR REPLACE INTO events (mission, event_id, category, class, start_ts, end_ts, n_canais, n_intervalos)
    SELECT
        l.mission,
        l.event_id,
        et.category,
        et.class,
        MIN(l.start_ts) AS start_ts,
        MAX(l.end_ts) AS end_ts,
        COUNT(DISTINCT l.channel) AS n_canais,
        COUNT(*) AS n_intervalos
    FROM labels l
    JOIN channels c ON c.mission = l.mission AND c.channel = l.channel
    JOIN event_types et ON et.mission = l.mission AND et.event_id = l.event_id
    WHERE l.mission = ?
      AND l.valido = 1
      AND c.no_recorte = 1
    GROUP BY l.mission, l.event_id, et.category, et.class;
    """
    cur = conn.execute(sql, (mission,))
    n_events = cur.rowcount
    logger.info(f"[{mission}] {n_events} eventos consolidados derivados.")
    return n_events


def derive_event_windows(conn: sqlite3.Connection, mission: str) -> None:
    """
    Gera as janelas de 1 h, 6 h e 24 h anteriores ao evento
    e busca janelas de referência/controle sem eventos pareadas.
    """
    logger.info(f"[{mission}] Derivando janelas de evento e de referência (1h, 6h, 24h)...")
    
    # Busca limites da missão
    cur = conn.execute("SELECT inicio_ts, fim_ts FROM missions WHERE mission = ?", (mission,))
    m_info = cur.fetchone()
    mission_inicio_ts = m_info["inicio_ts"]
    
    # Carrega todos os intervalos proibidos (labels válidas de qualquer canal + envelopes)
    cur = conn.execute(
        "SELECT start_ts, end_ts FROM labels WHERE mission = ? AND valido = 1",
        (mission,)
    )
    forbidden_intervals = [(row["start_ts"], row["end_ts"]) for row in cur.fetchall()]
    
    # Carrega eventos da missão
    cur = conn.execute("SELECT event_id, start_ts, end_ts FROM events WHERE mission = ?", (mission,))
    events = cur.fetchall()
    
    records = []
    
    def overlaps_any(start: int, end: int) -> bool:
        for f_start, f_end in forbidden_intervals:
            if not (end < f_start or start > f_end):
                return True
        return False

    for ev in events:
        eid = ev["event_id"]
        ev_start = ev["start_ts"]
        
        for h in [1, 6, 24]:
            dur_ms = h * 3600 * 1000
            
            # 1. Janela do evento: termina exatamente no início do evento
            w_ev_start = ev_start - dur_ms
            w_ev_end = ev_start
            records.append((mission, eid, h, "evento", w_ev_start, w_ev_end))
            
            # 2. Janela de referência pareada: busca 1 a 4 semanas antes
            ref_found = False
            for week_shift in [1, 2, 3, 4]:
                shift_ms = week_shift * 7 * 24 * 3600 * 1000
                ref_start = w_ev_start - shift_ms
                ref_end = w_ev_end - shift_ms
                
                if ref_start >= mission_inicio_ts and not overlaps_any(ref_start, ref_end):
                    records.append((mission, eid, h, "referencia", ref_start, ref_end))
                    ref_found = True
                    break
                    
    sql = """
    INSERT OR REPLACE INTO event_windows (mission, event_id, horas, tipo, inicio_ts, fim_ts)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    conn.executemany(sql, records)
    logger.info(f"[{mission}] {len(records)} janelas contextuais registradas em 'event_windows'.")


def populate_splits(conn: sqlite3.Connection) -> None:
    """Registra as divisões oficiais e estratégicas de treino/validação/teste."""
    logger.info("Registrando splits em 'splits'...")
    splits_data = [
        # Mission 1 - Divisão oficial e 50/50
        (
            "M1",
            "metade_temporal",
            "train",
            iso_to_ms("2000-01-01T00:00:00Z"),
            iso_to_ms("2006-10-01T00:00:00Z"),
            "Treino inicial (7 anos = 84 meses oficiais do ESA-ADB)",
        ),
        (
            "M1",
            "metade_temporal",
            "val",
            iso_to_ms("2006-10-01T00:00:00Z"),
            iso_to_ms("2007-01-01T00:00:00Z"),
            "Validação oficial (últimos 3 meses do bloco de treino)",
        ),
        (
            "M1",
            "metade_temporal",
            "test",
            iso_to_ms("2007-01-01T00:00:00Z"),
            iso_to_ms("2013-12-31T23:59:59Z"),
            "Teste oficial (segunda metade, 7 anos)",
        ),
        # Mission 2 - Corte temporal clássico (50/50)
        (
            "M2",
            "metade_temporal",
            "train",
            iso_to_ms("2000-01-01T00:00:00Z"),
            iso_to_ms("2001-07-01T00:00:00Z"),
            "Treino inicial (21 meses oficiais do ESA-ADB)",
        ),
        (
            "M2",
            "metade_temporal",
            "val",
            iso_to_ms("2001-07-01T00:00:00Z"),
            iso_to_ms("2001-10-01T00:00:00Z"),
            "Validação (últimos 3 meses do primeiro período)",
        ),
        (
            "M2",
            "metade_temporal",
            "test",
            iso_to_ms("2001-10-01T00:00:00Z"),
            iso_to_ms("2003-06-30T23:59:59Z"),
            "Teste (segunda metade: ATENÇÃO, contém apenas 1 anomalia rotulada)",
        ),
        # Mission 2 - Split balanceado para garantir anomalias na validação e teste
        (
            "M2",
            "balanceado_m2",
            "train",
            iso_to_ms("2000-01-01T00:00:00Z"),
            iso_to_ms("2000-12-31T23:59:59Z"),
            "Treino ano 1 (puramente nominal)",
        ),
        (
            "M2",
            "balanceado_m2",
            "val",
            iso_to_ms("2001-01-01T00:00:00Z"),
            iso_to_ms("2001-06-30T23:59:59Z"),
            "Validação (contém anomalias e eventos raros)",
        ),
        (
            "M2",
            "balanceado_m2",
            "test",
            iso_to_ms("2001-07-01T00:00:00Z"),
            iso_to_ms("2003-06-30T23:59:59Z"),
            "Teste (período posterior estendido para avaliação robusta)",
        ),
    ]
    
    sql = """
    INSERT OR REPLACE INTO splits (mission, split_id, papel, inicio_ts, fim_ts, descricao)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    conn.executemany(sql, splits_data)
    logger.info(f"{len(splits_data)} partições registradas em 'splits'.")


def build_catalog_from_dir(
    m1_dir: Optional[Path] = None,
    m2_dir: Optional[Path] = None,
    db_dir: Optional[Path] = None,
    recreate: bool = True,
) -> Path:
    """
    Executa o pipeline completo de construção do catálogo centralizado esa_catalog.sqlite.
    """
    logger.info("Iniciando construção de esa_catalog.sqlite...")
    if recreate:
        init_db("esa_catalog", "schema_catalog.sql", db_dir=db_dir, recreate=True)
        
    conn = get_connection("esa_catalog", read_only=False, db_dir=db_dir)
    
    try:
        with conn:
            populate_missions(conn)
            populate_splits(conn)
            
            # Processa Mission 1 se diretório fornecido
            if m1_dir and Path(m1_dir).exists():
                m1_path = Path(m1_dir)
                load_channels(conn, "M1", m1_path / "channels.csv")
                load_telecommands(conn, "M1", m1_path / "telecommands.csv")
                load_event_types(conn, "M1", m1_path / "anomaly_types.csv")
                load_and_audit_labels(conn, "M1", m1_path / "labels.csv")
                derive_events(conn, "M1")
                derive_event_windows(conn, "M1")
                
            # Processa Mission 2 se diretório fornecido
            if m2_dir and Path(m2_dir).exists():
                m2_path = Path(m2_dir)
                load_channels(conn, "M2", m2_path / "channels.csv")
                load_telecommands(conn, "M2", m2_path / "telecommands.csv")
                load_event_types(conn, "M2", m2_path / "anomaly_types.csv")
                load_and_audit_labels(conn, "M2", m2_path / "labels.csv")
                derive_events(conn, "M2")
                derive_event_windows(conn, "M2")
                
            conn.execute("ANALYZE;")
            logger.info("Catálogo finalizado e analisado com sucesso.")
            
    finally:
        conn.close()
        
    return get_db_path("esa_catalog", db_dir=db_dir)
