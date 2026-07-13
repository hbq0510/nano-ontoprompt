"""对象规则 API — CRUD for ObjectRule"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.object_rule import ObjectRule
import uuid

router = APIRouter(dependencies=[Depends(get_current_user)])


class RuleCreate(BaseModel):
    name_cn: str
    description: Optional[str] = None
    python_code: Optional[str] = None
    object_type_id: Optional[str] = None
    object_instance_id: Optional[str] = None


class RuleUpdate(BaseModel):
    name_cn: Optional[str] = None
    description: Optional[str] = None
    python_code: Optional[str] = None


# ── 列表 (可按 type_id 或 instance_id 过滤) ──
@router.get("/{ontology_id}/rules")
def list_rules(
    ontology_id: str,
    object_type_id: str = "",
    object_instance_id: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(ObjectRule).filter(ObjectRule.ontology_id == ontology_id)
    if object_type_id:
        q = q.filter(ObjectRule.object_type_id == object_type_id)
    if object_instance_id:
        q = q.filter(ObjectRule.object_instance_id == object_instance_id)
    rules = q.order_by(ObjectRule.created_at.desc()).all()
    return {
        "data": [
            {
                "id": r.id,
                "name_cn": r.name_cn,
                "description": r.description,
                "python_code": r.python_code,
                "object_type_id": r.object_type_id,
                "object_instance_id": r.object_instance_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ]
    }


# ── 创建 ──
@router.post("/{ontology_id}/rules", status_code=201)
def create_rule(ontology_id: str, body: RuleCreate, db: Session = Depends(get_db)):
    rule = ObjectRule(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        name_cn=body.name_cn,
        description=body.description,
        python_code=body.python_code,
        object_type_id=body.object_type_id or None,
        object_instance_id=body.object_instance_id or None,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "name_cn": rule.name_cn}


# ── 更新 ──
@router.put("/{ontology_id}/rules/{rule_id}")
def update_rule(ontology_id: str, rule_id: str, body: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(ObjectRule).filter(
        ObjectRule.id == rule_id, ObjectRule.ontology_id == ontology_id
    ).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    if body.name_cn is not None:
        rule.name_cn = body.name_cn
    if body.description is not None:
        rule.description = body.description
    if body.python_code is not None:
        rule.python_code = body.python_code
    db.commit()
    return {"id": rule.id, "status": "updated"}


# ── 删除 ──
@router.delete("/{ontology_id}/rules/{rule_id}", status_code=204)
def delete_rule(ontology_id: str, rule_id: str, db: Session = Depends(get_db)):
    rule = db.query(ObjectRule).filter(
        ObjectRule.id == rule_id, ObjectRule.ontology_id == ontology_id
    ).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    db.commit()
