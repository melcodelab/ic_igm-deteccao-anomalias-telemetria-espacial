"""Busca eventos históricos com canais em comum, sem consultar além da validação."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from src.db.connection import get_connection
from ..config import DEFAULT_DB_DIR, SPLIT_ID_PADRAO
from ..history import history_cutoff
from ..utils import iso_to_ms, ms_to_iso, validate_mission


def find_similar_events(mission: str, ts_referencia_iso: str,
                        canais: Optional[Sequence[str]] = None,
                        db_dir: Optional[Path] = None) -> dict:
    """Retorna eventos anteriores ao cutoff com canais afetados em comum."""
    validate_mission(mission)
    cutoff = history_cutoff(mission, db_dir)
    reference = min(iso_to_ms(ts_referencia_iso), cutoff)
    conn = get_connection("esa_catalog", read_only=True, db_dir=db_dir or DEFAULT_DB_DIR)
    try:
        split = SPLIT_ID_PADRAO[mission]
        val_end = conn.execute(
            "SELECT MAX(fim_ts) FROM splits WHERE mission=? AND split_id=? AND papel IN ('train','val')",
            (mission, split),
        ).fetchone()[0]
        wanted = set(canais or [])
        rows = conn.execute(
            """SELECT e.event_id,e.category,e.class,e.start_ts,e.end_ts,e.n_canais,
                      GROUP_CONCAT(DISTINCT l.channel) AS canais
               FROM events e LEFT JOIN labels l ON l.mission=e.mission AND l.event_id=e.event_id
               WHERE e.mission=? AND e.start_ts<=? AND e.start_ts<?
                 AND e.category IN ('Anomaly','Rare Event')
               GROUP BY e.mission,e.event_id ORDER BY e.start_ts DESC""",
            (mission, reference, int(val_end)),
        ).fetchall()
        selected = []
        for row in rows:
            event_channels = set((row[6] or "").split(",")) - {""}
            if not wanted or wanted.intersection(event_channels):
                selected.append({
                    "event_id": row[0], "category": row[1], "class": row[2],
                    "inicio_ms": row[3], "fim_ms": row[4],
                    "inicio_iso": ms_to_iso(row[3]), "fim_iso": ms_to_iso(row[4]),
                    "canais": sorted(event_channels), "n_canais": row[5],
                })
        nominal = sum(e["category"] == "Rare Event" for e in selected)
        anomaly = sum(e["category"] == "Anomaly" for e in selected)
        return {
            "periodo_consultado": "treino+validacao",
            "cutoff_ms": int(val_end),
            "cutoff_iso": ms_to_iso(int(val_end)),
            "nominal": nominal,
            "anomalia": anomaly,
            "resumo": (
                f"Foram encontrados {len(selected)} eventos históricos com canais em comum: "
                f"{nominal} eventos raros nominais e {anomaly} anomalias."
            ),
            "eventos": selected[:20],
            "total_encontrado": len(selected),
        }
    finally:
        conn.close()

