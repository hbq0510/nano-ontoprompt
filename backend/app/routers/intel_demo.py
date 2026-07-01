"""
军事情报动态分析演示 API — 分层混合方案

Layer 1 (同步, <1s): 情报关键词匹配已有本体 → 即时威胁评估
Layer 2 (异步, 后台): LLM 深度抽取 → 增量更新本体

端点：
  POST /init
  POST /{oid}/assess-quick  — Layer 1: 快速威胁评估
  POST /{oid}/submit        — Layer 2: 异步 LLM 抽取（后台更新本体）
  GET  /{oid}/snapshots
  GET  /{oid}/assess
  GET  /{oid}/graph
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
from app.models.logic import LogicRule
from app.models.action import Action
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
# POST /{ontology_id}/assess-quick  — Layer 1 快速威胁评估
# ══════════════════════════════════════════════════════════════════════

@router.post("/{ontology_id}/assess-quick")
def assess_quick(
    ontology_id: str,
    body: IntelSubmitRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Layer 1 — 同步快速评估（不调 LLM）。

    1. 情报文本关键词匹配知识本体中已有实体
    2. 找到被触发的逻辑规则（linked_entities 命中）
    3. 找到被触发的动作（linked_entities 或 linked_logic_ids 命中）
    4. 计算危险等级
    5. 立即返回（不创建快照，不写入数据库）
    """
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    text = body.intel_text.strip()
    if not text:
        raise HTTPException(400, "intel_text is required")

    # 1. 获取知识本体中所有实体
    all_entities = db.query(Entity).filter(Entity.ontology_id == ontology_id).all()
    if not all_entities:
        # 本体为空，直接返回基础评估
        return {"data": {
            "ontology_id": ontology_id,
            "ontology_name": project.name,
            "matched_entities": [],
            "triggered_rules": [],
            "triggered_actions": [],
            "danger_level": "low",
            "danger_score": 0.0,
            "recommendations": ["保持监视", "常规巡逻"],
            "mode": "baseline",
        }}

    # 2. 关键词匹配：2-gram + 精确包含，不再用单字重叠和泛化类型匹配
    matched: list[dict] = []
    for e in all_entities:
        name = e.name_cn or ""
        if len(name) < 2:
            continue

        # 精确包含（整词匹配）
        exact = name in text

        # 2-gram 匹配：实体名的 2 字片段在情报中出现过半则命中
        bigrams = set()
        for i in range(len(name) - 1):
            bigrams.add(name[i:i+2])
        bg_hits = sum(1 for bg in bigrams if bg in text)
        bg_ratio = bg_hits / max(len(bigrams), 1)

        # 综合判定：精确 或 2-gram 命中≥70%（避免"中程弹道导弹"被"弹道导弹"误命中）
        if exact or bg_ratio >= 0.7:
            matched.append({
                "id": e.id,
                "name_cn": e.name_cn,
                "type": e.type or "",
                "confidence": e.confidence or 1.0,
                "match_keyword": name,
                "properties": e.properties or {},
            })

    matched_ids = {m["id"] for m in matched}
    matched_names = {m["name_cn"] for m in matched}

    # 3. 找触发的逻辑规则
    all_rules = db.query(LogicRule).filter(
        LogicRule.ontology_id == ontology_id,
        LogicRule.enabled == True,
    ).all()

    triggered_rules: list[dict] = []
    for r in all_rules:
        linked = r.linked_entities or []
        hit = any(le in matched_names or any(le in mname for mname in matched_names) or any(mname in le for mname in matched_names) for le in linked)
        if hit:
            triggered_rules.append({
                "id": r.id,
                "name_cn": r.name_cn,
                "formula": r.formula or "",
                "description": r.description or "",
                "linked_entities": linked,
                "confidence": r.confidence or 1.0,
            })

    triggered_rule_ids = {r["id"] for r in triggered_rules}

    # 4. 找触发的动作
    all_actions = db.query(Action).filter(
        Action.ontology_id == ontology_id,
        Action.enabled == True,
    ).all()

    triggered_actions: list[dict] = []
    for a in all_actions:
        linked_ents = a.linked_entities or []
        linked_logics = a.linked_logic_ids or []
        hit = any(le in matched_names or any(le in mn for mn in matched_names) or any(mn in le for mn in matched_names) for le in linked_ents)
        if not hit:
            hit = any(lid in triggered_rule_ids for lid in linked_logics)
        if hit:
            triggered_actions.append({
                "id": a.id,
                "name_cn": a.name_cn,
                "name_en": a.name_en or "",
                "execution_rule": a.execution_rule or "",
                "function_code": a.function_code or "",
                "description": a.description or "",
                "linked_entities": linked_ents,
                "linked_logic_ids": linked_logics,
                "confidence": a.confidence or 1.0,
            })

    # 5. 危险评估（仅对匹配到的实体 + 它们之间的关系）
    matched_entity_list = [{"name_cn": m["name_cn"], "type": m["type"]} for m in matched]
    # 找出涉及匹配实体的关系
    all_relations = db.query(Relation).filter(Relation.ontology_id == ontology_id).all()
    matched_relation_list: list[dict] = []
    for r in all_relations:
        if r.source_entity in matched_ids or r.target_entity in matched_ids:
            matched_relation_list.append({
                "source": r.source_entity, "target": r.target_entity,
                "type": r.type or "关联",
            })

    if matched_entity_list:
        score, level = calculate_danger(matched_entity_list, matched_relation_list)
    else:
        score, level = 0.0, "low"

    # 综合建议：规则触发的动作 + 引擎建议
    action_recs = [a["name_cn"] for a in triggered_actions[:3]]
    engine_recs = generate_recommendations(level, matched_entity_list, matched_relation_list)
    all_recs = action_recs + [r for r in engine_recs if r not in action_recs]

    return {"data": {
        "ontology_id": ontology_id,
        "ontology_name": project.name,
        "matched_entities": matched,
        "triggered_rules": triggered_rules,
        "triggered_actions": triggered_actions,
        "danger_level": level,
        "danger_score": score,
        "recommendations": all_recs[:5],
        "mode": "quick",
    }}


