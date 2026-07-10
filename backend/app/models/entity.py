import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # properties: 仅供展示的百科式参考信息，不保证结构化。
    # 不允许被 conditions/submission_criteria 的 field 引用。
    # 条件判断应使用 property_schema 中已定义的字段。
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    # property_schema: 该实体类型允许的可量化属性定义（schema，不是具体值）
    # 格式: {"字段名": {"type": "number|string|boolean", "unit": "可选"}}
    # conditions/submission_criteria 的 field 只能引用此字段中已定义的键。
    property_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[str] = mapped_column(String(20), default="v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
