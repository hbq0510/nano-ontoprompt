"""对象动作 API — CRUD for ObjectAction"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.deps import get_db, get_current_user
from app.models.object_action import ObjectAction
import uuid

router = APIRouter(dependencies=[Depends(get_current_user)])


class ActionCreate(BaseModel):
    name_cn: str
    description: Optional[str] = None
    python_code: Optional[str] = None
    object_type_id: Optional[str] = None
    object_instance_id: Optional[str] = None
    object_rule_id: Optional[str] = None


class ActionUpdate(BaseModel):
    name_cn: Optional[str] = None
    description: Optional[str] = None
    python_code: Optional[str] = None


@router.get("/{ontology_id}/actions-v2")
def list_actions(
    ontology_id: str,
    object_type_id: str = "",
    object_instance_id: str = "",
    object_rule_id: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(ObjectAction).filter(ObjectAction.ontology_id == ontology_id)
    if object_type_id:
        q = q.filter(ObjectAction.object_type_id == object_type_id)
    if object_instance_id:
        q = q.filter(ObjectAction.object_instance_id == object_instance_id)
    if object_rule_id:
        q = q.filter(ObjectAction.object_rule_id == object_rule_id)
    actions = q.order_by(ObjectAction.created_at.desc()).all()
    return {
        "data": [
            {
                "id": a.id, "name_cn": a.name_cn, "description": a.description,
                "python_code": a.python_code,
                "object_type_id": a.object_type_id, "object_instance_id": a.object_instance_id,
                "object_rule_id": a.object_rule_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in actions
        ]
    }


@router.post("/{ontology_id}/actions-v2", status_code=201)
def create_action(ontology_id: str, body: ActionCreate, db: Session = Depends(get_db)):
    act = ObjectAction(
        id=str(uuid.uuid4()), ontology_id=ontology_id,
        name_cn=body.name_cn, description=body.description, python_code=body.python_code,
        object_type_id=body.object_type_id or None,
        object_instance_id=body.object_instance_id or None,
        object_rule_id=body.object_rule_id or None,
    )
    db.add(act); db.commit(); db.refresh(act)
    return {"id": act.id, "name_cn": act.name_cn}


@router.put("/{ontology_id}/actions-v2/{action_id}")
def update_action(ontology_id: str, action_id: str, body: ActionUpdate, db: Session = Depends(get_db)):
    act = db.query(ObjectAction).filter(
        ObjectAction.id == action_id, ObjectAction.ontology_id == ontology_id
    ).first()
    if not act:
        raise HTTPException(404, "Action not found")
    if body.name_cn is not None: act.name_cn = body.name_cn
    if body.description is not None: act.description = body.description
    if body.python_code is not None: act.python_code = body.python_code
    db.commit()
    return {"id": act.id, "status": "updated"}


@router.delete("/{ontology_id}/actions-v2/{action_id}", status_code=204)
def delete_action(ontology_id: str, action_id: str, db: Session = Depends(get_db)):
    act = db.query(ObjectAction).filter(
        ObjectAction.id == action_id, ObjectAction.ontology_id == ontology_id
    ).first()
    if not act: raise HTTPException(404, "Action not found")
    db.delete(act); db.commit()
