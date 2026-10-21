"""
Verificador de Integridade e Auditoria Cruzada dos Bancos ESA-ADB.
Executa as validações prescritas na Seção 10 do documento 'Arquitetura do Banco de Dados.md'.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .connection import get_attached_connection, get_connection, get_db_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_integrity")


def check_sqlite_pragmas(db_name: str, db_dir: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """Verifica PRAGMA integrity_check e PRAGMA foreign_key_check em um banco."""
    conn = get_connection(db_name, read_only=True, db_dir=db_dir)
    errors = []
    
    try:
        # Integrity check
        cur = conn.execute("PRAGMA integrity_check;")
        rows = [r[0] for r in cur.fetchall()]
        if rows != ["ok"]:
            errors.append(f"[{db_name}] PRAGMA integrity_check falhou: {rows}")
            
        # Foreign key check
        cur = conn.execute("PRAGMA foreign_key_check;")
        fk_rows = cur.fetchall()
        if fk_rows:
            errors.append(f"[{db_name}] Violações de chave estrangeira encontradas: {len(fk_rows)} linhas.")
            
    finally:
        conn.close()
        
    return len(errors) == 0, errors


def verify_catalog_consistency(db_dir: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """Verifica integridade interna do catálogo esa_catalog.sqlite."""
    conn = get_connection("esa_catalog", read_only=True, db_dir=db_dir)
    errors = []
    
    try:
        # 1. Total de eventos derivados por categoria
        cur = conn.execute("""
            SELECT mission, category, COUNT(*) AS count
            FROM events
            GROUP BY mission, category;
        """)
        counts = {(r["mission"], r["category"]): r["count"] for r in cur.fetchall()}
        logger.info(f"Contagem de eventos derivados por missão/categoria: {counts}")
        
        # M1 esperado: 51 Anomaly, 63 Rare Event, 4 Communication Gap (Total: 118)
        m1_total = sum(v for k, v in counts.items() if k[0] == "M1")
        if m1_total != 118:
            errors.append(f"[esa_catalog] M1 esperava 118 eventos derivados, encontrado {m1_total}.")
            
        # 2. Verifica se todo event_id de event_windows existe em events
        cur = conn.execute("""
            SELECT COUNT(*) AS orfaos
            FROM event_windows w
            LEFT JOIN events e ON e.mission = w.mission AND e.event_id = w.event_id
            WHERE e.event_id IS NULL;
        """)
        orfaos_w = cur.fetchone()["orfaos"]
        if orfaos_w > 0:
            errors.append(f"[esa_catalog] Encontradas {orfaos_w} janelas sem evento correspondente em 'events'.")
            
        # 3. Verifica labels inválidos auditados
        cur = conn.execute("SELECT mission, valido, COUNT(*) as c FROM labels GROUP BY mission, valido;")
        logger.info(f"Rótulos auditados por validade: {[dict(r) for r in cur.fetchall()]}")

    finally:
        conn.close()
        
    return len(errors) == 0, errors


def verify_cross_db_integrity(db_dir: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """Verifica consistência lógica entre o catálogo e os bancos de telemetria anexados."""
    conn = get_attached_connection(db_dir=db_dir, attach_m1=True, attach_m2=True, attach_exp=True, read_only=True)
    errors = []
    
    try:
        # Verifica se m1 está anexado
        cur = conn.execute("PRAGMA database_list;")
        databases = {r["name"]: r["file"] for r in cur.fetchall()}
        
        if "m1" in databases:
            logger.info("Auditando consistência entre catálogo e esa_m1.sqlite...")
            
            # Checa se total de linhas bate com meta e com missions
            cur = conn.execute("SELECT COUNT(*) AS total FROM m1.telemetry;")
            total_m1 = cur.fetchone()["total"]
            if total_m1 != 15381169:
                errors.append(f"[m1.telemetry] Contagem de leituras esperada 15.381.169, encontrada {total_m1:,}.")
            else:
                logger.info(f"[m1.telemetry] OK: 15.381.169 leituras confirmadas.")
                
            # Checa se todos os telecomandos em tc_executions existem no catálogo
            cur = conn.execute("""
                SELECT COUNT(DISTINCT t.telecommand) AS nao_catalogados
                FROM m1.tc_executions t
                LEFT JOIN telecommands c ON c.mission = 'M1' AND c.telecommand = t.telecommand
                WHERE c.telecommand IS NULL;
            """)
            nao_cat = cur.fetchone()["nao_catalogados"]
            if nao_cat > 0:
                errors.append(f"[m1.tc_executions] {nao_cat} telecomandos executados não estão no catálogo.")
            else:
                logger.info("[m1.tc_executions] OK: Todos os telecomandos executados estão devidamente catalogados.")
                
        if "m2" in databases:
            logger.info("Auditando consistência entre catálogo e esa_m2.sqlite...")
            cur = conn.execute("SELECT COUNT(*) AS total FROM m2.telemetry;")
            total_m2 = cur.fetchone()["total"]
            if total_m2 != 7387262:
                errors.append(f"[m2.telemetry] Contagem de leituras esperada 7.387.262, encontrada {total_m2:,}.")
                
    finally:
        conn.close()
        
    return len(errors) == 0, errors


def run_full_validation(db_dir: Optional[Path] = None) -> bool:
    """Executa a rotina completa de auditoria em todos os bancos."""
    logger.info("=" * 70)
    logger.info("INICIANDO AUDITORIA COMPLETA DE INTEGRIDADE (SEÇÃO 10.4)")
    logger.info("=" * 70)
    
    all_ok = True
    all_errors = []
    
    # 1. PRAGMAs nos bancos existentes
    for db_name in ["esa_catalog", "esa_m1", "esa_m2", "esa_experiments"]:
        db_path = get_db_path(db_name, db_dir)
        if db_path.exists():
            ok, errs = check_sqlite_pragmas(db_name, db_dir)
            if ok:
                logger.info(f"[{db_name}] PRAGMA integrity_check e foreign_keys: OK")
            else:
                all_ok = False
                all_errors.extend(errs)
                
    # 2. Catálogo
    ok, errs = verify_catalog_consistency(db_dir)
    if not ok:
        all_ok = False
        all_errors.extend(errs)
        
    # 3. Cruzamento entre bancos
    ok, errs = verify_cross_db_integrity(db_dir)
    if not ok:
        all_ok = False
        all_errors.extend(errs)
        
    logger.info("=" * 70)
    if all_ok:
        logger.info("TODAS AS VALIDAÇÕES PASSARAM COM SUCESSO! INTEGRIDADE GARANTIDA.")
    else:
        logger.error(f"FALHAS ENCONTRADAS ({len(all_errors)}):")
        for err in all_errors:
            logger.error(f"  - {err}")
    logger.info("=" * 70)
    
    return all_ok
