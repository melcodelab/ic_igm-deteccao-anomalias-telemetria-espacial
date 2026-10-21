"""
Testes automatizados da arquitetura de banco de dados e pipeline de ETL ESA-ADB.
Valida criação de tabelas, integridade de dados e ausência de vazamento.
"""

import sqlite3
from pathlib import Path
import pytest

from src.db.connection import get_connection, get_db_path, get_attached_connection
from src.db.verify_integrity import check_sqlite_pragmas, verify_catalog_consistency, verify_cross_db_integrity


def test_catalog_file_exists():
    catalog_path = get_db_path("esa_catalog")
    assert catalog_path.exists(), "esa_catalog.sqlite deve existir"
    assert catalog_path.stat().st_size > 0


def test_m1_telemetry_file_exists():
    m1_path = get_db_path("esa_m1")
    assert m1_path.exists(), "esa_m1.sqlite deve existir"
    assert m1_path.stat().st_size > 1_000_000_000, "esa_m1.sqlite deve ter ~1.1 GB"


def test_experiments_file_exists():
    exp_path = get_db_path("esa_experiments")
    assert exp_path.exists(), "esa_experiments.sqlite deve existir"


def test_sqlite_pragmas():
    ok, errors = check_sqlite_pragmas("esa_catalog")
    assert ok, f"PRAGMA check falhou no catálogo: {errors}"
    
    ok, errors = check_sqlite_pragmas("esa_m1")
    assert ok, f"PRAGMA check falhou no esa_m1: {errors}"
    
    ok, errors = check_sqlite_pragmas("esa_experiments")
    assert ok, f"PRAGMA check falhou no esa_experiments: {errors}"


def test_catalog_events_and_labels_counts():
    conn = get_connection("esa_catalog", read_only=True)
    try:
        # Total de eventos derivados na Mission 1
        cur = conn.execute("SELECT COUNT(*) AS total FROM events WHERE mission = 'M1';")
        assert cur.fetchone()["total"] == 118, "M1 deve ter exatamente 118 eventos consolidados derivados"
        
        # Categorias de eventos
        cur = conn.execute("SELECT category, COUNT(*) as c FROM events WHERE mission = 'M1' GROUP BY category;")
        cat_counts = {r["category"]: r["c"] for r in cur.fetchall()}
        assert cat_counts["Anomaly"] == 51, "M1 deve ter 51 anomalias"
        assert cat_counts["Rare Event"] == 63, "M1 deve ter 63 eventos raros"
        assert cat_counts["Communication Gap"] == 4, "M1 deve ter 4 lacunas de comunicação"
        
        # Total de labels auditados
        cur = conn.execute("SELECT COUNT(*) AS total FROM labels WHERE mission = 'M1';")
        assert cur.fetchone()["total"] == 3589, "M1 deve ter exatamente 3.589 linhas em labels"
        
        # Janelas contextuais
        cur = conn.execute("SELECT COUNT(*) AS total FROM event_windows WHERE mission = 'M1';")
        assert cur.fetchone()["total"] == 708, "M1 deve ter 708 janelas (118 * 3 * 2)"
        
    finally:
        conn.close()


def test_telemetry_m1_readings():
    conn = get_connection("esa_m1", read_only=True)
    try:
        cur = conn.execute("SELECT COUNT(*) AS total FROM telemetry;")
        assert cur.fetchone()["total"] == 15381169, "M1 telemetry deve ter exatamente 15.381.169 leituras"
        
        cur = conn.execute("SELECT COUNT(*) AS total FROM tc_executions;")
        assert cur.fetchone()["total"] == 1594722, "M1 tc_executions deve ter 1.594.722 execuções"
    finally:
        conn.close()


def test_cross_db_attached_integrity():
    ok, errors = verify_cross_db_integrity()
    assert ok, f"Verificação cruzada com ATTACH falhou: {errors}"
