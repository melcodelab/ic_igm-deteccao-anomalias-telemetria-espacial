"""Métricas calculadas sobre resultados salvos pelo replay."""
from __future__ import annotations

import re


def calculate_metrics(records: list[dict]) -> dict:
    package_count = len(records)
    records = [record for record in records if record.get("resposta")]
    total = len(records)
    violation_counts: dict[str, int] = {}
    channel_tp = channel_fp = channel_fn = 0
    category_ok = category_n = dangerous_errors = 0
    history_bins: dict[str, list[bool]] = {"0": [], "1-4": [], "5+": []}
    ablation_results: dict[str, list[tuple[dict, dict]]] = {}
    repeat_stabilities = []
    for record in records:
        for rule in record.get("regras_violadas", []):
            violation_counts[rule] = violation_counts.get(rule, 0) + 1
        cited = set(re.findall(r"\bchannel_\d+\b", record.get("resposta", ""), re.I))
        expected = set(record.get("canais_rotulados", []))
        channel_tp += len(cited & expected)
        channel_fp += len(cited - expected)
        channel_fn += len(expected - cited)
        category = record.get("categoria")
        answer = record.get("resposta", "").casefold()
        if category in ("Anomaly", "Rare Event"):
            category_n += 1
            predicted_anomaly = "anomalia" in answer
            predicted_rare = "evento raro" in answer or "nominal" in answer
            predicted = "Anomaly" if predicted_anomaly else "Rare Event" if predicted_rare else None
            category_ok += predicted == category
            if category == "Anomaly" and predicted == "Rare Event":
                dangerous_errors += 1
            n_history = record.get("n_alertas_historicos", record.get("n_historico", 0))
            bucket = "0" if n_history == 0 else "1-4" if n_history < 5 else "5+"
            history_bins[bucket].append(predicted == category)
        for variant, result in record.get("ablations", {}).items():
            ablation_results.setdefault(variant, []).append((record, result))
        repeated = record.get("repeticoes", [])
        if repeated:
            outputs = [record.get("resposta", "")] + repeated
            normalized = [re.sub(r"\s+", " ", output.strip().casefold()) for output in outputs]
            repeat_stabilities.append(max(normalized.count(x) for x in set(normalized)) / len(normalized))
    return {
        "n_explicacoes": total,
        "n_pacotes_preparados": package_count,
        "M1_violacoes": {"por_regra": violation_counts,
                         "taxa_com_violacao": sum(bool(r.get("regras_violadas")) for r in records) / total if total else None},
        "M2_canais": {"precision": channel_tp / (channel_tp + channel_fp) if channel_tp + channel_fp else None,
                       "recall": channel_tp / (channel_tp + channel_fn) if channel_tp + channel_fn else None,
                       "tp": channel_tp, "fp": channel_fp, "fn": channel_fn},
        "M3_categoria": {"acuracia": category_ok / category_n if category_n else None,
                         "n": category_n, "anomalia_tratada_como_nominal": dangerous_errors},
        "M4_ablation_contexto": {variant: _ablation_metrics(values, records)
                                 for variant, values in ablation_results.items()},
        "M5_estabilidade": {"consistencia_exata_normalizada":
            sum(repeat_stabilities) / len(repeat_stabilities) if repeat_stabilities else None,
            "n_casos_repetidos": len(repeat_stabilities)},
        "M6_historico": {bucket: {"acuracia_categoria": sum(values) / len(values) if values else None,
                                  "n": len(values)} for bucket, values in history_bins.items()},
    }


def _ablation_metrics(pairs: list[tuple[dict, dict]]) -> dict:
    tp = fp = fn = category_correct = category_n = dangerous = passed = 0
    for record, result in pairs:
        passed += bool(result.get("ok"))
        cited = set(re.findall(r"\bchannel_\d+\b", result.get("resposta", ""), re.I))
        expected = set(record.get("canais_rotulados", []))
        tp += len(cited & expected)
        fp += len(cited - expected)
        fn += len(expected - cited)
        category = record.get("categoria")
        if category in ("Anomaly", "Rare Event"):
            text = result.get("resposta", "").casefold()
            predicted = "Anomaly" if "anomalia" in text else "Rare Event" if "evento raro" in text or "nominal" in text else None
            category_n += 1
            category_correct += predicted == category
            dangerous += category == "Anomaly" and predicted == "Rare Event"
    n = len(pairs)
    return {"taxa_aprovacao": passed / n if n else None,
            "precision_canais": tp / (tp + fp) if tp + fp else None,
            "recall_canais": tp / (tp + fn) if tp + fn else None,
            "acuracia_categoria": category_correct / category_n if category_n else None,
            "anomalia_como_nominal": dangerous, "n": n}
