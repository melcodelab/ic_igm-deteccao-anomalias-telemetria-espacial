"""Consulta telecomandos executados antes de um instante, limitado ao delta configurado."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.db.connection import get_attached_connection
from ..config import DB_ALIAS, DEFAULT_DB_DIR, DELTA_TC_MINUTOS
from ..utils import iso_to_ms, ms_to_iso, validate_mission


def recent_commands(mission: str, ts_referencia_iso: str,
                    db_dir: Optional[Path] = None, delta_minutos: int = DELTA_TC_MINUTOS) -> dict:
    validate_mission(mission)
    if delta_minutos <= 0:
        raise ValueError("delta_minutos deve ser positivo")
    end = iso_to_ms(ts_referencia_iso)
    start = end - delta_minutos * 60_000
    alias = DB_ALIAS[mission]
    conn = get_attached_connection(db_dir=db_dir or DEFAULT_DB_DIR,
                                   attach_m1=mission == "M1", attach_m2=mission == "M2",
                                   attach_exp=False, read_only=True)
    try:
        commands = conn.execute(
            f"""SELECT t.telecommand,t.ts,c.priority FROM {alias}.tc_executions t
                LEFT JOIN telecommands c ON c.mission=? AND c.telecommand=t.telecommand
                WHERE t.ts>=? AND t.ts<=? ORDER BY t.ts DESC""",
            (mission, start, end),
        ).fetchall()
        return {"janela_minutos": delta_minutos,
            "comandos": [{"telecommand": r[0], "ts_ms": r[1], "ts_iso": ms_to_iso(r[1]),
                      "priority": r[2]} for r in commands],
                "total": len(commands)}
    finally:
        conn.close()

