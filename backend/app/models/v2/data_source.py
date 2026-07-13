"""数据源 — 注册远程数据库表，供属性值绑定"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ontology_id: Mapped[str] = mapped_column(String, ForeignKey("ontology_projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    db_config: Mapped[dict] = mapped_column(JSON, default=dict)  # {db_type, host, port, user, password, database}
    registered_table: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
