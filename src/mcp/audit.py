"""Persistência comum das interações do copiloto no banco de experimentos."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.db.connection import get_connection, init_db
from .config import DEFAULT_DB_DIR


def record_explanation(evidence: dict, answer: str, verification: dict,
                       tool_name: str, model: str, temperature: float | None = None,
                       db_dir: Path | None = None) -> int:
    db = db_dir or DEFAULT_DB_DIR
    init_db("esa_experiments", "schema_experiments.sql", db_dir=db)
    conn = get_connection("esa_experiments", db_dir=db)
    try:
        cur = conn.execute(
            """INSERT INTO explanations
               (alert_id,tool_name,pacote_json,resposta_bruta,verificador_ok,regras_violadas,
                modelo_llm,temperatura,criado_em) VALUES (?,?,?,?,?,?,?,?,?)""",
            (evidence.get("alert_id"), tool_name,
             json.dumps(evidence, ensure_ascii=False), answer,
             int(verification["ok"]), json.dumps(verification["regras_violadas"]),
             model, temperature, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()
