"""
Construtor e Exportador de Datasets para Modelos de Machine Learning (Autoencoder / Baselines).
Gera tensores .npy e metadados estruturados:
- Treino puramente nominal (exclusão estrita de todos os eventos rotulados).
- Normalização robusta (mediana e MAD) calculada exclusivamente sobre o treino nominal.
- Zero vazamento de dados de validação ou teste.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .connection import get_attached_connection, get_connection, get_db_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_dataset")

DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"


def create_sliding_windows(arr: np.ndarray, window_len: int, step: int) -> np.ndarray:
    """
    Cria janelas deslizantes 3D de forma eficiente (N_janelas, window_len, N_canais).
    """
    n_samples, n_features = arr.shape
    if n_samples < window_len:
        return np.empty((0, window_len, n_features), dtype=arr.dtype)
        
    num_windows = (n_samples - window_len) // step + 1
    shape = (num_windows, window_len, n_features)
    strides = (arr.strides[0] * step, arr.strides[0], arr.strides[1])
    return np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)


def calculate_robust_scaler(data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcula mediana e escala robusta (1.4826 * MAD) por canal.
    Se o MAD for zero, utiliza o desvio médio absoluto ou desvio padrão como salvaguarda.
    """
    mediana = np.median(data, axis=0)
    dev = np.abs(data - mediana)
    mad = np.median(dev, axis=0)
    escala = 1.4826 * mad
    
    # Salvaguardas se escala for 0 (canais constantes ou quantizados)
    for i in range(len(escala)):
        if escala[i] == 0:
            mean_dev = np.mean(dev[:, i])
            escala[i] = mean_dev if mean_dev > 0 else (np.std(data[:, i]) or 1.0)
            
    return mediana, escala


