from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional


class SkillCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str
    description: Optional[str] = ""
    domain: Optional[str] = "军事"
    accepted_input_types: Optional[list[str]] = ["text/plain"]
    prompt_id: Optional[str] = None
    model_id: Optional[str] = None
    ontology_name_pattern: Optional[str] = "{skill_name}-{timestamp}"
    prebuilt_entities: Optional[list[str]] = []


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    accepted_input_types: Optional[list[str]] = None
    prompt_id: Optional[str] = None
    model_id: Optional[str] = None
    ontology_name_pattern: Optional[str] = None
    prebuilt_entities: Optional[list[str]] = None
    enabled: Optional[bool] = None


class SkillOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    domain: str
    accepted_input_types: list
    prompt_id: Optional[str]
    model_id: Optional[str]
    ontology_name_pattern: str
    prebuilt_entities: list
    enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class SkillListItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    domain: str
    enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── SkillTrigger schemas ──────────────────────────────────────────


class SkillTriggerOut(BaseModel):
    id: str
    skill_id: str
    skill_name: Optional[str] = None
    status: str
    input_file_name: str
    input_metadata: dict
    ontology_id: Optional[str] = None
    extraction_task_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
