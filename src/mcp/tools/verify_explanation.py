"""Verifica e audita texto redigido pelo modelo do host MCP."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..audit import record_explanation
from ..config import DEFAULT_DB_DIR, HOST_MODELO_PADRAO
from ..verifier import verify_explanation


def verify_host_explanation(evidence: dict, resposta: str,
                            host_model: str = HOST_MODELO_PADRAO,
                            db_dir: Optional[Path] = None) -> dict:
    result = verify_explanation(resposta, evidence)
    record_explanation(evidence, resposta, result, "verify_host_explanation",
                       host_model, None, db_dir or DEFAULT_DB_DIR)
    return {**result, "resposta_aprovada": resposta if result["ok"] else None,
            "alerta_mantido": True}