def export_ml_dataset(
    mission: str = "M1",
    split_id: str = "metade_temporal",
    janela_len: int = 60,
    passo: int = 10,
    db_dir: Optional[Path] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """
    Exporta matrizes de treino nominal, validação e teste a partir dos bancos SQLite.
    """
    target_out_dir = Path(out_dir) if out_dir else (DEFAULT_PROCESSED_DIR / mission / split_id)
    target_out_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"[{mission}] Iniciando exportação de dataset ML (split: {split_id})...")
    conn = get_attached_connection(db_dir=db_dir, attach_m1=(mission == "M1"), attach_m2=(mission == "M2"), read_only=True)
    
    try:
        db_alias = "m1" if mission == "M1" else "m2"
        
        # 1. Busca os canais do recorte da missão
        cur = conn.execute(
            "SELECT channel FROM channels WHERE mission = ? AND no_recorte = 1 ORDER BY channel;",
            (mission,)
        )
        channels = [r["channel"] for r in cur.fetchall()]
        if not channels:
            raise ValueError(f"Nenhum canal no recorte para a missão {mission}.")
            
        logger.info(f"[{mission}] Canais do recorte ({len(channels)}): {channels}")
        ch_cols = ", ".join(channels)
        
        # 2. Busca partições do split
        cur = conn.execute(
            "SELECT papel, inicio_ts, fim_ts FROM splits WHERE mission = ? AND split_id = ?;",
            (mission, split_id)
        )
        splits = {r["papel"]: (r["inicio_ts"], r["fim_ts"]) for r in cur.fetchall()}
        if "train" not in splits:
            raise ValueError(f"Split {split_id} não possui partição 'train'.")
            
        train_start, train_end = splits["train"]
        val_start, val_end = splits.get("val", (0, 0))
        test_start, test_end = splits.get("test", (0, 0))
        
        # 3. Busca rótulos válidos da missão para expurgar eventos do treino nominal
        cur = conn.execute(
            "SELECT start_ts, end_ts FROM labels WHERE mission = ? AND valido = 1;",
            (mission,)
        )
        label_intervals = [(r["start_ts"], r["end_ts"]) for r in cur.fetchall()]
        logger.info(f"[{mission}] Total de intervalos rotulados para expurgo no treino: {len(label_intervals)}")
        
        # 4. Carrega telemetria do período de treino de forma eficiente
        logger.info(f"[{mission}] Carregando telemetria de treino via pandas/SQLite...")
        sql_train = f"SELECT ts, {ch_cols} FROM {db_alias}.telemetry WHERE ts >= ? AND ts < ? ORDER BY ts;"
        df_train = pd.read_sql_query(sql_train, conn, params=[train_start, train_end])
        
        if df_train.empty:
            raise ValueError("Nenhum dado encontrado para o período de treino.")
            
        train_ts = df_train["ts"].values
        train_data = df_train[channels].values.astype(np.float64)
        del df_train
        
        # Filtra estritamente leituras nominais (sem colisão com labels)
        nominal_mask = np.ones(len(train_ts), dtype=bool)
        for l_start, l_end in label_intervals:
            if l_end >= train_start and l_start <= train_end:
                nominal_mask &= ~((train_ts >= l_start) & (train_ts <= l_end))
                
        train_nominal = train_data[nominal_mask]
        pct_nominal = 100.0 * len(train_nominal) / len(train_data)
        logger.info(
            f"[{mission}] Treino limpo: {len(train_nominal):,} leituras nominais "
            f"({pct_nominal:.2f}% do período; {len(train_data) - len(train_nominal):,} leituras com rótulo expurgadas)."
        )
        
        # 5. Calcula parâmetros de normalização no treino nominal
        mediana, escala = calculate_robust_scaler(train_nominal)
        
        norm_params = {
            "channels": channels,
            "mediana": mediana.tolist(),
            "escala": escala.tolist(),
        }
        with open(target_out_dir / "norm_params.json", "w", encoding="utf-8") as f:
            json.dump(norm_params, f, indent=2)
            
        train_norm = (train_nominal - mediana) / escala
        del train_data, train_nominal
        
        # 6. Gera janelas de treino
        train_windows = create_sliding_windows(train_norm, janela_len, passo)
        train_win_path = target_out_dir / "train_windows.npy"
        np.save(train_win_path, train_windows)
        logger.info(f"[{mission}] Janelas de treino salvas: shape {train_windows.shape} em {train_win_path.name}")
        del train_norm, train_windows
        
        # 7. Validação (se existir)
        val_win_path = None
        if val_start and val_end > val_start:
            logger.info(f"[{mission}] Carregando e processando partição de validação...")
            sql_val = f"SELECT ts, {ch_cols} FROM {db_alias}.telemetry WHERE ts >= ? AND ts < ? ORDER BY ts;"
            df_val = pd.read_sql_query(sql_val, conn, params=[val_start, val_end])
            val_data = df_val[channels].values.astype(np.float64)
            del df_val
            
            val_norm = (val_data - mediana) / escala
            val_windows = create_sliding_windows(val_norm, janela_len, passo)
            val_win_path = target_out_dir / "val_windows.npy"
            np.save(val_win_path, val_windows)
            logger.info(f"[{mission}] Janelas de validação salvas: shape {val_windows.shape}")
            del val_data, val_norm, val_windows
            
        # 8. Teste (se existir)
        test_win_path = None
        if test_start and test_end > test_start:
            logger.info(f"[{mission}] Carregando e processando partição de teste...")
            sql_test = f"SELECT ts, {ch_cols} FROM {db_alias}.telemetry WHERE ts >= ? AND ts < ? ORDER BY ts;"
            df_test = pd.read_sql_query(sql_test, conn, params=[test_start, test_end])
            test_data = df_test[channels].values.astype(np.float64)
            del df_test
            
            test_norm = (test_data - mediana) / escala
            test_windows = create_sliding_windows(test_norm, janela_len, passo)
            test_win_path = target_out_dir / "test_windows.npy"
            np.save(test_win_path, test_windows)
            logger.info(f"[{mission}] Janelas de teste salvas: shape {test_windows.shape}")
            del test_data, test_norm, test_windows
            
        # 9. Salva resumo de metadados do dataset
        summary = {
            "mission": mission,
            "split_id": split_id,
            "janela_len": janela_len,
            "passo": passo,
            "channels": channels,
            "arquivos": {
                "norm_params": "norm_params.json",
                "train_windows": "train_windows.npy",
                "val_windows": "val_windows.npy" if val_win_path else None,
                "test_windows": "test_windows.npy" if test_win_path else None,
            },
        }
        with open(target_out_dir / "dataset_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
            
        logger.info(f"[{mission}] Dataset exportado com sucesso em: {target_out_dir}")
        return {k: str(v) for k, v in summary["arquivos"].items() if v}
        
    finally:
        conn.close()
