"""实体类型模板 Pydantic Schema"""
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class FieldDef(BaseModel):
    """单个字段定义"""
    name: str                    # 字段名，如 射程
    type: str = "string"         # string / number / select / boolean / text
    required: bool = False
    options: list[str] = []      # type=select 时的可选值
    unit: str = ""               # 单位，如 km


class EntityTemplateCreate(BaseModel):
    """创建模板"""
    type_name: str                                    # 实体类型名称，如 导弹
    type_name_en: Optional[str] = None
    description: Optional[str] = None
    fields: list[FieldDef] = []                       # 字段定义列表


class EntityTemplateUpdate(BaseModel):
    """更新模板"""
    type_name: Optional[str] = None
    type_name_en: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[list[FieldDef]] = None


class EntityTemplateOut(BaseModel):
    """模板响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    ontology_id: str
    type_name: str
    type_name_en: Optional[str] = None
    description: Optional[str] = None
    fields: list[dict] = []
    created_at: datetime
    updated_at: datetime
