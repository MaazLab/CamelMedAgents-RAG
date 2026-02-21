# pipeline.py

from query_reformulation.intent_separator import IntentSeparator
from query_reformulation.symptom_extractor import SymptomAttributeExtractor
from query_reformulation.structured_builder import StructuredRepresentationBuilder


class LLMQueryProcessingPipeline:

    def __init__(self):
        self.intent_separator = IntentSeparator()
        self.extractor = SymptomAttributeExtractor()
        self.builder = StructuredRepresentationBuilder()

    def run(self, raw_query: str):

        intent_output = self.intent_separator.process(raw_query)

        extraction_output = self.extractor.process(
            intent_output.cleaned_text
        )

        structured_output = self.builder.build(
            intent_output=intent_output,
            extraction_output=extraction_output
        )

        return {
            "intent_separation": intent_output.model_dump(),
            "symptom_extraction": extraction_output.model_dump(),
            "structured_representation": structured_output.model_dump()
        }