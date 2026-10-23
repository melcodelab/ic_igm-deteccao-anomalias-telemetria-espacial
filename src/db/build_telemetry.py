"""
ETL de Carga de Séries Temporais e Telecomandos.
Gera os bancos esa_m1.sqlite e esa_m2.sqlite:
- Telemetria multivariada em tabela larga indexada por ts (inteiro em ms UTC).
- Execuções de telecomandos indexadas por (telecommand, ts) e (ts, telecommand).
- Metadados de auditoria e validação de integridade.
"""

from __future__ import annotations

import glob
import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .connection import get_connection, get_db_path, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_telemetry")


def load_zip_pickle(path: Path) -> pd.DataFrame:
    """Carrega DataFrame serializado com pickle dentro de um arquivo .zip."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if not names:
            raise ValueError(f"Arquivo zip vazio: {path}")
        with z.open(names[0]) as f:
            return pd.read_pickle(f)


def build_telemetry_m1(
    m1_dir: Path,
    db_dir: Optional[Path] = None,
    batch_size: int = 250_000,
    recreate: bool = True,
) -> Path:
    """
    Constrói o banco esa_m1.sqlite:
    - Lê canais 41 a 46 de m1_dir/channels/channel_*.zip.
    - Valida estritamente se todos os canais possuem os mesmos timestamps.
    - Grava em tabela larga telemetry(ts, channel_41, ..., channel_46).
    - Lê todos os telecommands de m1_dir/telecommands/telecommand_*.zip e grava em tc_executions.
    """
    m1_path = Path(m1_dir)
    if not (m1_path / "channels").exists() and (m1_path / "ESA-Mission1" / "channels").exists():
        m1_path = m1_path / "ESA-Mission1"
    channels_dir = m1_path / "channels"
    tc_dir = m1_path / "telecommands"
    
    if not channels_dir.exists():
        raise FileNotFoundError(f"Pasta de canais não encontrada: {channels_dir}")
        
    logger.info("Iniciando construção de esa_m1.sqlite...")
    if recreate:
        init_db("esa_m1", "schema_m1.sql", db_dir=db_dir, recreate=True)
        
    conn = get_connection("esa_m1", read_only=False, db_dir=db_dir)
    
    # Otimizações de I/O para carga inicial em massa
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    
    channel_ids = [41, 42, 43, 44, 45, 46]
    channel_names = [f"channel_{cid}" for cid in channel_ids]
    
    try:
        # 1. Carrega canal de referência para obter timestamps
        ref_cid = channel_ids[0]
        ref_path = channels_dir / f"channel_{ref_cid}.zip"
        logger.info(f"[M1] Carregando canal de referência: {ref_path.name}...")
        df_ref = load_zip_pickle(ref_path)
        
        n_rows = len(df_ref)
        ref_index = df_ref.index
        logger.info(f"[M1] Leituras encontradas: {n_rows:,} registros.")
        
        # Converte índice DatetimeIndex para inteiros epoch ms
        if ref_index.tz is None:
            # DatetimeIndex ingênuo: trata como UTC
            ts_ms = ref_index.view("int64") // 1_000_000
        else:
            ts_ms = ref_index.tz_convert("UTC").view("int64") // 1_000_000
            
        data_matrix = np.zeros((n_rows, len(channel_ids)), dtype=np.float64)
        data_matrix[:, 0] = df_ref.iloc[:, 0].values.astype(np.float64)
        del df_ref
        
        # Carrega os demais canais e valida alinhamento de timestamps
        for idx, cid in enumerate(channel_ids[1:], start=1):
            ch_path = channels_dir / f"channel_{cid}.zip"
            logger.info(f"[M1] Carregando e validando canal: {ch_path.name}...")
            df_ch = load_zip_pickle(ch_path)
            
            if len(df_ch) != n_rows:
                raise ValueError(
                    f"[M1] Erro de integridade: {ch_path.name} tem {len(df_ch)} linhas, esperado {n_rows}."
                )
            if not df_ch.index.equals(ref_index):
                raise ValueError(
                    f"[M1] Erro de alinhamento: Timestamps de {ch_path.name} não coincidem com {ref_path.name}."
                )
                
            data_matrix[:, idx] = df_ch.iloc[:, 0].values.astype(np.float64)
            del df_ch

        # 2. Inserção em lotes na tabela 'telemetry'
        logger.info(f"[M1] Inserindo {n_rows:,} registros na tabela 'telemetry'...")
        insert_sql = """
        INSERT INTO telemetry (ts, channel_41, channel_42, channel_43, channel_44, channel_45, channel_46)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        
        with conn:
            for start in range(0, n_rows, batch_size):
                end = min(start + batch_size, n_rows)
                batch_ts = ts_ms[start:end]
                batch_data = data_matrix[start:end, :]
                
                batch_tuples = [
                    (int(batch_ts[i]), float(batch_data[i, 0]), float(batch_data[i, 1]),
                     float(batch_data[i, 2]), float(batch_data[i, 3]), float(batch_data[i, 4]),
                     float(batch_data[i, 5]))
                    for i in range(end - start)
                ]
                conn.executemany(insert_sql, batch_tuples)
                if (start // batch_size) % 10 == 0 or end == n_rows:
                    logger.info(f"[M1] Telemetria: {end:,} / {n_rows:,} linhas gravadas.")
                    
        del data_matrix, ts_ms, ref_index

        # 3. Carga de telecomandos
        if tc_dir.exists():
            tc_files = sorted(tc_dir.glob("telecommand_*.zip"))
            logger.info(f"[M1] Carregando execuções de {len(tc_files)} telecomandos...")
            
            tc_records = []
            tc_insert_sql = "INSERT OR IGNORE INTO tc_executions (telecommand, ts) VALUES (?, ?);"
            
            for f_path in tc_files:
                tc_name = f_path.stem
                df_tc = load_zip_pickle(f_path)
                if df_tc.empty:
                    continue
                tc_idx = df_tc.index
                if tc_idx.tz is None:
                    t_ms = tc_idx.view("int64") // 1_000_000
                else:
                    t_ms = tc_idx.tz_convert("UTC").view("int64") // 1_000_000
                    
                for t in t_ms:
                    tc_records.append((tc_name, int(t)))
                    
                if len(tc_records) >= batch_size:
                    with conn:
                        conn.executemany(tc_insert_sql, tc_records)
                    tc_records.clear()
                    
            if tc_records:
                with conn:
                    conn.executemany(tc_insert_sql, tc_records)
                tc_records.clear()
                
            cur = conn.execute("SELECT COUNT(*) AS total FROM tc_executions;")
            total_tcs = cur.fetchone()["total"]
            logger.info(f"[M1] Total de execuções de telecomandos gravadas: {total_tcs:,}.")

        # 4. Gravação de metadados
        cur = conn.execute("SELECT MIN(ts) AS min_ts, MAX(ts) AS max_ts, COUNT(*) AS total FROM telemetry;")
        row_stat = cur.fetchone()
        
        meta_records = [
            ("mission", "M1"),
            ("n_leituras", str(row_stat["total"])),
            ("inicio_ts", str(row_stat["min_ts"])),
            ("fim_ts", str(row_stat["max_ts"])),
            ("data_carga", datetime.now(timezone.utc).isoformat()),
            ("versao_esquema", "1"),
        ]
        with conn:
            conn.executemany("INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?);", meta_records)
        
        # 5. Otimizações pós-carga e análise
        logger.info("[M1] Finalizando banco e gerando estatísticas do planejador (ANALYZE)...")
        conn.commit()
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("ANALYZE;")
        logger.info("[M1] Carga de esa_m1.sqlite concluída com sucesso.")

    finally:
        conn.close()
        
    return get_db_path("esa_m1", db_dir=db_dir)


def build_telemetry_m2(
    m2_dir: Path,
    db_dir: Optional[Path] = None,
    batch_size: int = 250_000,
    recreate: bool = True,
) -> Path:
    """
    Constrói o banco esa_m2.sqlite:
    - Lê canais 18 a 28 de m2_dir/channels/channel_*.zip.
    - Valida timestamps e grava na tabela larga telemetry.
    - Lê telecomandos e grava em tc_executions.
    """
    m2_path = Path(m2_dir)
    if not (m2_path / "channels").exists() and (m2_path / "ESA-Mission2" / "channels").exists():
        m2_path = m2_path / "ESA-Mission2"
    channels_dir = m2_path / "channels"
    tc_dir = m2_path / "telecommands"
    
    if not channels_dir.exists():
        raise FileNotFoundError(f"Pasta de canais não encontrada: {channels_dir}")
        
    logger.info("Iniciando construção de esa_m2.sqlite...")
    if recreate:
        init_db("esa_m2", "schema_m2.sql", db_dir=db_dir, recreate=True)
        
    conn = get_connection("esa_m2", read_only=False, db_dir=db_dir)
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    
    channel_ids = list(range(18, 29))
    
    try:
        ref_cid = channel_ids[0]
        ref_path = channels_dir / f"channel_{ref_cid}.zip"
        logger.info(f"[M2] Carregando canal de referência: {ref_path.name}...")
        df_ref = load_zip_pickle(ref_path)
        
        n_rows = len(df_ref)
        ref_index = df_ref.index
        logger.info(f"[M2] Leituras encontradas: {n_rows:,} registros.")
        
        if ref_index.tz is None:
            ts_ms = ref_index.view("int64") // 1_000_000
        else:
            ts_ms = ref_index.tz_convert("UTC").view("int64") // 1_000_000
            
        data_matrix = np.zeros((n_rows, len(channel_ids)), dtype=np.float64)
        data_matrix[:, 0] = df_ref.iloc[:, 0].values.astype(np.float64)
        del df_ref
        
        for idx, cid in enumerate(channel_ids[1:], start=1):
            ch_path = channels_dir / f"channel_{cid}.zip"
            logger.info(f"[M2] Carregando e validando canal: {ch_path.name}...")
            df_ch = load_zip_pickle(ch_path)
            
            if len(df_ch) != n_rows:
                raise ValueError(
                    f"[M2] Erro: {ch_path.name} tem {len(df_ch)} linhas, esperado {n_rows}."
                )
            if not df_ch.index.equals(ref_index):
                raise ValueError(
                    f"[M2] Erro: Timestamps de {ch_path.name} não coincidem com {ref_path.name}."
                )
                
            data_matrix[:, idx] = df_ch.iloc[:, 0].values.astype(np.float64)
            del df_ch

        cols = ["ts"] + [f"channel_{cid}" for cid in channel_ids]
        insert_sql = f"INSERT INTO telemetry ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))});"
        
        logger.info(f"[M2] Inserindo {n_rows:,} registros na tabela 'telemetry'...")
        with conn:
            for start in range(0, n_rows, batch_size):
                end = min(start + batch_size, n_rows)
                batch_ts = ts_ms[start:end]
                batch_data = data_matrix[start:end, :]
                
                batch_tuples = [
                    (int(batch_ts[i]),) + tuple(float(batch_data[i, j]) for j in range(len(channel_ids)))
                    for i in range(end - start)
                ]
                conn.executemany(insert_sql, batch_tuples)
                if (start // batch_size) % 10 == 0 or end == n_rows:
                    logger.info(f"[M2] Telemetria: {end:,} / {n_rows:,} linhas gravadas.")
                    
        del data_matrix, ts_ms, ref_index

        if tc_dir.exists():
            tc_files = sorted(tc_dir.glob("telecommand_*.zip"))
            logger.info(f"[M2] Carregando execuções de {len(tc_files)} telecomandos...")
            tc_records = []
            tc_insert_sql = "INSERT OR IGNORE INTO tc_executions (telecommand, ts) VALUES (?, ?);"
            
            for f_path in tc_files:
                tc_name = f_path.stem
                df_tc = load_zip_pickle(f_path)
                if df_tc.empty:
                    continue
                tc_idx = df_tc.index
                t_ms = tc_idx.view("int64") // 1_000_000 if tc_idx.tz is None else tc_idx.tz_convert("UTC").view("int64") // 1_000_000
                for t in t_ms:
                    tc_records.append((tc_name, int(t)))
                    
                if len(tc_records) >= batch_size:
                    with conn:
                        conn.executemany(tc_insert_sql, tc_records)
                    tc_records.clear()
                    
            if tc_records:
                with conn:
                    conn.executemany(tc_insert_sql, tc_records)
                tc_records.clear()

        # 4. Grava metadados da carga
        row_stat = conn.execute(
            "SELECT COUNT(*) AS total, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM telemetry;"
        ).fetchone()
        meta_records = [
            ("missao", "M2"),
            ("n_leituras", str(row_stat["total"])),
            ("inicio_ts", str(row_stat["min_ts"])),
            ("fim_ts", str(row_stat["max_ts"])),
            ("data_carga", datetime.now(timezone.utc).isoformat()),
            ("versao_esquema", "1"),
        ]
        with conn:
            conn.executemany("INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?);", meta_records)

        conn.commit()
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("ANALYZE;")
        logger.info("[M2] Carga de esa_m2.sqlite concluída com sucesso.")

    finally:
        conn.close()
        
    return get_db_path("esa_m2", db_dir=db_dir)
