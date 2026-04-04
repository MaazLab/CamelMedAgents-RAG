from pydantic import BaseModel, Field
from typing import List, Optional


class Symptom(BaseModel):
    name: str
    normalized_name: Optional[str] = None
    anatomical_location: Optional[str] = None
    severity: Optional[str] = None
    
class TemporalSymptom(BaseModel):
    symptom: str
    duration_days: Optional[int] = None
    onset_type: Optional[str] = None


class PatientContext(BaseModel):
    age: Optional[int] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    pregnancy_status: Optional[str] = None
    comorbidities: List[str] = Field(default_factory=list)


class ClinicalInterpretation(BaseModel):
    intent: Optional[str] = None
    red_flag: bool = False
    red_flag_reasons: List[str] = Field(default_factory=list)


class Duration(BaseModel):
    value: Optional[str] = None
    normalized_days: Optional[int] = None
    onset_type: Optional[str] = None  # acute | chronic | sudden | gradual


class StructuredQuery(BaseModel):
    original_text: str
    label: str
    category: str

    symptoms: List[Symptom] = Field(..., min_items=1)

    duration: Optional[Duration] = None
    frequency: Optional[str] = None 
    triggers: List[str] = Field(default_factory=list)
    symptom_temporal_map: List[TemporalSymptom] = Field(default_factory=list)

    patient_context: Optional[PatientContext] = None
    clinical_interpretation: Optional[ClinicalInterpretation] = None

    # severity_overall: Optional[str] = None

    # anatomical_locations: List[str] = Field(default_factory=list)

    # query_complexity_score: int
    

