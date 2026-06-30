"""
军事情报动态分析演示 API

5 个端点：
  POST /init          — 创建演示会话 (Ontology)
  POST /{oid}/submit  — 提交情报 → 触发抽取
  GET  /{oid}/snapshots — 时间线
  GET  /{oid}/assess  — 完整评估 + 图数据
  GET  /{oid}/graph   — 图单独查
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.ontology import OntologyProject
from app.models.entity import Entity
from app.models.relation import Relation
from app.models.prompt import Prompt
from app.models.model_config import ModelConfig
from app.models.intel_snapshot import IntelSnapshot
from app.models.extraction_task import ExtractionTask
from app.models.file import UploadedFile
from app.schemas.intel import (
    IntelInitRequest,
    IntelInitResponse,
    IntelSubmitRequest,
    IntelSubmitResponse,
    IntelSnapshotOut,
    IntelAssessResponse,
    GraphData,
)
from app.services.intel_analyzer import calculate_danger, generate_recommendations
import uuid
import os
import tempfile
from datetime import datetime, timezone

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# POST /init
# ══════════════════════════════════════════════════════════════════════

@router.post("/init", status_code=201)
def init_session(
    body: IntelInitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建情报分析演示会话 — 新建一个 Ontology 项目。"""
    project = OntologyProject(
        id=str(uuid.uuid4()),
        name=body.name,
        domain="军事",
        description=body.description or "动态军事情报分析演示",
        build_mode="intel_demo",
        created_by=current_user.id,
        status="created",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"data": IntelInitResponse(ontology_id=project.id, name=project.name)}


# ══════════════════════════════════════════════════════════════════════
# POST /{ontology_id}/submit
# ══════════════════════════════════════════════════════════════════════

