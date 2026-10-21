"""
Script Orquestrador Geral do Pipeline de Dados ESA-ADB.
Executa as fases de construção, validação e exportação descritas em 'Arquitetura do Banco de Dados.md'.

Uso:
    python -m src.db.build_all --m1-dir "C:/path/to/ESA-Mission1" [--m2-dir "C:/path/to/ESA-Mission2"] [--export-ml]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .build_catalog import build_catalog_from_dir
from .build_telemetry import build_telemetry_m1, build_telemetry_m2
from .connection import init_db
from .export_dataset import export_ml_dataset
from .verify_integrity import run_full_validation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_all")


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrói o ecossistema de bancos de dados ESA-ADB.")
    parser.add_argument(
        "--m1-dir",
        type=str,
        default=r"C:\Users\josej\Downloads\ESA-Mission1\ESA-Mission1",
        help="Caminho do diretório raiz da Mission 1 (contendo channels.csv, labels.csv, etc.)",
    )
    parser.add_argument(
        "--m2-dir",
        type=str,
        default=None,
        help="Caminho do diretório raiz da Mission 2 (opcional)",
    )
    parser.add_argument(
        "--db-dir",
        type=str,
        default=None,
        help="Diretório onde os bancos SQLite serão criados (padrão: data/db/)",
    )
    parser.add_argument(
        "--skip-telemetry",
        action="store_true",
        help="Se ativado, pula a carga pesada de telemetria e constrói apenas o catálogo",
    )
    parser.add_argument(
        "--export-ml",
        action="store_true",
        help="Se ativado, exporta os datasets de machine learning (.npy) após a validação",
    )
    args = parser.parse_args()

    t0 = time.time()
    logger.info("======================================================================")
    logger.info("INICIANDO CONSTRUÇÃO COMPLETA DO BANCO DE DADOS ESA-ADB")
    logger.info("======================================================================")

    # 1. Catálogo unificado
    logger.info("FASE 1: Construindo catálogo unificado esa_catalog.sqlite...")
    m1_path = Path(args.m1_dir) if args.m1_dir else None
    m2_path = Path(args.m2_dir) if args.m2_dir else None
    db_path = Path(args.db_dir) if args.db_dir else None

    build_catalog_from_dir(m1_dir=m1_path, m2_dir=m2_path, db_dir=db_path, recreate=True)

    # 2. Banco de experimentos inicial
    logger.info("FASE 2: Inicializando banco de experimentos esa_experiments.sqlite...")
    init_db("esa_experiments", "schema_experiments.sql", db_dir=db_path, recreate=False)

    # 3. Séries temporais da Mission 1
    if not args.skip_telemetry and m1_path and m1_path.exists():
        logger.info("FASE 3: Ingerindo séries temporais e telecomandos da Mission 1...")
        build_telemetry_m1(m1_dir=m1_path, db_dir=db_path, recreate=True)

    # 4. Séries temporais da Mission 2 (se fornecido)
    if not args.skip_telemetry and m2_path and m2_path.exists():
        logger.info("FASE 4: Ingerindo séries temporais e telecomandos da Mission 2...")
        build_telemetry_m2(m2_dir=m2_path, db_dir=db_path, recreate=True)

    # 5. Auditoria e verificação de integridade
    logger.info("FASE 5: Executando checagens de integridade e consistência relacional...")
    val_ok = run_full_validation(db_dir=db_path)
    if not val_ok:
        logger.error("A validação encontrou inconsistências. Verifique o log acima.")
        return 1

    # 6. Exportação para ML (opcional)
    if args.export_ml:
        logger.info("FASE 6: Exportando datasets para treino do Autoencoder (.npy)...")
        export_ml_dataset(mission="M1", split_id="metade_temporal", db_dir=db_path)

    elapsed = time.time() - t0
    logger.info("======================================================================")
    logger.info(f"PIPELINE CONCLUÍDO COM SUCESSO EM {elapsed:.1f} SEGUNDOS!")
    logger.info("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
