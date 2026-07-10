import uuid, json
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import event
from app.database import Base

class LogicRule(Base):
    __tablename__ = "logic_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    formula: Mapped[str] = mapped_column(Text, nullable=True)
    # conditions: 结构化条件数组，程序可机械校验
    # 格式: [{"field": "损毁比例", "op": ">", "value": 0.3}]
    # op 取值: >, <, >=, <=, ==, !=, in
    # field 只能引用对应 target_entity_type 的 property_schema 中已定义的字段
    conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    # needs_review: 当条件字段校验不通过时标记为 true
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # linked_object_type_ids: Phase 2 精确关联到 object_types 表（替代 linked_entities 的字符串匹配）
    linked_object_type_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[str] = mapped_column(String(20), default="v0.1")
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    _linked_entities: Mapped[str] = mapped_column("linked_entities", Text, default="[]")

    @property
    def linked_entities(self) -> list:
        try:
            return json.loads(self._linked_entities or "[]")
        except Exception:
            return []

    @linked_entities.setter
    def linked_entities(self, value: list):
        self._linked_entities = json.dumps(value or [], ensure_ascii=False)
