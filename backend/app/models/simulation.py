"""推演系统模型 — Scenario / ScenarioTick / ScenarioEvent"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Scenario(Base):
    """想定场景 — 一次推演的定义"""
    __tablename__ = "sim_scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 参与推演的实例 ID 列表 (ObjectInstance id)
    participant_instance_ids: Mapped[list] = mapped_column(JSON, default=list)

    # 初始态势 — 每个参与实例的初始属性值（位置等信息，每次推演从此重置）
    # {"instance_id": "xxx", "initial_properties": {"latitude": 30.5, "longitude": 120.2, ...}}
    initial_state: Mapped[list] = mapped_column(JSON, default=list)

    # 每实例的固定设计参数（不随 tick 变化，不在此表中的视为纯位置数据）
    # {"instance_id": "xxx", "design_params": {"speed_mach": 8, "range_km": 400, ...}}
    design_params_map: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    # 推演参数
    tick_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)  # 每 tick 间隔（模拟用）
    max_ticks: Mapped[int] = mapped_column(Integer, default=100)
    current_tick: Mapped[int] = mapped_column(Integer, default=0)

    # 状态：draft | running | paused | finished
    status: Mapped[str] = mapped_column(String(20), default="draft")

    # 停止条件: max_ticks | intercept_success | intercept_fail | target_lost
    stop_condition: Mapped[str | None] = mapped_column(String(50), default="max_ticks", nullable=True)

    # 是否循环推演（结束后回到初始状态）
    loop: Mapped[bool] = mapped_column(Boolean, default=False)

    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ScenarioTick(Base):
    """推演 Tick 状态快照 — 每个时间步的完整态势"""
    __tablename__ = "sim_ticks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    tick: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # 当前 tick 所有实例的属性快照
    # {"instance_id": "xxx", "properties": {"latitude": 31.0, "speed": 5.0, ...}, "links": [...]}
    instance_states: Mapped[list] = mapped_column(JSON, default=list)

    # 当前 tick 所有活跃的 Link
    # [{"link_id": "xxx", "link_type": "探测", "source": "雷达B", "target": "导弹A", "properties": {...}}]
    active_links: Mapped[list] = mapped_column(JSON, default=list)

    # 当前 tick 触发的事件列表
    events: Mapped[list | None] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ScenarioEvent(Base):
    """推演事件 — 记录每次规则命中、动作执行、状态变化"""
    __tablename__ = "sim_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    tick: Mapped[int] = mapped_column(Integer, nullable=False)

    # event_type: rule_check (规则检查), action_exec (动作执行), state_change (状态变化), link_created (关系建立)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # source/target 实例描述
    source_instance_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_instance_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 人类可读的描述
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 额外数据
    extra: Mapped[dict | None] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
