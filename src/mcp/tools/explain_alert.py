"""Orquestra evidências, geração opcional, verificação e auditoria de uma explicação."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from ..audit import record_explanation
from ..config import DEFAULT_DB_DIR, HOST_MODELO_PADRAO
from ..evidence import build_evidence
from ..verifier import verify_explanation


def explain_alert(mission: str, ts_inicio_iso: str, ts_fim_iso: str,
                  canais: Sequence[str], scores: Optional[dict] = None,
                  alert_id: Optional[int] = None, db_dir: Optional[Path] = None,
                  resposta: Optional[str] = None) -> dict:
    """Monta evidências para alerta detectado; verifica texto do host se fornecido."""
    db = db_dir or DEFAULT_DB_DIR
    evidence = build_evidence(mission, ts_inicio_iso, ts_fim_iso, canais, scores, alert_id, db)
    if resposta is None:
        return {
            "alert_id": alert_id,
            "alerta_mantido": True,
            "evidencia": evidence,
            "instrucao": "Use as evidências para redigir a explicação e envie o texto para verificação.",
            "verificacao": None,
        }
    answer = resposta
    verification = verify_explanation(answer, evidence)
    record_explanation(evidence, answer, verification, "explain_alert",
                       HOST_MODELO_PADRAO, None, db)
    return {"alert_id": alert_id, "alerta_mantido": True, "evidencia": evidence,
            "resposta": answer if verification["ok"] else None,
            "resposta_bloqueada": not verification["ok"], "verificacao": verification}

