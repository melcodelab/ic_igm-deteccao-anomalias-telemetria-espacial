"""
Baseline Estatístico — Medianas e Escalas Robustas do Período de Treino.

Calcula e armazena em cache (lru_cache) as estatísticas de normalização
calculadas exclusivamente sobre o split de treino nominal de cada missão.

Por que lru_cache:
    O cálculo exige carregar millions de registros de telemetria. O cache
    garante que esse trabalho é feito uma única vez por processo, independente
    de quantas tools chamem get_baseline().
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.db.connection import get_attached_connection
from .config import CHANNELS, DB_ALIAS, DEFAULT_DB_DIR, SPLIT_ID_PADRAO

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def get_baseline(mission: str, db_dir_str: Optional[str] = None) -> dict[str, dict[str, float]]:
    """
    Retorna as estatísticas baseline {channel: {mediana, escala}} do split de treino.

    O resultado é cacheado por (mission, db_dir_str). A primeira chamada para
    cada missão pode levar alguns segundos (carrega os dados de treino).

    Args:
        mission: 'M1' ou 'M2'.
        db_dir_str: Caminho string do diretório de bancos (None = padrão do projeto).

    Returns:
        Dict indexado por nome de canal com 'mediana' e 'escala' (MAD × 1.4826).
    """
    db_dir = Path(db_dir_str) if db_dir_str else DEFAULT_DB_DIR
    split_id = SPLIT_ID_PADRAO[mission]
    channels = CHANNELS[mission]
    alias = DB_ALIAS[mission]

    logger.info(f"[baseline] Calculando baseline para {mission} (split={split_id})…")

    conn = get_attached_connection(
        db_dir=db_dir,
        attach_m1=(mission == "M1"),
        attach_m2=(mission == "M2"),
        attach_exp=False,
        read_only=True,
    )

    try:
        # Busca limites do split de treino
        row = conn.execute(
            "SELECT inicio_ts, fim_ts FROM splits WHERE mission=? AND split_id=? AND papel='train'",
            (mission, split_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Split '{split_id}/train' não encontrado para {mission}.")
        train_start, train_end = row["inicio_ts"], row["fim_ts"]

        # Busca labels válidas para expurgar do treino (garantia de treino nominal puro)
        labels = conn.execute(
            "SELECT start_ts, end_ts FROM labels WHERE mission=? AND valido=1",
            (mission,),
        ).fetchall()
        label_intervals = [(r["start_ts"], r["end_ts"]) for r in labels]

        # Carrega telemetria do período de treino
        ch_cols = ", ".join(channels)
        df = pd.read_sql_query(
            f"SELECT ts, {ch_cols} FROM {alias}.telemetry WHERE ts >= ? AND ts < ? ORDER BY ts",
            conn,
            params=[train_start, train_end],
        )

        ts_arr = df["ts"].values
        data = df[channels].values.astype(np.float64)

        # Máscara de dados nominais (sem labels)
        nominal_mask = np.ones(len(ts_arr), dtype=bool)
        for l_start, l_end in label_intervals:
            if l_end >= train_start and l_start <= train_end:
                nominal_mask &= ~((ts_arr >= l_start) & (ts_arr <= l_end))

        nominal_data = data[nominal_mask]
        pct = 100.0 * len(nominal_data) / max(len(data), 1)
        logger.info(f"[baseline] {mission}: {len(nominal_data):,} amostras nominais ({pct:.1f}%).")

        # Mediana e MAD por canal
        mediana = np.median(nominal_data, axis=0)
        dev = np.abs(nominal_data - mediana)
        mad = np.median(dev, axis=0)
        escala = 1.4826 * mad

        # Salvaguardas para canais com escala zero
        for i in range(len(escala)):
            if escala[i] == 0:
                mean_dev = float(np.mean(dev[:, i]))
                escala[i] = mean_dev if mean_dev > 0 else float(np.std(nominal_data[:, i]) or 1.0)

        result = {
            ch: {"mediana": float(mediana[i]), "escala": float(escala[i])}
            for i, ch in enumerate(channels)
        }
        logger.info(f"[baseline] {mission}: baseline calculado com sucesso.")
        return result

    finally:
        conn.close()


def invalidate_baseline_cache() -> None:
    """Limpa o cache do baseline (útil em testes que mudam o DB)."""
    get_baseline.cache_clear()
