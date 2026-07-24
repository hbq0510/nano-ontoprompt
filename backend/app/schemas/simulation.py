"""推演系统 Schema"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ── Scenario ──────────────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    participant_instance_ids: list[str] = []
    initial_state: list[dict] = []
    design_params_map: dict = {}
    tick_interval_ms: int = 1000
    max_ticks: int = 100
    stop_condition: Optional[str] = "max_ticks"  # max_ticks | intercept_success | intercept_fail | target_lost
    loop: bool = False


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    participant_instance_ids: Optional[list[str]] = None
    initial_state: Optional[list[dict]] = None
    design_params_map: Optional[dict] = None
    tick_interval_ms: Optional[int] = None
    max_ticks: Optional[int] = None
    stop_condition: Optional[str] = None
    loop: Optional[bool] = None
    status: Optional[str] = None


class ScenarioOut(BaseModel):
    id: str
    ontology_id: str
    name: str
    description: Optional[str] = None
    participant_instance_ids: list = []
    initial_state: list = []
    design_params_map: dict = {}
    tick_interval_ms: int = 1000
    max_ticks: int = 100
    current_tick: int = 0
    status: str = "draft"
    stop_condition: Optional[str] = "max_ticks"
    loop: bool = False
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScenarioListItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str
    current_tick: int
    max_ticks: int
    participant_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Tick ──────────────────────────────────────────────────────────

class TickOut(BaseModel):
    id: str
    scenario_id: str
    tick: int
    instance_states: list = []
    active_links: list = []
    events: Optional[list] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Event ─────────────────────────────────────────────────────────

class EventOut(BaseModel):
    id: str
    scenario_id: str
    tick: int
    event_type: str
    source_instance_id: Optional[str] = None
    target_instance_id: Optional[str] = None
    description: Optional[str] = None
    extra: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Simulation Control ────────────────────────────────────────────

class SimulationStepResult(BaseModel):
    tick: int
    events: list[dict] = []
    instance_states: list[dict] = []
    active_links: list[dict] = []
    finished: bool = False
