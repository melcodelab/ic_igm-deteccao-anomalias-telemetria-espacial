"""Consultas históricas com limite explícito em treino + validação."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.db.connection import get_connection
from .config import DEFAULT_DB_DIR, SPLIT_ID_PADRAO
from .utils import validate_mission


def history_cutoff(mission: str, db_dir: Optional[Path] = None) -> int:
    """Maior timestamp permitido para contexto histórico (fim de treino/validação)."""
    validate_mission(mission)
    conn = get_connection("esa_catalog", read_only=True, db_dir=db_dir or DEFAULT_DB_DIR)
    try:
        split = SPLIT_ID_PADRAO[mission]
        row = conn.execute(
            "SELECT MAX(fim_ts) FROM splits WHERE mission=? AND split_id=? AND papel IN ('train','val')",
            (mission, split),
        ).fetchone()
        if row is None or row[0] is None:
            raise RuntimeError(f"Split de treino/validação ausente para {mission}/{split}.")
        return int(row[0])
    finally:
        conn.close()

