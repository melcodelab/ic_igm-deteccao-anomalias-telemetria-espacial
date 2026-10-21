"""
Gerenciamento de conexões SQLite para o projeto ESA-ADB.
Suporta conexões URI (modo somente leitura), PRAGMAs otimizados e junções multi-banco com ATTACH.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

# Diretório padrão onde residem os bancos SQLite
DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "db"
DEFAULT_SQL_DIR = Path(__file__).resolve().parent / "sql"


def ensure_db_dir(db_dir: Optional[Path] = None) -> Path:
    """Garante que o diretório de bancos de dados exista."""
    target_dir = Path(db_dir) if db_dir else DEFAULT_DB_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def get_db_path(db_name: str, db_dir: Optional[Path] = None) -> Path:
    """Retorna o caminho absoluto de um arquivo de banco de dados."""
    base_dir = ensure_db_dir(db_dir)
    filename = db_name if db_name.endswith(".sqlite") else f"{db_name}.sqlite"
    return base_dir / filename


def get_connection(
    db_name: str,
    read_only: bool = False,
    wal_mode: bool = False,
    db_dir: Optional[Path] = None,
) -> sqlite3.Connection:
    """
    Abre uma conexão com um banco SQLite especificado.
    
    Args:
        db_name: Nome do banco (ex: 'esa_catalog', 'esa_m1', 'esa_experiments').
        read_only: Se True, abre em modo somente leitura via URI (?mode=ro) e ativa query_only.
        wal_mode: Se True, ativa journal_mode=WAL (útil para o banco de experimentos concorrente).
        db_dir: Diretório opcional dos bancos.
    """
    db_path = get_db_path(db_name, db_dir)
    
    if read_only:
        if not db_path.exists():
            raise FileNotFoundError(f"Banco de dados não encontrado para leitura: {db_path}")
        uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = ON;")
    else:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        if wal_mode:
            conn.execute("PRAGMA journal_mode = WAL;")
        else:
            conn.execute("PRAGMA journal_mode = DELETE;")
            
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_name: str, schema_sql_file: str, db_dir: Optional[Path] = None, recreate: bool = False) -> Path:
    """
    Executa o script DDL SQL para inicializar ou recriar as tabelas de um banco.
    """
    db_path = get_db_path(db_name, db_dir)
    if recreate and db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
            
    sql_path = DEFAULT_SQL_DIR / schema_sql_file
    if not sql_path.exists():
        raise FileNotFoundError(f"Arquivo DDL SQL não encontrado: {sql_path}")
        
    with open(sql_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    conn = get_connection(db_name, read_only=False, wal_mode=(db_name == "esa_experiments"), db_dir=db_dir)
    try:
        with conn:
            conn.executescript(schema_sql)
    finally:
        conn.close()
        
    return db_path


def get_attached_connection(
    db_dir: Optional[Path] = None,
    attach_m1: bool = True,
    attach_m2: bool = True,
    attach_exp: bool = True,
    read_only: bool = True,
) -> sqlite3.Connection:
    """
    Abre conexão com o catálogo e anexa os demais bancos via ATTACH DATABASE.
    Permite queries relacionais cruzadas entre catálogo, telemetria e experimentos.
    """
    base_dir = ensure_db_dir(db_dir)
    conn = get_connection("esa_catalog", read_only=read_only, db_dir=base_dir)
    
    mode_str = "?mode=ro" if read_only else ""
    
    if attach_m1:
        m1_path = (base_dir / "esa_m1.sqlite").as_posix()
        if Path(m1_path).exists():
            conn.execute(f"ATTACH DATABASE 'file:{m1_path}{mode_str}' AS m1;")
            
    if attach_m2:
        m2_path = (base_dir / "esa_m2.sqlite").as_posix()
        if Path(m2_path).exists():
            conn.execute(f"ATTACH DATABASE 'file:{m2_path}{mode_str}' AS m2;")
            
    if attach_exp:
        exp_path = (base_dir / "esa_experiments.sqlite").as_posix()
        if Path(exp_path).exists():
            conn.execute(f"ATTACH DATABASE 'file:{exp_path}{mode_str}' AS exp;")
            
    return conn
