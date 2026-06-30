"""Skills CRUD + Trigger API — v2"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.deps import get_db, get_current_user
from app.models.skill import Skill, SkillTrigger
from app.models.user import User
from app.models.prompt import Prompt
from app.models.model_config import ModelConfig
from app.schemas.skill import SkillCreate, SkillUpdate, SkillOut, SkillListItem, SkillTriggerOut
import uuid
import os
from datetime import datetime, timezone

router = APIRouter()


# ── Skill CRUD ──────────────────────────────────────────────────────


@router.get("")
def list_skills(
    domain: Optional[str] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Skill)
    if domain:
        q = q.filter(Skill.domain == domain)
    if enabled_only:
        q = q.filter(Skill.enabled == True)
    skills = q.order_by(Skill.created_at.desc()).all()
    return {"data": [SkillListItem.model_validate(s).model_dump() for s in skills]}


@router.post("", status_code=201)
def create_skill(
    body: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # verify references exist if provided
    if body.prompt_id:
        if not db.query(Prompt).filter(Prompt.id == body.prompt_id).first():
            raise HTTPException(400, f"Prompt {body.prompt_id} not found")
    if body.model_id:
        if not db.query(ModelConfig).filter(ModelConfig.id == body.model_id).first():
            raise HTTPException(400, f"ModelConfig {body.model_id} not found")

    skill = Skill(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description or "",
        domain=body.domain or "军事",
        accepted_input_types=body.accepted_input_types or ["text/plain"],
        prompt_id=body.prompt_id,
        model_id=body.model_id,
        ontology_name_pattern=body.ontology_name_pattern or "{skill_name}-{timestamp}",
        prebuilt_entities=body.prebuilt_entities or [],
        created_by=current_user.id,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return {"data": SkillOut.model_validate(skill).model_dump()}


@router.get("/{skill_id}")
def get_skill(skill_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s:
        raise HTTPException(404, "Skill not found")
    return {"data": SkillOut.model_validate(s).model_dump()}


@router.put("/{skill_id}")
def update_skill(
    skill_id: str,
    body: SkillUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s:
        raise HTTPException(404, "Skill not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return {"data": SkillOut.model_validate(s).model_dump()}


@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s:
        raise HTTPException(404, "Skill not found")
    db.delete(s)
    db.commit()


# ── Trigger API ─────────────────────────────────────────────────────


@router.post("/{skill_id}/trigger", status_code=201)
def trigger_skill(
    skill_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """外部系统调用：上传文件并触发 Skill，创建 pending 触发记录"""
    import json as _json

    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(404, "Skill not found")
    if not skill.enabled:
        raise HTTPException(400, "Skill is disabled")

    # Parse metadata
    try:
        meta = _json.loads(metadata) if isinstance(metadata, str) else metadata
    except _json.JSONDecodeError:
        meta = {}

    # Save file to MinIO (or local uploads for dev)
    file_ext = os.path.splitext(file.filename or "data")[1]
    stored_name = f"skill_{skill_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    stored_path = _save_upload(file, stored_name)

    trigger = SkillTrigger(
        id=str(uuid.uuid4()),
        skill_id=skill_id,
        status="pending",
        input_file_path=stored_path,
        input_file_name=file.filename or "unknown",
        input_metadata=meta,
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)

    return {
        "data": {
            "trigger_id": trigger.id,
            "status": trigger.status,
            "message": "Skill triggered, waiting for user confirmation",
        }
    }


@router.get("/triggers/pending")
def list_pending_triggers(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """获取所有 pending 状态的触发记录（前端轮询用）"""
    triggers = (
        db.query(SkillTrigger)
        .filter(SkillTrigger.status == "pending")
        .order_by(SkillTrigger.created_at.desc())
        .all()
    )
    result = []
    for t in triggers:
        skill = db.query(Skill).filter(Skill.id == t.skill_id).first()
        d = SkillTriggerOut.model_validate(t).model_dump()
        d["skill_name"] = skill.name if skill else "Unknown"
        result.append(d)
    return {"data": result}


@router.post("/triggers/{trigger_id}/confirm")
def confirm_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户确认触发 → 创建 Ontology → 关联文件 → 投递抽取任务"""
    trigger = db.query(SkillTrigger).filter(SkillTrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    if trigger.status != "pending":
        raise HTTPException(400, f"Trigger status is '{trigger.status}', cannot confirm")

    skill = db.query(Skill).filter(Skill.id == trigger.skill_id).first()
    if not skill:
        raise HTTPException(404, "Skill not found")

    # ── 1. 创建 Ontology 项目 ──
    from app.models.ontology import OntologyProject

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    onto_name = skill.ontology_name_pattern.replace("{skill_name}", skill.name).replace(
        "{timestamp}", ts
    )

    ontology = OntologyProject(
        id=str(uuid.uuid4()),
        name=onto_name,
        domain=skill.domain,
        description=f"由 Skill「{skill.name}」自动创建",
        build_mode="simple_llm",
        created_by=current_user.id,
    )
    db.add(ontology)
    db.flush()

    # ── 2. 将文件关联到 Ontology（创建 UploadedFile 记录）──
    from app.models.file import UploadedFile

    uf = UploadedFile(
        id=str(uuid.uuid4()),
        ontology_id=ontology.id,
        filename=trigger.input_file_name,
        file_path=trigger.input_file_path,
        file_size=0,
        mime_type=_guess_mime(trigger.input_file_name),
        converted_md="",  # will be handled by extraction via vision LLM
    )
    db.add(uf)
    db.flush()

    # ── 3. 投递抽取任务 ──
    from app.models.extraction_task import ExtractionTask

    task = ExtractionTask(
        id=str(uuid.uuid4()),
        ontology_id=ontology.id,
        prompt_id=skill.prompt_id or None,
        model_id=skill.model_id or None,
        status="queued",
        parameters={
            "file_ids": [uf.id],
            "skill_id": skill.id,
            "prebuilt_entities": skill.prebuilt_entities or [],
            "input_file_path": trigger.input_file_path,
            "input_file_name": trigger.input_file_name,
        },
        progress={"stage": "queued", "pct": 0},
    )
    db.add(task)
    db.flush()

    # Update trigger
    trigger.status = "executing"
    trigger.ontology_id = ontology.id
    trigger.extraction_task_id = task.id

    # Update ontology status
    ontology.status = "creating"

    db.commit()
    db.refresh(task)

    # Queue Celery task
    try:
        from app.tasks.extraction import run_extraction

        run_extraction.delay(task.id)
    except Exception:
        import threading

        def run_sync():
            from app.tasks.extraction import run_extraction

            try:
                run_extraction(task.id)
            except Exception:
                pass

        threading.Thread(target=run_sync, daemon=True).start()

    return {
        "data": {
            "trigger_id": trigger.id,
            "ontology_id": ontology.id,
            "extraction_task_id": task.id,
            "status": "executing",
            "message": "Ontology created, extraction started",
        }
    }


@router.post("/triggers/{trigger_id}/reject")
def reject_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """用户拒绝触发 → 清理"""
    trigger = db.query(SkillTrigger).filter(SkillTrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    if trigger.status != "pending":
        raise HTTPException(400, f"Trigger status is '{trigger.status}', cannot reject")

    trigger.status = "rejected"
    db.commit()

    # Clean up temp file (best-effort)
    _delete_upload(trigger.input_file_path)

    return {"data": {"trigger_id": trigger.id, "status": "rejected"}}


@router.get("/triggers/{trigger_id}")
def get_trigger(
    trigger_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    trigger = db.query(SkillTrigger).filter(SkillTrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    skill = db.query(Skill).filter(Skill.id == trigger.skill_id).first()
    d = SkillTriggerOut.model_validate(trigger).model_dump()
    d["skill_name"] = skill.name if skill else "Unknown"
    return {"data": d}


# ── Helpers ──────────────────────────────────────────────────────────


def _save_upload(file: UploadFile, stored_name: str) -> str:
    """Save uploaded file to MinIO or local uploads dir."""
    from app.config import settings

    # Read content once
    content = file.file.read()
    file.file.seek(0)

    # Try MinIO first
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        bucket = "skill-triggers"
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, stored_name, content, len(content))
        return f"minio://{bucket}/{stored_name}"
    except Exception:
        pass

    # Fallback to local uploads
    uploads_dir = os.path.join(settings.uploads_dir, "skill-triggers")
    os.makedirs(uploads_dir, exist_ok=True)
    full_path = os.path.join(uploads_dir, stored_name)
    with open(full_path, "wb") as f:
        f.write(content)
    return full_path


def _delete_upload(file_path: str):
    """Delete a previously uploaded file (best-effort)."""
    try:
        if file_path.startswith("minio://"):
            from app.config import settings
            from minio import Minio

            bucket, obj = file_path[8:].split("/", 1)
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_use_ssl,
            )
            client.remove_object(bucket, obj)
        elif os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def _guess_mime(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".json": "application/json",
        ".csv": "text/csv",
        ".md": "text/markdown",
    }
    return mapping.get(ext, "application/octet-stream")
