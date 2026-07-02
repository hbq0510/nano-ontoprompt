from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class IntelInitRequest(BaseModel):
    name: str = "军事情报分析演示"
    description: Optional[str] = None


class IntelInitResponse(BaseModel):
    ontology_id: str
    name: str


class IntelSubmitRequest(BaseModel):
    intel_text: str
    label: Optional[str] = None  # 不填则自动 T1/T2/T3


class IntelSubmitResponse(BaseModel):
    snapshot_id: str
    task_id: str
    status: str  # "extracting"


class IntelSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    intel_text: str
    entity_count: int
    relation_count: int
    danger_score: float
    danger_level: str
    recommendations: list[str]
    status: str
    created_at: datetime


class GraphData(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    neo4j_available: bool = False
    fallback: Optional[str] = None


class IntelAssessResponse(BaseModel):
    ontology_id: str
    ontology_name: str
    danger_level: str
    danger_score: float
    recommendations: list[str]
    entity_count: int
    relation_count: int
    snapshots: list[IntelSnapshotOut]
    graph: GraphData


class IntelForwardRequest(BaseModel):
    """手动转发请求 — 传入情报文本，分析后推送到外部 agent"""
    intel_text: str


class IntelForwardResponse(BaseModel):
    success: bool
    message: str
    webhook_url: str
    webhook_task_id: str | None = None  # Celery 异步任务 ID，用于追踪推送状态
    payload: dict  # 实际发送给外部 agent 的内容
