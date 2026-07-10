import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    execution_rule: Mapped[str] = mapped_column(Text, nullable=True)
    function_code: Mapped[str] = mapped_column(Text, nullable=True)
    linked_entities: Mapped[list] = mapped_column(JSON, default=list)
    linked_logic_ids: Mapped[list] = mapped_column(JSON, default=list)
    # submission_criteria: 结构化提交条件，程序可机械校验
    # 格式: [{"field": "损毁比例", "op": ">", "value": 0.3}]
    # op 取值: >, <, >=, <=, ==, !=, in
    # field 只能引用对应 target_entity_type 的 property_schema 中已定义的字段
    submission_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    # target_entity_type: 该动作作用于哪种实体类型，引用 entities.name_en（遗留，新代码用 target_object_type_id）
    target_entity_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # target_object_type_id: Phase 2 关联到 object_types 表（软引用，不设 FK 约束以兼容 ALTER TABLE）
    target_object_type_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # needs_review: 当条件字段校验不通过时标记为 true，不阻断入库但需人工审核
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[str] = mapped_column(String(20), default="v0.1")
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
