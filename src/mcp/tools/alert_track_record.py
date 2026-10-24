"""Resumo de classificações de alertas anotados antes do timestamp consultado."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.db.connection import get_attached_connection
from ..config import DEFAULT_DB_DIR, SPLIT_ID_PADRAO
from ..history import history_cutoff
from ..utils import iso_to_ms, validate_mission


def alert_track_record(mission: str, ts_referencia_iso: str,
                       db_dir: Optional[Path] = None) -> dict:
    """Conta alertas históricos rotulados; retorna indisponível se não há runs."""
    validate_mission(mission)
    cutoff = min(iso_to_ms(ts_referencia_iso), history_cutoff(mission, db_dir))
    conn = get_attached_connection(db_dir=db_dir or DEFAULT_DB_DIR, attach_m1=False,
                                   attach_m2=False, attach_exp=True, read_only=True)
    try:
        dbs = {row[1] for row in conn.execute("PRAGMA database_list")}
        if "exp" not in dbs:
            return {"disponivel": False, "motivo": "Banco de experimentos ausente.", "n": 0}
        exists = conn.execute(
            "SELECT 1 FROM exp.sqlite_master WHERE type='table' AND name='alerts'"
        ).fetchone()
        if not exists:
            return {"disponivel": False, "motivo": "Schema de alertas ausente.", "n": 0}
        rows = conn.execute(
            """SELECT a.alert_id,
                      MAX(CASE WHEN m.category='Anomaly' THEN 1 ELSE 0 END) AS anomaly,
                      MAX(CASE WHEN m.category='Rare Event' THEN 1 ELSE 0 END) AS rare_event,
                      COUNT(m.event_id) AS matches
               FROM exp.alerts a JOIN exp.runs r ON r.run_id=a.run_id
               LEFT JOIN exp.alert_matches m ON m.alert_id=a.alert_id
               WHERE r.mission=? AND r.split_id=? AND a.fim_ts<=? AND a.inicio_ts<?
               GROUP BY a.alert_id ORDER BY a.inicio_ts""",
            (mission, SPLIT_ID_PADRAO[mission], cutoff, cutoff),
        ).fetchall()
        known = [r for r in rows if r[3] > 0]
        return {"disponivel": bool(known), "n": len(known),
                "anomalia": sum(bool(r[1]) for r in known),
                "evento_raro_nominal": sum(bool(r[2]) for r in known),
                "sem_rotulo": len(rows) - len(known),
                "nota": "Resumo somente de alertas anotados; ausência de rótulo não significa alerta falso.",
                "periodo_consultado": "treino+validacao", "cutoff_ms": cutoff}
    finally:
        conn.close()
