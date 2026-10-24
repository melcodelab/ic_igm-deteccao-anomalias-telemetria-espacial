"""Resumo determinístico de telemetria, eventos e telecomandos no período."""
from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Optional

from .analyze_window import analyze_window
from .recent_commands import recent_commands
from ..config import DELTA_TC_MINUTOS
from ..utils import iso_to_ms, ms_to_iso
from src.db.connection import get_connection
from ..config import DEFAULT_DB_DIR


def shift_summary(mission: str, ts_inicio_iso: str, ts_fim_iso: str,
                  db_dir: Optional[Path] = None) -> dict:
    analysis = analyze_window(mission, ts_inicio_iso, ts_fim_iso, db_dir)
    start, end = iso_to_ms(ts_inicio_iso), iso_to_ms(ts_fim_iso)
    previous_start = start - (end - start)
    previous_end = start - 1
    previous_start_iso = ms_to_iso(previous_start)
    previous_end_iso = ms_to_iso(previous_end)
    previous_analysis = analyze_window(mission, previous_start_iso, previous_end_iso, db_dir)
    conn = get_connection("esa_catalog", read_only=True, db_dir=db_dir or DEFAULT_DB_DIR)
    try:
        events = conn.execute(
            """SELECT event_id,category,class,start_ts,end_ts,n_canais
               FROM events WHERE mission=? AND start_ts<=? AND end_ts>=? ORDER BY start_ts""",
            (mission, end, start),
        ).fetchall()
    finally:
        conn.close()
    command_window_minutes = max(DELTA_TC_MINUTOS, ceil((end - start) / 60_000))
    commands = recent_commands(
        mission, ts_fim_iso, db_dir, delta_minutos=command_window_minutes
    )
    statuses = [v.get("status") for v in analysis["canais"].values()]
    current_channels = analysis.get("canais", {})
    previous_channels = previous_analysis.get("canais", {})
    status_rank = {"nominal": 0, "elevado": 1, "muito_elevado": 2}
    trend = {"piorando": [], "estaveis": [], "melhorando": [], "sem_referencia": []}
    score_deltas: dict[str, float] = {}
    for channel, current in current_channels.items():
        previous = previous_channels.get(channel, {})
        current_rank = status_rank.get(current.get("status"))
        previous_rank = status_rank.get(previous.get("status"))
        current_score = current.get("desvio_normalizado_mad")
        previous_score = previous.get("desvio_normalizado_mad")
        if current_rank is None or previous_rank is None or current_score is None or previous_score is None:
            trend["sem_referencia"].append(channel)
            continue
        delta = round(current_score - previous_score, 2)
        score_deltas[channel] = delta
        if current_rank > previous_rank or delta >= 0.25:
            trend["piorando"].append(channel)
        elif current_rank < previous_rank or delta <= -0.25:
            trend["melhorando"].append(channel)
        else:
            trend["estaveis"].append(channel)

    event_details = [
        {"event_id": row[0], "category": row[1], "class": row[2],
         "inicio_ms": row[3], "fim_ms": row[4],
         "inicio_iso": ms_to_iso(row[3]), "fim_iso": ms_to_iso(row[4]),
         "n_canais_afetados": row[5]}
        for row in events
    ]
    event_counts: dict[str, int] = {}
    for event in event_details:
        event_counts[event["category"]] = event_counts.get(event["category"], 0) + 1

    summary = {
        "missao": mission, "periodo": analysis["periodo"],
        "leituras": analysis["periodo"]["n_leituras"],
        "canais_em_alerta": analysis.get("canais_em_alerta", []),
        "canais_muito_elevados": [
            channel for channel, data in current_channels.items()
            if data.get("status") == "muito_elevado"
        ],
        "canais_elevados": [
            channel for channel, data in current_channels.items()
            if data.get("status") == "elevado"
        ],
        "tendencia_canais": {
            "periodo_anterior": {"inicio": previous_start_iso, "fim": previous_end_iso},
            "variacao_desvio_mad": score_deltas,
            "limiar_estabilidade_mad": 0.25,
            **trend,
        },
        "qualidade": analysis["qualidade"],
        "eventos_anotados": event_counts,
        "eventos_detalhados": event_details,
        "telecomandos_na_janela_final": recent_commands(mission, ts_fim_iso, db_dir),
        "telecomandos_no_turno": commands,
        "canais_nominais": sum(s == "nominal" for s in statuses),
    }
    return summary

