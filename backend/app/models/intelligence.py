"""情报模型 — 推演中途插入的实时情报"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Intelligence(Base):
    __tablename__ = "sim_intelligence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("sim_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[str | None] = mapped_column(String, ForeignKey("sim_plans.id", ondelete="SET NULL"), nullable=True)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)

    # 自由文本情报
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM 解析后的结构化操作
    # [{"action":"create_link","link_type":"探测","source":"radar_id","target":"missile_id"},
    #  {"action":"update_instance","instance_id":"xxx","props":{"track_capacity":50}},
    #  {"action":"delete_link","link_id":"xxx"}]
    parsed: Mapped[list | None] = mapped_column(JSON, default=None)

    # 状态: pending → parsing → parsed → applied
    status: Mapped[str] = mapped_column(String(20), default="pending")

    source: Mapped[str | None] = mapped_column(String(50), default="manual")  # manual | auto | external

    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