@router.post("/{ontology_id}/submit", status_code=201)
def submit_intel(
    ontology_id: str,
    body: IntelSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交情报文本 → 创建快照 → 调用 LLM 抽取 → 返回 task_id，前端轮询评估结果。"""
    import re as _re

    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    text = body.intel_text.strip()

    # 自动生成 label
    if body.label:
        label = body.label
    else:
        count = (
            db.query(func.count(IntelSnapshot.id))
            .filter(IntelSnapshot.ontology_id == ontology_id)
            .scalar()
            or 0
        )
        label = f"T{count + 1}"

    # 写入临时文件（供抽取任务读取）
    tmp_path = os.path.join(tempfile.gettempdir(), f"intel_{uuid.uuid4().hex}.txt")
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)

    # 创建 UploadedFile（converted_md 预填文本）
    uf = UploadedFile(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        filename=f"intel_{label}.txt",
        file_path=tmp_path,
        file_size=len(text.encode("utf-8")),
        mime_type="text/plain",
        converted_md=text,
    )
    db.add(uf)

    # 创建快照
    snapshot = IntelSnapshot(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        label=label,
        intel_text=text,
        status="extracting",
    )
    db.add(snapshot)
    db.flush()

    # 查找可用的 prompt 和 model
    prompt = db.query(Prompt).order_by(Prompt.created_at.asc()).first()
    model_cfg = db.query(ModelConfig).order_by(ModelConfig.created_at.asc()).first()

    # 创建 ExtractionTask
    task = ExtractionTask(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        prompt_id=prompt.id if prompt else None,
        model_id=model_cfg.id if model_cfg else None,
        status="queued",
        parameters={
            "file_ids": [uf.id],
            "intel_demo": True,
            "label": label,
        },
        progress={"stage": "queued", "pct": 0},
    )
    db.add(task)
    db.flush()
    snapshot.extraction_task_id = task.id
    project.status = "creating"
    db.commit()
    db.refresh(task)

    # 投递 Celery 抽取任务
    try:
        from app.tasks.extraction import run_extraction
        run_extraction.delay(task.id)
    except Exception:
        import threading
        def _run(): run_extraction(task.id)
        threading.Thread(target=_run, daemon=True).start()

    return {
        "data": IntelSubmitResponse(
            snapshot_id=snapshot.id,
            task_id=task.id,
            status="extracting",
        )
    }


# ══════════════════════════════════════════════════════════════════════
# GET /{ontology_id}/snapshots
# ══════════════════════════════════════════════════════════════════════

@router.get("/{ontology_id}/snapshots")
def list_snapshots(
    ontology_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """获取所有情报快照（按时间排序）。"""
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    snapshots = (
        db.query(IntelSnapshot)
        .filter(IntelSnapshot.ontology_id == ontology_id)
        .order_by(IntelSnapshot.created_at.asc())
        .all()
    )
    return {"data": [IntelSnapshotOut.model_validate(s).model_dump() for s in snapshots]}


# ══════════════════════════════════════════════════════════════════════
# GET /{ontology_id}/assess
# ══════════════════════════════════════════════════════════════════════

@router.get("/{ontology_id}/assess")
def assess(
    ontology_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """完整评估：危险等级 + 建议 + 时间线 + 图数据。"""
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    # 收集实体和关系
    entities = db.query(Entity).filter(Entity.ontology_id == ontology_id).all()
    relations = db.query(Relation).filter(Relation.ontology_id == ontology_id).all()

    entity_list = [
        {
            "name_cn": e.name_cn or "",
            "type": e.type or "",
            "confidence": e.confidence or 1.0,
        }
        for e in entities
    ]
    relation_list = [
        {
            "source": r.source_entity or "",
            "target": r.target_entity or "",
            "type": r.type or "关联",
            "confidence": r.confidence or 1.0,
        }
        for r in relations
    ]

    # 计算危险等级
    score, level = calculate_danger(entity_list, relation_list)
    recs = generate_recommendations(level, entity_list, relation_list)

    # 更新最新快照
    latest = (
        db.query(IntelSnapshot)
        .filter(IntelSnapshot.ontology_id == ontology_id)
        .order_by(IntelSnapshot.created_at.desc())
        .first()
    )
    if latest and latest.status == "extracting":
        # 检查关联的 extraction_task 是否完成
        if latest.extraction_task_id:
            task = db.query(ExtractionTask).filter(ExtractionTask.id == latest.extraction_task_id).first()
            if task and task.status in ("completed", "failed"):
                latest.status = "completed" if task.status == "completed" else "failed"
        else:
            latest.status = "completed"

    if latest:
        latest.danger_score = score
        latest.danger_level = level
        latest.recommendations = recs
        latest.entity_count = len(entities)
        latest.relation_count = len(relations)
        db.commit()

    # 时间线
    snapshots = (
        db.query(IntelSnapshot)
        .filter(IntelSnapshot.ontology_id == ontology_id)
        .order_by(IntelSnapshot.created_at.asc())
        .all()
    )

    # 图数据
    graph = _build_graph(ontology_id, db)

    return {
        "data": IntelAssessResponse(
            ontology_id=project.id,
            ontology_name=project.name,
            danger_level=level,
            danger_score=score,
            recommendations=recs,
            entity_count=len(entities),
            relation_count=len(relations),
            snapshots=[IntelSnapshotOut.model_validate(s).model_dump() for s in snapshots],
            graph=graph,
        )
    }


# ══════════════════════════════════════════════════════════════════════
# GET /{ontology_id}/graph
# ══════════════════════════════════════════════════════════════════════

@router.get("/{ontology_id}/graph")
def get_graph(
    ontology_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """单独查询图数据。"""
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")
    return {"data": _build_graph(ontology_id, db)}


# ══════════════════════════════════════════════════════════════════════
# Helper: build graph data
# ══════════════════════════════════════════════════════════════════════

def _build_graph(ontology_id: str, db: Session) -> GraphData:
    """从 Neo4j 或 PostgreSQL 构建图数据。"""
    # 先尝试 Neo4j
    try:
        from app.services.v2.graph.neo4j_service import Neo4jService

        neo = Neo4jService()
        if neo.available:
            data = neo.get_graph_data(ontology_id, limit=300)
            neo.close()
            if data.get("nodes"):
                # Convert Neo4j-specific types to JSON-safe types
                return GraphData(
                    nodes=_to_json_safe(data["nodes"]),
                    edges=_to_json_safe(data.get("edges", data.get("relations", []))),
                    neo4j_available=True,
                )
    except Exception:
        pass

    # PostgreSQL 回退
    entities = db.query(Entity).filter(Entity.ontology_id == ontology_id).all()
    relations = db.query(Relation).filter(Relation.ontology_id == ontology_id).all()

    nodes: list[dict] = []
    for e in entities:
        nodes.append(
            {
                "id": e.id,
                "labels": [e.type or "Entity"],
                "properties": {
                    "name_cn": e.name_cn or "",
                    "name_en": e.name_en or "",
                    "type": e.type or "",
                    "description": (e.description or "")[:100],
                    "confidence": e.confidence or 1.0,
                },
            }
        )

    edges: list[dict] = []
    for r in relations:
        edges.append(
            {
                "id": r.id,
                "source": r.source_entity or "",
                "target": r.target_entity or "",
                "type": r.type or "关联",
            }
        )

    return GraphData(nodes=nodes, edges=edges, neo4j_available=False, fallback="postgresql")


import datetime as _dt

def _to_json_safe(obj):
    """递归转换对象中的 Neo4j datetime 等类型为 JSON-safe 值。"""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
