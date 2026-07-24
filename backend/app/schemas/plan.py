"""方案系统 Schema"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── Plan ────────────────────────────────────────────────────────

class DecisionStep(BaseModel):
    trigger: str            # 触发条件: "distance<400" | "intercept_success" | "tick>=5"
    target: str = ""        # 执行对象类型: "interceptor" | "radar" | "missile"
    action: str             # 动作: "launch" | "jam" | "track" | "stop" | "wait"
    params: dict = {}       # 参数: {"count": 2, "mode": "salvo"}


class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    decisions: list[DecisionStep] = []
    source: Optional[str] = "manual"
    template_id: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    decisions: Optional[list[DecisionStep]] = None
    status: Optional[str] = None
    score: Optional[dict] = None


class PlanOut(BaseModel):
    id: str
    scenario_id: str
    name: str
    description: Optional[str] = None
    decisions: list = []
    status: str = "proposed"
    score: Optional[dict] = None
    source: Optional[str] = "manual"
    template_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class PlanListItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str
    score: Optional[dict] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── PlanRun ─────────────────────────────────────────────────────

class PlanRunOut(BaseModel):
    id: str
    plan_id: str
    scenario_id: str
    status: str
    tick_count: int = 0
    result: Optional[dict] = None
    decision_log: Optional[list] = None
    events: Optional[list] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── LLM Generate ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    count: int = 3         # 生成几个方案
    strategy: str = "diverse"  # diverse | aggressive | conservative


# ── Compare ─────────────────────────────────────────────────────

class CompareItem(BaseModel):
    plan_id: str
    plan_name: str
    score: dict = {}
    status: str
