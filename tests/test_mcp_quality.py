from src.mcp.tools.check_data_quality import _classify_quality_severity
from src.mcp.utils import ms_to_iso
from src.mcp.verifier import verify_explanation


def test_quality_severity_uses_worst_impact():
    assert _classify_quality_severity(0, 0, 0, False) == "boa"
    assert _classify_quality_severity(0.1, 9, 0, True) == "leve"
    assert _classify_quality_severity(0, 20, 0, True) == "moderada"
    assert _classify_quality_severity(0, 40, 0, True) == "grave"


def test_ms_to_iso_preserves_millisecond_boundaries():
    assert ms_to_iso(1_000) == "1970-01-01T00:00:01Z"
    assert ms_to_iso(1_001) == "1970-01-01T00:00:01.001Z"


def test_verifier_requires_clear_sections_and_concrete_action():
    evidence = {"eventos_similares": {"total_encontrado": 5}}
    answer = """**1. O que aconteceu**
    O período monitorado apresentou uma alteração nos dados observados durante o turno.
    **2. Por que o sistema avisou**
    O aviso foi gerado porque o comportamento medido ultrapassou os critérios definidos para acompanhamento.
    **3. O que pode explicar**
    Os dados disponíveis descrevem o comportamento, mas não permitem determinar a causa física dessa alteração.
    **4. Quanto confiar**
    Há referências históricas suficientes para comparação, embora elas não confirmem o diagnóstico de um componente.
    **5. O que verificar**
    Monitore as próximas leituras e compare a evolução com os demais canais antes de escalar para a equipe responsável.
    """

    result = verify_explanation(answer, evidence)
    assert result == {"ok": True, "regras_violadas": []}


def test_verifier_rejects_short_answer_without_action():
    answer = """O que aconteceu: dados alterados.
    Por que o sistema avisou: houve uma variação.
    O que pode explicar: não é possível concluir.
    Quanto confiar: incerteza.
    O que verificar: aguardar.
    """

    result = verify_explanation(answer, {"eventos_similares": {"total_encontrado": 0}})
    assert "R9" in result["regras_violadas"]
    assert "R10" in result["regras_violadas"]


def test_verifier_recognizes_action_after_inline_heading():
    answer = """O que aconteceu: o canal apresentou uma alteração relevante durante o período analisado.
    Por que o sistema avisou: os valores observados diferiram do comportamento histórico esperado.
    O que pode explicar: não é possível determinar a causa física apenas com os dados disponíveis.
    Quanto confiar: a amostra histórica é pequena e a qualidade dos dados limita as conclusões.
    O que verificar: monitore as próximas leituras e comunique a equipe responsável se persistir.
    """

    result = verify_explanation(answer, {"eventos_similares": {"total_encontrado": 2}})
    assert "R9" not in result["regras_violadas"]
    assert "R10" not in result["regras_violadas"]