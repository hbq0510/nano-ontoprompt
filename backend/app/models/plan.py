"""方案系统模型 — Plan (决策链) / PlanRun (方案执行记录)"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Plan(Base):
    """方案 — 一条决策链"""
    __tablename__ = "sim_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 决策链: [{"trigger": "distance<400", "target": "interceptor", "action": "launch", "params": {...}}, ...]
    decisions: Mapped[list] = mapped_column(JSON, default=list)

    # 状态: proposed | running | evaluated
    status: Mapped[str] = mapped_column(String(20), default="proposed")

    # 评估指标: {"kill_probability": 0.92, "ammo_used": 2, "time_ticks": 18, ...}
    score: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    # 方案来源: llm | manual | template
    source: Mapped[str | None] = mapped_column(String(20), default="manual")

    # 模板: 如果来源是 template，记录模板ID
    template_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PlanRun(Base):
    """方案执行记录"""
    __tablename__ = "sim_plan_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_plans.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_scenarios.id", ondelete="CASCADE"), nullable=False
    )

    # 状态: pending | running | success | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # 执行了多少 tick
    tick_count: Mapped[int] = mapped_column(Integer, default=0)

    # 最终评估指标
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    # 执行的决策日志
    decision_log: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # 事件快照（关键事件列表）
    events: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
