from pydantic import BaseModel, Field
from typing import List, Optional


class Symptom(BaseModel):
    name: str
    normalized_name: Optional[str] = None
    anatomical_location: Optional[str] = None
    severity: Optional[str] = None


class Demographics(BaseModel):
    age: Optional[int] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    pregnancy_status: Optional[str] = None


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
    severity_overall: Optional[str] = None

    anatomical_locations: List[str] = Field(default_factory=list)

    demographics: Optional[Demographics] = None

    intent: Optional[str] = None  # diagnosis | treatment | reassurance | emergency | prognosis

    red_flag: bool = False

    comorbidities: List[str] = Field(default_factory=list)

    triggers: List[str] = Field(default_factory=list)
    
    frequency: Optional[str] = None 

    query_complexity_score: int
    

