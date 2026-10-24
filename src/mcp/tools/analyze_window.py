"""
Tool: analyze_window
Analisa o estado dos canais de telemetria em um período de tempo.

Para cada canal, calcula estatísticas (média, desvio, mín, máx) e compara
com o histórico nominal do período de treino via desvio normalizado (em MADs).
Identifica também eventos conhecidos que ocorreram no período consultado.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.db.connection import get_attached_connection
from ..baseline import get_baseline
from ..config import (
    CHANNELS,
    DB_ALIAS,
    DEFAULT_DB_DIR,
    DESVIO_ELEVADO,
    DESVIO_MUITO_ELEVADO,
)
from ..utils import iso_to_ms, ms_to_iso, validate_mission, validate_window
from .check_data_quality import check_data_quality

logger = logging.getLogger(__name__)


def analyze_window(
    mission: str,
    ts_inicio_iso: str,
    ts_fim_iso: str,
    db_dir: Optional[Path] = None,
) -> dict:
    """
    Analisa o estado dos canais de telemetria em um período.

    Calcula estatísticas por canal e compara com o histórico nominal para
    identificar desvios. Inclui eventos conhecidos no período e qualidade dos dados.
    Útil para entender o que estava acontecendo em um dado momento da missão.

    Args:
        mission: Missão a analisar ('M1' ou 'M2').
        ts_inicio_iso: Início do período (ISO 8601, ex: '2005-03-30T00:00:00Z').
        ts_fim_iso: Fim do período (ISO 8601).
        db_dir: Diretório dos bancos SQLite (None = padrão do projeto).

    Returns:
        Dict com estatísticas por canal, qualidade dos dados e eventos conhecidos.
    """
    validate_mission(mission)
    ts_inicio = iso_to_ms(ts_inicio_iso)
    ts_fim = iso_to_ms(ts_fim_iso)
    validate_window(ts_inicio, ts_fim)

    db = db_dir or DEFAULT_DB_DIR
    db_str = str(db) if db_dir else None
    channels = CHANNELS[mission]
    alias = DB_ALIAS[mission]

    conn = get_attached_connection(
        db_dir=db,
        attach_m1=(mission == "M1"),
        attach_m2=(mission == "M2"),
        attach_exp=False,
        read_only=True,
    )

    try:
        # Carrega telemetria do período
        ch_cols = ", ".join(channels)
        df = pd.read_sql_query(
            f"SELECT ts, {ch_cols} FROM {alias}.telemetry WHERE ts >= ? AND ts <= ? ORDER BY ts",
            conn,
            params=[ts_inicio, ts_fim],
        )

        if df.empty:
            return {
                "missao": mission,
                "periodo": {"inicio": ts_inicio_iso, "fim": ts_fim_iso, "n_leituras": 0},
                "canais": {},
                "eventos_conhecidos_no_periodo": [],
                "qualidade": {"status": "sem_dados"},
                "aviso": "Nenhuma leitura encontrada no período.",
            }

        # Baseline do treino (cacheado)
        baseline = get_baseline(mission, db_str)

        # Estatísticas por canal
        canais_stats: dict[str, dict] = {}
        for ch in channels:
            vals = df[ch].dropna().values
            if len(vals) == 0:
                canais_stats[ch] = {"status": "sem_dados"}
                continue

            med = float(np.mean(vals))
            med_robusta = float(np.median(vals))
            std = float(np.std(vals))
            mn = float(np.min(vals))
            mx = float(np.max(vals))

            escala_base = baseline[ch]["escala"]
            mediana_base = baseline[ch]["mediana"]
            desvio_norm = (
                abs(med_robusta - mediana_base) / escala_base if escala_base > 0 else 0.0
            )

            if desvio_norm >= DESVIO_MUITO_ELEVADO:
                status = "muito_elevado"
            elif desvio_norm >= DESVIO_ELEVADO:
                status = "elevado"
            else:
                status = "nominal"

            canais_stats[ch] = {
                "media": round(med, 6),
                "mediana": round(med_robusta, 6),
                "desvio_padrao": round(std, 6),
                "min": round(mn, 6),
                "max": round(mx, 6),
                "desvio_normalizado_mad": round(desvio_norm, 2),
                "referencia_nominal": round(mediana_base, 6),
                "status": status,
            }

        # Eventos conhecidos no período
        rows = conn.execute(
            """
            SELECT event_id, category, class, start_ts, end_ts, n_canais
            FROM events
            WHERE mission = ? AND start_ts <= ? AND end_ts >= ?
            ORDER BY start_ts
            """,
            (mission, ts_fim, ts_inicio),
        ).fetchall()

        eventos = [
            {
                "event_id": r["event_id"],
                "category": r["category"],
                "class": r["class"],
                "inicio": ms_to_iso(r["start_ts"]),
                "fim": ms_to_iso(r["end_ts"]),
                "n_canais_afetados": r["n_canais"],
            }
            for r in rows
        ]

        # Qualidade dos dados (reutiliza a tool)
        qualidade = check_data_quality(mission, ts_inicio_iso, ts_fim_iso, db_dir=db)

        # Canais com desvio elevado ou muito_elevado
        canais_em_alerta = [
            ch for ch, v in canais_stats.items()
            if v.get("status") in ("elevado", "muito_elevado")
        ]

        return {
            "missao": mission,
            "periodo": {
                "inicio": ts_inicio_iso,
                "fim": ts_fim_iso,
                "n_leituras": len(df),
            },
            "canais": canais_stats,
            "canais_em_alerta": canais_em_alerta,
            "eventos_conhecidos_no_periodo": eventos,
            "qualidade": {
                "status": qualidade["status"],
                "severidade": qualidade.get("severidade", "boa"),
                "n_lacunas": qualidade.get("n_lacunas", 0),
                "canais_travados": qualidade.get("canais_travados", []),
                "metricas_severidade": qualidade.get("metricas_severidade", {}),
            },
        }

    finally:
        conn.close()
