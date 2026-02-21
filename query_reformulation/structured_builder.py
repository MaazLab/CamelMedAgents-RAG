from query_reformulation.schemas import (
    StructuredRepresentation,
    ClinicalPresentation,
    ClinicalModifiers,
    MetaInformation,
    SymptomAttributeOutput,
    IntentSeparationOutput
)


class StructuredRepresentationBuilder:

    def build(
        self,
        intent_output: IntentSeparationOutput,
        extraction_output: SymptomAttributeOutput
    ) -> StructuredRepresentation:

        modifiers = ClinicalModifiers(
            duration=extraction_output.duration,
            severity=extraction_output.severity,
            frequency=extraction_output.frequency,
            trigger=extraction_output.trigger
        )

        clinical_presentation = ClinicalPresentation(
            symptoms=extraction_output.symptoms,
            modifiers=modifiers
        )

        meta = MetaInformation(
            uncertainty_flag=intent_output.uncertainty,
            emotional_context=intent_output.emotional_context
        )

        return StructuredRepresentation(
            clinical_presentation=clinical_presentation,
            meta=meta
        )