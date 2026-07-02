"""
实体类型模板 — 定义每种实体类型（导弹、坦克、雷达站等）的字段结构。

一个 Ontology 下可以有多个模板，每个模板对应一个实体 type。
创建实体时，系统根据 type 匹配模板，按模板定义的字段结构校验和填充 properties。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class EntityTemplate(Base):
    __tablename__ = "entity_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="实体类型名称，如 导弹、坦克、雷达站")  # noqa: E501
    type_name_en: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="英文类型名")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="类型描述")
    fields: Mapped[dict] = mapped_column(JSON, default=list, comment="字段定义列表 [{name, type, required, options, unit}]")  # noqa: E501
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))  # noqa: E501