# ══════════════════════════════════════════════════════════════════════
# POST /{ontology_id}/submit  — Layer 2 异步深度抽取
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
        # 追踪本次抽取新增的实体/关系（用于撤回）
        if latest.status == "completed" and latest.extraction_task_id:
            # 以快照创建时间为界，找出之后新增的实体和关系
            cutoff = latest.created_at
            new_entities = db.query(Entity).filter(
                Entity.ontology_id == ontology_id,
                Entity.created_at > cutoff
            ).all()
            new_relations = db.query(Relation).filter(
                Relation.ontology_id == ontology_id,
                Relation.created_at > cutoff
            ).all()
            if new_entities or new_relations:
                latest.created_entity_ids = [e.id for e in new_entities]
                latest.created_relation_ids = [r.id for r in new_relations]
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
# POST /{ontology_id}/undo-last  — 撤回最近一次深度抽取
# ══════════════════════════════════════════════════════════════════════

@router.post("/{ontology_id}/undo-last")
def undo_last_extraction(
    ontology_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """撤回最近一次深度抽取操作，删除其创建的实体和关系。"""
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    # 找最近一次有创建记录且未被撤回的快照
    latest = (
        db.query(IntelSnapshot)
        .filter(
            IntelSnapshot.ontology_id == ontology_id,
            IntelSnapshot.status == "completed",
        )
        .order_by(IntelSnapshot.created_at.desc())
        .first()
    )

    # 如果 created_entity_ids 为空，按时间回退查找
    entity_ids = latest.created_entity_ids if latest and latest.created_entity_ids else []
    relation_ids = latest.created_relation_ids if latest and latest.created_relation_ids else []

    if not entity_ids and latest and latest.created_at:
        # 回退方案：删除该快照创建时间之后的所有实体
        cutoff = latest.created_at
        late_entities = db.query(Entity).filter(
            Entity.ontology_id == ontology_id,
            Entity.created_at > cutoff
        ).all()
        late_relations = db.query(Relation).filter(
            Relation.ontology_id == ontology_id,
            Relation.created_at > cutoff
        ).all()
        entity_ids = [e.id for e in late_entities]
        relation_ids = [r.id for r in late_relations]

    if not latest or (not entity_ids and not relation_ids):
        return {"data": {"reverted": False, "message": "没有可撤回的操作"}}

    reverted_entities = 0
    reverted_relations = 0

    # 删除关系
    for rid in relation_ids:
        rel = db.query(Relation).filter(Relation.id == rid).first()
        if rel:
            db.delete(rel)
            reverted_relations += 1

    # 删除实体
    for eid in entity_ids:
        ent = db.query(Entity).filter(Entity.id == eid).first()
        if ent:
            db.delete(ent)
            reverted_entities += 1

    # 标记快照为已撤回
    latest.status = "reverted"
    db.commit()

    return {"data": {
        "reverted": True,
        "snapshot_label": latest.label,
        "reverted_entities": reverted_entities,
        "reverted_relations": reverted_relations,
        "message": f"已撤回 {latest.label}：删除 {reverted_entities} 个实体、{reverted_relations} 条关系",
    }}


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
    """从 PostgreSQL 构建图数据（跳过 Neo4j，确保 created_at 完整）。"""
    entities = db.query(Entity).filter(Entity.ontology_id == ontology_id).all()
    relations = db.query(Relation).filter(Relation.ontology_id == ontology_id).all()

    nodes: list[dict] = []
    for e in entities:
        created = e.created_at.isoformat() if e.created_at else None
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
                    "created_at": created,
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
