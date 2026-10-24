"""
Tool: check_data_quality
Verifica a qualidade dos dados de telemetria em uma janela temporal.

Detecta três tipos de problema:
- Lacunas: intervalos entre timestamps maiores que LACUNA_FATOR × cadência mediana.
- Canais congelados: mesmo valor repetido por CANAL_TRAVADO_N_AMOSTRAS consecutivas.
- Dados ausentes: porcentagem de leituras com NaN/NULL por canal.
"""

from __future__ import annotations

import logging
from math import ceil
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.db.connection import get_attached_connection
from ..config import (
    CANAL_TRAVADO_N_AMOSTRAS,
    CADENCIA_S,
    CHANNELS,
    DB_ALIAS,
    DEFAULT_DB_DIR,
    LACUNA_FATOR,
)
from ..utils import iso_to_ms, ms_to_iso, validate_mission, validate_window

logger = logging.getLogger(__name__)


def check_data_quality(
    mission: str,
    ts_inicio_iso: str,
    ts_fim_iso: str,
    db_dir: Optional[Path] = None,
) -> dict:
    """
    Verifica a qualidade dos dados de telemetria em um período.

    Retorna um relatório estruturado com lacunas detectadas, canais congelados
    e percentual de leituras válidas por canal. Um dado com problemas de qualidade
    não deve ser usado para conclusões sobre anomalias sem ressalvas.

    Args:
        mission: Missão a analisar ('M1' ou 'M2').
        ts_inicio_iso: Início do período (ISO 8601, ex: '2005-03-30T00:00:00Z').
        ts_fim_iso: Fim do período (ISO 8601).
        db_dir: Diretório dos bancos SQLite (None = padrão do projeto).

    Returns:
        Dict com 'status', 'lacunas', 'canais_travados' e 'pct_valida_por_canal'.
    """
    validate_mission(mission)
    ts_inicio = iso_to_ms(ts_inicio_iso)
    ts_fim = iso_to_ms(ts_fim_iso)
    validate_window(ts_inicio, ts_fim)

    db = db_dir or DEFAULT_DB_DIR
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
        ch_cols = ", ".join(channels)
        df = pd.read_sql_query(
            f"SELECT ts, {ch_cols} FROM {alias}.telemetry WHERE ts >= ? AND ts <= ? ORDER BY ts",
            conn,
            params=[ts_inicio, ts_fim],
        )

        if df.empty:
            return {
                "status": "sem_dados",
                "severidade": "grave",
                "n_leituras": 0,
                "lacunas": [],
                "canais_travados": [],
                "pct_valida_por_canal": {},
                "metricas_severidade": {
                    "pct_leituras_estimadas_ausentes": 0.0,
                    "pct_canais_travados": 0.0,
                    "pct_dados_ausentes": 0.0,
                },
                "aviso": "Nenhuma leitura encontrada no período especificado.",
            }

        cadence_row = conn.execute(
            "SELECT cadencia_mediana_s FROM missions WHERE mission = ?", (mission,)
        ).fetchone()
        cadence_s = float(cadence_row[0]) if cadence_row and cadence_row[0] else CADENCIA_S[mission]
        gap_threshold_ms = cadence_s * 1000.0 * LACUNA_FATOR

        ts_arr = df["ts"].values
        n = len(ts_arr)

        # --- Lacunas ---
        diffs = np.diff(ts_arr)
        lacuna_idx = np.where(diffs > gap_threshold_ms)[0]
        lacunas = [
            {
                "inicio": ms_to_iso(int(ts_arr[i])),
                "fim": ms_to_iso(int(ts_arr[i + 1])),
                "duracao_s": round(float(diffs[i]) / 1000, 1),
            }
            for i in lacuna_idx
        ]

        # --- Canais congelados ---
        canais_travados = []
        for ch in channels:
            vals = df[ch].values
            if _tem_sequencia_repetida(vals, CANAL_TRAVADO_N_AMOSTRAS):
                canais_travados.append(ch)

        # --- Percentual de dados válidos por canal ---
        pct_valida = {}
        for ch in channels:
            n_validos = int(df[ch].notna().sum())
            pct_valida[ch] = round(100.0 * n_validos / n, 2)

        missing_samples = sum(
            max(ceil(float(diff) / (cadence_s * 1000.0)) - 1, 0)
            for diff in diffs[lacuna_idx]
        )
        pct_missing_samples = 100.0 * missing_samples / max(n + missing_samples, 1)
        pct_frozen_channels = 100.0 * len(canais_travados) / max(len(channels), 1)
        pct_missing_values = sum(100.0 - value for value in pct_valida.values()) / max(len(channels), 1)

        # Status geral
        tem_dados_ausentes = any(value < 100.0 for value in pct_valida.values())
        tem_problema = len(lacunas) > 0 or len(canais_travados) > 0 or tem_dados_ausentes
        status = "comprometida" if tem_problema else "boa"
        severidade = _classify_quality_severity(
            pct_missing_samples, pct_frozen_channels, pct_missing_values, tem_problema
        )

        return {
            "status": status,
            "severidade": severidade,
            "n_leituras": n,
            "cadencia_esperada_s": cadence_s,
            "lacunas": lacunas,
            "n_lacunas": len(lacunas),
            "canais_travados": canais_travados,
            "pct_valida_por_canal": pct_valida,
            "metricas_severidade": {
                "pct_leituras_estimadas_ausentes": round(pct_missing_samples, 3),
                "pct_canais_travados": round(pct_frozen_channels, 2),
                "pct_dados_ausentes": round(pct_missing_values, 3),
            },
        }

    finally:
        conn.close()


def _tem_sequencia_repetida(arr: np.ndarray, n_min: int) -> bool:
    """Retorna True se o array tem N ou mais valores idênticos consecutivos."""
    if len(arr) < n_min:
        return False
    count = 1
    for i in range(1, len(arr)):
        if arr[i] == arr[i - 1] and not np.isnan(arr[i]):
            count += 1
            if count >= n_min:
                return True
        else:
            count = 1
    return False


def _classify_quality_severity(
    pct_missing_samples: float,
    pct_frozen_channels: float,
    pct_missing_values: float,
    has_problem: bool,
) -> str:
    """Classifica qualidade pela maior proporção de impacto observado."""
    if not has_problem:
        return "boa"

    ranks = [
        1 if pct_missing_samples <= 1 else 2 if pct_missing_samples <= 5 else 3,
        1 if pct_frozen_channels <= 10 else 2 if pct_frozen_channels <= 30 else 3,
        1 if pct_missing_values <= 1 else 2 if pct_missing_values <= 5 else 3,
    ]
    return {1: "leve", 2: "moderada", 3: "grave"}[max(ranks)]
