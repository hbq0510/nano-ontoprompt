from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class EntityCreate(BaseModel):
    name_cn: str
    name_en: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    properties: Dict[str, Any] = {}
    property_schema: Dict[str, Any] = {}
    confidence: Optional[float] = None

class EntityUpdate(BaseModel):
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    property_schema: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None

class EntityOut(BaseModel):
    id: str
    ontology_id: str
    name_cn: str
    name_en: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    properties: Dict[str, Any] = {}
    property_schema: Dict[str, Any] = {}
    confidence: float = 1.0
    version: str = "v0.1"
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
