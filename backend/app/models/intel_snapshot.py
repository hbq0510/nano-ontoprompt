import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class IntelSnapshot(Base):
    """情报快照 — 记录每个时间点的情报输入和评估结果"""

    __tablename__ = "intel_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )

    # 时间点标签 T1 / T2 / T3
    label: Mapped[str] = mapped_column(String(50), nullable=False)

    # 原始情报文本
    intel_text: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联的抽取任务
    extraction_task_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("extraction_tasks.id", ondelete="SET NULL"), nullable=True
    )

    # 评估结果（由危险评估引擎计算）
    danger_score: Mapped[float] = mapped_column(Float, default=0.0)
    danger_level: Mapped[str] = mapped_column(String(20), default="low")  # low/medium/high/critical
    recommendations: Mapped[list] = mapped_column(JSON, default=list)

    # 当前快照时的统计
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, default=0)

    # 本次抽取创建的实体/关系 ID（用于撤回）
    created_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_relation_ids: Mapped[list] = mapped_column(JSON, default=list)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="extracting")  # extracting/completed/failed/reverted

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
