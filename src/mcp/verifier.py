"""Verificador conservador das regras de segurança R1–R8."""
from __future__ import annotations

import re

from .config import MIN_AMOSTRA_HISTORICO

HEADINGS = ("o que aconteceu", "por que o sistema avisou", "o que pode explicar",
            "quanto confiar", "o que verificar")
TECHNICAL_TERMS = ("MAD", "telemetria", "telecomando", "anomalia", "baseline", "score",
                   "desvio normalizado")
BAD_ADVICE = re.compile(r"\b(ignorar|ignore|desconsidere|descartar o alerta)\b", re.I)
CONFIRMED_FAILURE = re.compile(r"\b(falha confirmada|componente falhou|está quebrado)\b", re.I)
ACTION_WORDS = re.compile(
    r"\b(monitor(?:e|ar|ando)?|verifi(?:que|car|cando)|chec(?:ar|que|ando)|"
    r"confirme|confirmar|acompanhe|acompanhar|compare|comparar|registre|registrar|"
    r"comunique|comunicar|acione|acionar|escale|escalar|revise|revisar|"
    r"inspecione|inspecionar|consulte|consultar)\b",
    re.I,
)
SECTION_PATTERN = re.compile(
    r"(?im)^\s*\**\s*(?:\d+[.)]\s*)?(o que aconteceu|por que o sistema avisou|"
    r"o que pode explicar|quanto confiar|o que verificar)\s*\**\s*:?[ \t]*"
)


def verify_explanation(text: str, evidence: dict) -> dict:
    violations: list[str] = []
    allowed = set(evidence.get("canais_afetados", []))
    allowed.update(x.get("telecommand") for x in evidence.get("telecomandos_recentes", {}).get("comandos", []))
    # Identificadores em linguagem natural devem estar presentes no pacote.
    for identifier in re.findall(r"\b(?:channel|telecommand|subsystem)_\d+\b", text, re.I):
        if identifier.lower() not in {str(x).lower() for x in allowed}:
            violations.append("R1")
            break
    text_for_numbers = re.sub(r"\b(?:channel|telecommand|subsystem)_\d+\b", "", text, flags=re.I)
    text_for_numbers = re.sub(r"\b\d{4}-\d{2}-\d{2}T[\d:.+-]+Z?\b", "", text_for_numbers)
    text_for_numbers = re.sub(r"(?m)^\s*\**\s*[1-5][.)]\s*.*?\**\s*$", "", text_for_numbers)
    numbers = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?", text_for_numbers)
    allowed_numbers: set[str] = set()

    def collect(value, key=""):
        if isinstance(value, dict):
            for child_key, child in value.items():
                if not any(marker in child_key.lower() for marker in ("_id", "_ms", "inicio", "fim", "periodo", "canal")):
                    collect(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed_numbers.add(str(value).replace(",", "."))

    collect(evidence)
    for token in numbers:
        raw = token.rstrip("%").replace(",", ".")
        if raw not in allowed_numbers:
            violations.append("R2")
            break
    if BAD_ADVICE.search(text): violations.append("R3")
    if CONFIRMED_FAILURE.search(text): violations.append("R4")
    similar = evidence.get("eventos_similares", {})
    commands = evidence.get("telecomandos_recentes", {}).get("total", 0)
    asserts_normal = re.search(r"\b(é normal|está normal|comportamento normal|é nominal|é esperado|rotineiro)\b", text, re.I)
    negates_normal = re.search(r"\b(não|sem|nenhuma|nenhum)\b.{0,30}\b(normal|nominal|esperado|rotineiro)\b", text, re.I)
    if asserts_normal and not negates_normal and not (similar.get("nominal", 0) > 0 or commands > 0):
        violations.append("R5")
    n = evidence.get("eventos_similares", {}).get("total_encontrado", 0)
    if n < MIN_AMOSTRA_HISTORICO and not re.search(
        r"\b(incerto|incerteza|insuficiente|poucos dados|não é possível concluir|limitada|"
        r"amostra(?: histórica)?(?: é)? pequena|amostra reduzida)\b",
        text,
        re.I,
    ):
        violations.append("R6")
    undefined = []
    for term in TECHNICAL_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text, re.I):
            after = text[re.search(rf"\b{re.escape(term)}\b", text, re.I).end():]
            if not re.match(r"\s*(?:\([^)]{3,}\)|,?\s*(?:que é|que significa|isto é|ou seja)\b)", after, re.I):
                undefined.append(term)
    if undefined:
        violations.append("R7")
    if any(heading not in text.casefold() for heading in HEADINGS): violations.append("R8")

    sections = list(SECTION_PATTERN.finditer(text))
    section_contents = {
        match.group(1).casefold(): text[match.end():sections[index + 1].start() if index + 1 < len(sections) else len(text)]
        for index, match in enumerate(sections)
    }
    action_section = section_contents.get("o que verificar", "")
    if not ACTION_WORDS.search(action_section):
        violations.append("R9")

    word_count = len(re.findall(r"\b[\wÀ-ÿ-]+\b", text))
    if word_count < 60 or any(
        len(re.findall(r"\b[\wÀ-ÿ-]+\b", section)) < 8
        for section in section_contents.values()
    ):
        violations.append("R10")
    violations = list(dict.fromkeys(violations))
    return {"ok": not violations, "regras_violadas": violations}

