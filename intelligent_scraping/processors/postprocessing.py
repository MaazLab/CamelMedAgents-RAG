RED_FLAG_TERMS = [
    "chest pain",
    "shortness of breath",
    "unconscious",
    "severe bleeding",
    "sudden weakness",
    "vision loss"
]


def apply_red_flag_guard(structured):
    text = structured.get("original_text", "").lower()

    for term in RED_FLAG_TERMS:
        if term in text:
            structured["red_flag"] = True
            break

    return structured