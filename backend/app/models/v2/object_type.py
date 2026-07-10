"""Phase 2 重构 — ObjectType / ObjectInstance / Interface / LinkType / Link

Palantir 风格两层拆分：
- ObjectType: 语义层——定义"这个类型有哪些字段"（schema）
- ObjectInstance: 实例层——具体的一行数据，属性值是填好的
- Interface: 共享属性横向打通
- LinkType: 定义两个类型之间允许的关系
- Link: 两个实例之间的具体连线

注意：跨表引用使用软 ID（普通 String），不设 FK 约束。
原因：LLM 提取时无法预知数据库 UUID，需要通过名称映射解析引用。
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ObjectType(Base):
    """对象类型——定义一类实体的 schema（属性定义、接口实现）"""
    __tablename__ = "object_types"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    interface_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[str] = mapped_column(String(20), default="v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ObjectInstance(Base):
    """对象实例——具体的一条数据，属性值是实际填好的"""
    __tablename__ = "object_instances"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    # 软引用 object_types.id，不设 FK（LLM 提取时 ID 动态生成）
    object_type_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[str] = mapped_column(String(20), default="v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Interface(Base):
    """接口——多个对象类型的共享属性定义，横向打通"""
    __tablename__ = "interfaces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_properties: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class LinkType(Base):
    """关系类型——定义两个 ObjectType 之间允许的关系"""
    __tablename__ = "link_types"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 软引用 object_types.id，不设 FK
    source_object_type_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_object_type_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Link(Base):
    """关系实例——两个具体的 ObjectInstance 之间的连线"""
    __tablename__ = "links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(
        String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False
    )
    # 软引用，不设 FK（LLM 提取时动态解析）
    link_type_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_instance_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_instance_id: Mapped[str] = mapped_column(String(200), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
