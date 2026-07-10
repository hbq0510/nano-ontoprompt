"""Phase 2 重构 — ObjectType/ObjectInstance/Interface/LinkType/Link 的 Pydantic schemas"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, List, Any


# ── ObjectType ──
class ObjectTypeCreate(BaseModel):
    name_cn: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    property_schema: Dict[str, Any] = {}
    interface_ids: List[str] = []
    confidence: Optional[float] = None

class ObjectTypeUpdate(BaseModel):
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    property_schema: Optional[Dict[str, Any]] = None
    interface_ids: Optional[List[str]] = None
    confidence: Optional[float] = None

class ObjectTypeOut(BaseModel):
    id: str
    ontology_id: str
    name_cn: str
    name_en: Optional[str]
    description: Optional[str]
    property_schema: Dict[str, Any] = {}
    interface_ids: List[str] = []
    confidence: float
    version: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── ObjectInstance ──
class ObjectInstanceCreate(BaseModel):
    object_type_id: str
    name_cn: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    properties: Dict[str, Any] = {}
    confidence: Optional[float] = None

class ObjectInstanceUpdate(BaseModel):
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None

class ObjectInstanceOut(BaseModel):
    id: str
    ontology_id: str
    object_type_id: str
    name_cn: str
    name_en: Optional[str]
    description: Optional[str]
    properties: Dict[str, Any] = {}
    confidence: float
    version: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Interface ──
class InterfaceCreate(BaseModel):
    name_cn: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    shared_properties: List[dict] = []

class InterfaceUpdate(BaseModel):
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    shared_properties: Optional[List[dict]] = None

class InterfaceOut(BaseModel):
    id: str
    ontology_id: str
    name_cn: str
    name_en: Optional[str]
    description: Optional[str]
    shared_properties: List[dict] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── LinkType ──
class LinkTypeCreate(BaseModel):
    name_cn: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    source_object_type_id: Optional[str] = None
    target_object_type_id: Optional[str] = None

class LinkTypeUpdate(BaseModel):
    name_cn: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    source_object_type_id: Optional[str] = None
    target_object_type_id: Optional[str] = None

class LinkTypeOut(BaseModel):
    id: str
    ontology_id: str
    name_cn: str
    name_en: Optional[str]
    description: Optional[str]
    source_object_type_id: Optional[str]
    target_object_type_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Link ──
class LinkCreate(BaseModel):
    link_type_id: str
    source_instance_id: str
    target_instance_id: str
    confidence: Optional[float] = None

class LinkOut(BaseModel):
    id: str
    ontology_id: str
    link_type_id: str
    source_instance_id: str
    target_instance_id: str
    confidence: float
    created_at: datetime
    model_config = {"from_attributes": True}
