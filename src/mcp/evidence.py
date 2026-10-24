"""Monta evidências estruturadas; valores numéricos são calculados fora da LLM."""
from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Optional, Sequence

from .history import history_cutoff
from .tools.alert_track_record import alert_track_record
from .tools.check_data_quality import check_data_quality
from .tools.find_similar_events import find_similar_events
from .config import DELTA_TC_MINUTOS
from .tools.recent_commands import recent_commands
from .utils import iso_to_ms, validate_mission


def build_evidence(mission: str, ts_inicio_iso: str, ts_fim_iso: str,
                   canais: Sequence[str], scores: Optional[dict] = None,
                   alert_id: Optional[int] = None, db_dir: Optional[Path] = None) -> dict:
    """Cria pacote auditável para um alerta; exclui anotações do período do alerta."""
    validate_mission(mission)
    start_ms = iso_to_ms(ts_inicio_iso)
    end_ms = iso_to_ms(ts_fim_iso)
    command_window_minutes = max(DELTA_TC_MINUTOS, ceil((end_ms - start_ms) / 60_000))
    return {
        "alert_id": alert_id,
        "missao": mission,
        "periodo": {"inicio": ts_inicio_iso, "fim": ts_fim_iso},
        "canais_afetados": sorted(set(canais)),
        "scores_detector": scores or {},
        "qualidade_dos_dados": check_data_quality(mission, ts_inicio_iso, ts_fim_iso, db_dir),
        "telecomandos_recentes": recent_commands(
            mission, ts_inicio_iso, db_dir, delta_minutos=command_window_minutes
        ),
        "eventos_similares": find_similar_events(mission, ts_inicio_iso, canais, db_dir),
        "historico_de_alertas": alert_track_record(mission, ts_inicio_iso, db_dir),
        "limite_historico_ms": history_cutoff(mission, db_dir),
        "timestamp_alerta_ms": end_ms,
        "nota": "Contexto histórico limitado a treino+validação; anotações do período atual não são usadas.",
    }

