"""
Utilitários compartilhados do módulo MCP.

Funções de conversão de timestamps e helpers sem dependências externas pesadas.
"""

from __future__ import annotations

from datetime import datetime, timezone


def iso_to_ms(iso_str: str) -> int:
    """Converte string ISO 8601 (UTC) para timestamp em milissegundos epoch."""
    import pandas as pd

    return int(pd.to_datetime(iso_str, utc=True).timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    """Converte timestamp em milissegundos epoch para string ISO 8601 (UTC)."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    if ms % 1000:
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_datetime(ms: int) -> datetime:
    """Converte timestamp em milissegundos epoch para objeto datetime UTC."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def validate_mission(mission: str) -> None:
    """Valida que a missão é suportada; levanta ValueError caso contrário."""
    from .config import MISSIONS

    if mission not in MISSIONS:
        raise ValueError(f"Missão inválida: '{mission}'. Suportadas: {sorted(MISSIONS)}")


def validate_window(ts_inicio_ms: int, ts_fim_ms: int) -> None:
    """Valida que a janela temporal é não-vazia e está na ordem correta."""
    if ts_inicio_ms >= ts_fim_ms:
        raise ValueError(
            f"ts_inicio ({ts_inicio_ms}) deve ser anterior a ts_fim ({ts_fim_ms})."
        )
