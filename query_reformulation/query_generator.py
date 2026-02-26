from typing import Dict
from query_reformulation.schemas import StructuredRepresentation


class QueryGenerator:

    def __init__(self):
        pass

    def _generate_dense_query(self, structured: StructuredRepresentation) -> str:
        symptoms = [
            symptom.normalized
            for symptom in structured.clinical_presentation.symptoms
        ]

        modifiers = structured.clinical_presentation.modifiers

        components = []

        if symptoms:
            components.append(" and ".join(symptoms))

        if modifiers.trigger:
            components.append(f"triggered by {modifiers.trigger}")

        if modifiers.duration:
            components.append(f"for {modifiers.duration}")

        dense_query = " ".join(components).strip()

        if dense_query:
            dense_query = dense_query[0].upper() + dense_query[1:] + "."

        return dense_query

    def _generate_keyword_query(self, structured: StructuredRepresentation) -> str:
        symptoms = [
            symptom.normalized
            for symptom in structured.clinical_presentation.symptoms
        ]

        modifiers = structured.clinical_presentation.modifiers

        parts = symptoms.copy()

        if modifiers.trigger:
            parts.append(modifiers.trigger)

        if modifiers.duration:
            parts.append(modifiers.duration)

        return " AND ".join(parts)

    def generate(self, structured: StructuredRepresentation) -> Dict[str, str]:

        return {
            "dense_query": self._generate_dense_query(structured),
            "keyword_query": self._generate_keyword_query(structured)
        }