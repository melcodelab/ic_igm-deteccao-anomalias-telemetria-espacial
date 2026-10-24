"""Prepara pacotes de replay e, quando fornecidas, verifica respostas do host MCP."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from src.db.connection import DEFAULT_DB_DIR, get_connection, init_db
from src.mcp.audit import record_explanation
from src.mcp.config import CHANNELS, HOST_MODELO_PADRAO, SPLIT_ID_PADRAO
from src.mcp.evidence import build_evidence
from src.mcp.utils import ms_to_iso
from src.mcp.verifier import verify_explanation
from .metrics import calculate_metrics


def replay(mission: str, db_dir: Path = DEFAULT_DB_DIR, limit: int | None = None,
           answers: dict | None = None, prepare_ablations: bool = False,
           host_model: str = HOST_MODELO_PADRAO) -> dict:
    """Cria evidência de casos do split de teste; não faz chamadas a provedores LLM."""
    init_db("esa_experiments", "schema_experiments.sql", db_dir=db_dir)
    conn = get_connection("esa_catalog", read_only=True, db_dir=db_dir)
    try:
        split = SPLIT_ID_PADRAO[mission]
        bounds = conn.execute(
            "SELECT inicio_ts,fim_ts FROM splits WHERE mission=? AND split_id=? AND papel='test' ORDER BY inicio_ts",
            (mission, split),
        ).fetchall()
        if not bounds:
            raise RuntimeError(f"Split de teste ausente: {mission}/{split}")
        clauses = " OR ".join("(e.start_ts<? AND e.end_ts>=?)" for _ in bounds)
        params = [v for row in bounds for v in (row[1], row[0])]
        events = conn.execute(
            f"SELECT e.event_id,e.category,e.start_ts,e.end_ts FROM events e WHERE e.mission=? AND ({clauses}) ORDER BY e.start_ts",
            [mission, *params],
        ).fetchall()
        if limit:
            events = events[:limit]
        records = []
        answer_map = answers or {}
        for event in events:
            labeled_channels = [r[0] for r in conn.execute(
                "SELECT DISTINCT channel FROM labels WHERE mission=? AND event_id=? AND valido=1 ORDER BY channel",
                (mission, event[0]),
            ).fetchall()]
            channels = [channel for channel in labeled_channels if channel in CHANNELS[mission]]
            start, end = int(event[2]), int(event[3])
            evidence = build_evidence(mission, ms_to_iso(start), ms_to_iso(end), channels,
                                      alert_id=None, db_dir=db_dir)
            entry = answer_map.get(event[0]) or {}
            if isinstance(entry, str):
                entry = {"resposta": entry}
            answer = entry.get("resposta")
            verification = None
            if answer:
                verification = verify_explanation(answer, evidence)
                record_explanation(evidence, answer, verification, "replay", host_model, None, db_dir)
            ablations = {}
            ablation_evidence = {}
            variants = {
                "sem_historico": "eventos_similares",
                "sem_telecomandos": "telecomandos_recentes",
                "sem_qualidade": "qualidade_dos_dados",
            }
            if prepare_ablations:
                for variant, key in variants.items():
                    packet = copy.deepcopy(evidence)
                    packet.pop(key, None)
                    ablation_evidence[variant] = packet
                    variant_answer = entry.get("ablation_responses", {}).get(variant)
                    if variant_answer:
                        result = verify_explanation(variant_answer, packet)
                        record_explanation(packet, variant_answer, result,
                                           f"replay_{variant}", host_model, None, db_dir)
                        ablations[variant] = {**result, "resposta": variant_answer}
            repeated_answers = entry.get("repeticoes", [])
            for repeated in repeated_answers:
                repeated_check = verify_explanation(repeated, evidence)
                record_explanation(evidence, repeated, repeated_check,
                                   "replay_repeticao", host_model, None, db_dir)
            records.append({"event_id": event[0], "categoria": event[1],
                            "canais_rotulados": channels, "evidencia": evidence,
                            "resposta": answer or "",
                            "regras_violadas": verification["regras_violadas"] if verification else [],
                            "bloqueada": not verification["ok"] if verification else None,
                            "n_historico": evidence["eventos_similares"]["total_encontrado"],
                            "n_alertas_historicos": evidence["historico_de_alertas"].get("n", 0),
                            "ablations": ablations, "ablation_evidencias": ablation_evidence,
                            "repeticoes": repeated_answers})
        return {"mission": mission, "split": split, "records": records,
                "metrics": calculate_metrics(records)}
    finally:
        conn.close()


def _predicted_category(answer: str) -> str | None:
    text = answer.casefold()
    if "anomalia" in text:
        return "Anomaly"
    if "evento raro" in text or "nominal" in text:
        return "Rare Event"
    return None


def render_cases(records: list[dict]) -> str:
    """Gera casos encontrados no replay; nunca inventa exemplos ausentes."""
    evaluated = [r for r in records if r.get("resposta")]
    good = next((r for r in evaluated if r["bloqueada"] is False and
                 _predicted_category(r["resposta"]) == r["categoria"]), None)
    blocked = next((r for r in evaluated if r["bloqueada"] is True), None)
    missed = next((r for r in evaluated if r["bloqueada"] is False and
                   _predicted_category(r["resposta"]) not in (None, r["categoria"])), None)
    sections = ["# Casos do replay MCP", "",
                "Gerado a partir das respostas fornecidas pelo host MCP. Casos ausentes não são substituídos por exemplos fictícios.", ""]
    for title, record in (("Explicação aceita e categoria correta", good),
                          ("Resposta barrada pelo verificador", blocked),
                          ("Erro de categoria não barrado", missed)):
        sections.extend([f"## {title}", ""])
        if record is None:
            sections.extend(["Não observado nos casos avaliados.", ""])
            continue
        sections.extend([f"- Evento: `{record['event_id']}` ({record['categoria']})",
                         f"- Canais anotados: {', '.join(record['canais_rotulados']) or 'nenhum'}",
                         f"- Verificador: {'barrada' if record['bloqueada'] else 'aceita'}; violações: {', '.join(record['regras_violadas']) or 'nenhuma'}",
                         "", "Resposta fornecida pelo host:", "", record["resposta"], ""])
    return "\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", choices=("M1", "M2"), required=True)
    parser.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR)
    parser.add_argument("--limit", type=int, help="Limita casos para um replay piloto")
    parser.add_argument("--answers-json", type=Path,
                        help="Respostas produzidas pelo host, indexadas por event_id")
    parser.add_argument("--host-model", default=HOST_MODELO_PADRAO,
                        help="Rótulo para registrar qual host/modelo produziu o texto")
    parser.add_argument("--prepare-ablations", action="store_true",
                        help="Inclui pacotes sem histórico, telecomandos e qualidade")
    parser.add_argument("--output", type=Path, default=Path("reports/replay"))
    parser.add_argument("--cases-output", type=Path, default=Path("reports/cases.md"))
    args = parser.parse_args()
    answer_map = json.loads(args.answers_json.read_text(encoding="utf-8")) if args.answers_json else None
    result = replay(args.mission, args.db_dir, args.limit, answer_map,
                    args.prepare_ablations, args.host_model)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"{args.mission.lower()}_replay.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.cases_output.parent.mkdir(parents=True, exist_ok=True)
    args.cases_output.write_text(render_cases(result["records"]), encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
