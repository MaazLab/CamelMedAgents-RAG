from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

from scrapers.patient_info.config import JSONL_INPUT_PATH
from scrapers.patient_info.database import Database
from scrapers.patient_info.logger import get_logger

logger = get_logger("query_loader")


def build_query_representation(record: dict) -> str:
    """Build a parameter-enriched natural language text from ALL available parameters."""
    parts: list[str] = []

    # Disease label
    label = record.get("label", "")
    if label:
        parts.append(f"{label.capitalize()} patient.")

    # Symptoms
    symptoms = record.get("symptoms") or []
    if symptoms:
        symptom_descs: list[str] = []
        for s in symptoms:
            name = s.get("normalized_name") or s.get("name") or ""
            if not name:
                continue
            qualifiers: list[str] = []
            severity = s.get("severity")
            if severity:
                qualifiers.append(severity)
            qualifiers.append(name)
            location = s.get("anatomical_location")
            if location:
                qualifiers.append(f"on {location}")
            symptom_descs.append(" ".join(qualifiers))
        if symptom_descs:
            parts.append(f"Symptoms: {', '.join(symptom_descs)}.")

    # Duration
    duration = record.get("duration")
    if duration and isinstance(duration, dict):
        dur_val = duration.get("value")
        onset = duration.get("onset_type")
        if dur_val:
            dur_str = f"Duration: {dur_val}"
            if onset:
                dur_str += f" ({onset} onset)"
            parts.append(dur_str + ".")

    # Frequency
    freq = record.get("frequency")
    if freq:
        parts.append(f"Frequency: {freq}.")

    # Triggers
    triggers = record.get("triggers") or []
    if triggers:
        parts.append(f"Triggers: {', '.join(str(t) for t in triggers)}.")

    # Symptom-temporal map (per-symptom duration/onset, more granular than overall duration)
    stm = record.get("symptom_temporal_map") or []
    if stm:
        stm_descs: list[str] = []
        for entry in stm:
            symptom = entry.get("symptom", "")
            dur_days = entry.get("duration_days", 0)
            onset = entry.get("onset_type", "")
            if symptom:
                desc = symptom
                if dur_days:
                    desc += f" for {dur_days} days"
                if onset:
                    desc += f" ({onset})"
                stm_descs.append(desc)
        if stm_descs:
            parts.append(f"Symptom timeline: {', '.join(stm_descs)}.")

    # Patient context
    pc = record.get("patient_context")
    if pc and isinstance(pc, dict):
        ctx_parts: list[str] = []
        age = pc.get("age")
        age_group = pc.get("age_group")
        gender = pc.get("gender")
        if age:
            ctx_parts.append(f"{age} year old")
        elif age_group:
            ctx_parts.append(age_group)
        if gender:
            ctx_parts.append(gender)
        pregnancy = pc.get("pregnancy_status")
        if pregnancy:
            ctx_parts.append(pregnancy)
        comorbidities = pc.get("comorbidities") or []
        if comorbidities:
            ctx_parts.append(f"with {', '.join(comorbidities)}")
        if ctx_parts:
            parts.append(f"Patient: {' '.join(ctx_parts)}.")

    # Clinical interpretation
    ci = record.get("clinical_interpretation")
    if ci and isinstance(ci, dict):
        intent = ci.get("intent")
        if intent:
            parts.append(f"Seeking {intent}.")
        if ci.get("red_flag"):
            reasons = ci.get("red_flag_reasons") or []
            if reasons:
                parts.append(f"Red flags: {', '.join(reasons)}.")
            else:
                parts.append("Red flag present.")

    # Original text
    orig = record.get("original_text", "")
    if orig:
        parts.append(f"Original query: {orig}")

    return " ".join(parts)


async def load_queries(
    db: Database,
    source_id: int,
    jsonl_path: Path | str | None = None,
) -> int:
    """Load structured queries from JSONL into the queries table. Returns count loaded.

    Raises
    ------
    FileNotFoundError
        If the JSONL file does not exist.
    ValueError
        If the file exists but yields zero valid queries.
    """
    path = Path(jsonl_path) if jsonl_path else JSONL_INPUT_PATH
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    logger.info("Loading queries from %s", path)

    loaded = 0
    skipped = 0
    label_counts: Counter = Counter()

    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipping invalid JSON at line %d: %s", line_num, e)
                continue

            original_text = record.get("original_text", "")
            if not original_text:
                logger.debug("Skipping line %d: no original_text", line_num)
                continue

            label = (record.get("label") or "").lower()
            representation = build_query_representation(record)

            result = await db.insert_query(
                source_id=source_id,
                original_text=original_text,
                label=label,
                category=record.get("category"),
                symptoms_json=json.dumps(record.get("symptoms")) if record.get("symptoms") else None,
                duration_json=json.dumps(record.get("duration")) if record.get("duration") else None,
                frequency=record.get("frequency"),
                triggers_json=json.dumps(record.get("triggers")) if record.get("triggers") else None,
                symptom_temporal_map_json=json.dumps(record.get("symptom_temporal_map")) if record.get("symptom_temporal_map") else None,
                patient_context_json=json.dumps(record.get("patient_context")) if record.get("patient_context") else None,
                clinical_interpretation_json=json.dumps(record.get("clinical_interpretation")) if record.get("clinical_interpretation") else None,
                representation_text=representation,
            )

            if result is not None:
                loaded += 1
                label_counts[label] += 1
            else:
                skipped += 1

    label_summary = ", ".join(f"{k}={v}" for k, v in sorted(label_counts.items()))
    logger.info(
        "Loaded %d queries (%d skipped). Labels: %s",
        loaded, skipped, label_summary or "none",
    )

    if loaded == 0:
        raise ValueError(
            f"Zero valid queries loaded from {path}. "
            f"File had {skipped} skipped entries. Pipeline cannot proceed without queries."
        )

    # Log a sample representation for verification
    cursor = await db.db.execute(
        "SELECT representation_text FROM queries WHERE source_id = ? LIMIT 1",
        (source_id,),
    )
    row = await cursor.fetchone()
    if row:
        logger.info("Sample representation: %s", row[0][:300])

    return loaded
