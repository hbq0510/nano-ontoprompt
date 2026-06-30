import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Skill(Base):
    """可复用的技能模板 — 绑定 prompt + model + 输入类型 + 输出模板"""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(100), default="军事")

    # 接受的输入类型，如 ["image/*", "text/plain", "application/pdf"]
    accepted_input_types: Mapped[list] = mapped_column(JSON, default=list)

    # 绑定的提示词 & 模型
    prompt_id: Mapped[str | None] = mapped_column(String, ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String, ForeignKey("model_configs.id", ondelete="SET NULL"), nullable=True)

    # 产出的 Ontology 命名模板，如 "军情分析-{timestamp}"
    ontology_name_pattern: Mapped[str] = mapped_column(String(300), default="{skill_name}-{timestamp}")

    # 预定义的实体类型（帮助 LLM 聚焦）
    prebuilt_entities: Mapped[list] = mapped_column(JSON, default=list)

    # 状态
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SkillTrigger(Base):
    """Skill 触发记录 — 外部系统推数据过来后创建"""

    __tablename__ = "skill_triggers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id: Mapped[str] = mapped_column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending / confirmed / rejected / executing / completed / failed

    # 输入文件信息
    input_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    input_file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    input_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    # 确认后关联
    ontology_id: Mapped[str | None] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="SET NULL"), nullable=True)
    extraction_task_id: Mapped[str | None] = mapped_column(String, ForeignKey("extraction_tasks.id", ondelete="SET NULL"), nullable=True)

    # 执行结果
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
