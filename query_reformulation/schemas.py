from pydantic import BaseModel, Field
from typing import List, Optional


class IntentSeparationOutput(BaseModel):
    cleaned_text: str = Field(description="Noise-removed clinical content")
    uncertainty: bool = Field(description="True if user expresses uncertainty or concern")
    emotional_context: Optional[str] = Field(description="Detected emotional tone")


class SymptomItem(BaseModel):
    original: str = Field(description="Original symptom phrase from user text")
    normalized: str = Field(description="Normalized clinical term")


class SymptomAttributeOutput(BaseModel):
    symptoms: List[SymptomItem] = Field(
        description="List of extracted symptoms with original and normalized forms"
    )
    duration: Optional[str] = Field(description="Extracted duration if mentioned")
    severity: Optional[str] = Field(description="Extracted severity if mentioned")
    frequency: Optional[str] = Field(description="Extracted frequency if mentioned")
    trigger: Optional[str] = Field(description="Extracted trigger if mentioned")


class ClinicalModifiers(BaseModel):
    duration: Optional[str]
    severity: Optional[str]
    frequency: Optional[str]
    trigger: Optional[str]


class ClinicalPresentation(BaseModel):
    symptoms: List[SymptomItem]
    modifiers: ClinicalModifiers


class MetaInformation(BaseModel):
    uncertainty_flag: bool
    emotional_context: Optional[str]


class StructuredRepresentation(BaseModel):
    clinical_presentation: ClinicalPresentation
    meta: MetaInformation