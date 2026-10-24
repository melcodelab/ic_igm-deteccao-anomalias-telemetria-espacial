"""Servidor MCP read-only para as ferramentas do copiloto espacial."""
from __future__ import annotations

from fastmcp import FastMCP

from .tools.analyze_window import analyze_window
from .tools.alert_track_record import alert_track_record
from .tools.check_data_quality import check_data_quality
from .tools.explain_alert import explain_alert
from .tools.find_similar_events import find_similar_events
from .tools.shift_summary import shift_summary
from .tools.verify_explanation import verify_host_explanation

mcp = FastMCP("Copiloto de Monitoramento Espacial")


@mcp.tool()
def tool_analyze_window(mission: str, ts_inicio_iso: str, ts_fim_iso: str) -> dict:
    """Resume estado e qualidade dos canais num intervalo UTC."""
    return analyze_window(mission, ts_inicio_iso, ts_fim_iso)


@mcp.tool()
def tool_check_data_quality(mission: str, ts_inicio_iso: str, ts_fim_iso: str) -> dict:
    """Verifica lacunas, canais congelados e valores ausentes."""
    return check_data_quality(mission, ts_inicio_iso, ts_fim_iso)


@mcp.tool()
def tool_find_similar_events(mission: str, ts_referencia_iso: str, canais: list[str] | None = None) -> dict:
    """Busca eventos históricos em treino+validação, sem consultar o teste."""
    return find_similar_events(mission, ts_referencia_iso, canais)


@mcp.tool()
def tool_alert_track_record(mission: str, ts_referencia_iso: str) -> dict:
    """Resume acertos anotados de alertas anteriores, sem tratar casos sem rótulo como falsos."""
    return alert_track_record(mission, ts_referencia_iso)


@mcp.tool()
def tool_explain_alert(mission: str, ts_inicio_iso: str, ts_fim_iso: str,
                       canais: list[str], scores: dict | None = None,
                       alert_id: int | None = None) -> dict:
    """Monta evidências para o host; envie a resposta gerada à tool de verificação."""
    return explain_alert(mission, ts_inicio_iso, ts_fim_iso, canais, scores, alert_id)


@mcp.tool()
def tool_verify_explanation(evidencia: dict, resposta: str) -> dict:
    """Verifica resposta do modelo host e audita o resultado antes de ser apresentada."""
    return verify_host_explanation(evidencia, resposta)


@mcp.tool()
def tool_shift_summary(mission: str, ts_inicio_iso: str, ts_fim_iso: str) -> dict:
    """Produz um resumo estruturado do turno/período."""
    return shift_summary(mission, ts_inicio_iso, ts_fim_iso)


@mcp.resource("resource://copiloto/glossary")
def glossary() -> str:
    """Glossário de termos da missão e do sistema."""
    from .config import RESOURCES_DIR
    return (RESOURCES_DIR / "glossary.md").read_text(encoding="utf-8")


@mcp.prompt()
def explanation_template() -> str:
    """Roteiro obrigatório de cinco partes para explicações de alertas."""
    from .config import RESOURCES_DIR
    template = (RESOURCES_DIR / "explanation_template.md").read_text(encoding="utf-8")
    glossary = (RESOURCES_DIR / "glossary.md").read_text(encoding="utf-8")
    return f"{template}\n\n## Glossário de referência obrigatória\n\n{glossary}"


if __name__ == "__main__":
    mcp.run()

