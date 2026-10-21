"""
Módulo de Banco de Dados e Engenharia de Datasets para ESA-ADB (MCP + Autoencoder).
Arquitetura em 4 arquivos SQLite:
- esa_catalog.sqlite (catálogo, rótulos, eventos derivados, janelas, splits)
- esa_m1.sqlite (telemetria multivariada e telecomandos da Mission1)
- esa_m2.sqlite (telemetria multivariada e telecomandos da Mission2)
- esa_experiments.sqlite (execuções, scores, alertas e métricas)
"""

from .connection import (
    DEFAULT_DB_DIR,
    DEFAULT_SQL_DIR,
    get_attached_connection,
    get_connection,
    get_db_path,
    init_db,
)
from .build_catalog import build_catalog_from_dir
from .build_telemetry import build_telemetry_m1, build_telemetry_m2
from .verify_integrity import run_full_validation
from .export_dataset import export_ml_dataset

__all__ = [
    "DEFAULT_DB_DIR",
    "DEFAULT_SQL_DIR",
    "get_connection",
    "get_attached_connection",
    "get_db_path",
    "init_db",
    "build_catalog_from_dir",
    "build_telemetry_m1",
    "build_telemetry_m2",
    "run_full_validation",
    "export_ml_dataset",
]
