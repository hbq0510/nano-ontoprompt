"""Phase 2 — ObjectType / ObjectInstance / Interface / LinkType / Link 的 CRUD 路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.v2.object_type import ObjectType, ObjectInstance, Interface, LinkType, Link
from app.schemas.object_type import (
    ObjectTypeCreate, ObjectTypeUpdate, ObjectTypeOut,
    ObjectInstanceCreate, ObjectInstanceUpdate, ObjectInstanceOut,
    InterfaceCreate, InterfaceUpdate, InterfaceOut,
    LinkTypeCreate, LinkTypeUpdate, LinkTypeOut,
    LinkCreate, LinkOut,
)
import uuid

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── ObjectType ───────────────────────────────────────────────────
@router.get("/{ontology_id}/object-types")
def list_object_types(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(ObjectType).filter(ObjectType.ontology_id == ontology_id).all()
    return {"data": [ObjectTypeOut.model_validate(o).model_dump() for o in items]}

@router.post("/{ontology_id}/object-types", status_code=201)
def create_object_type(ontology_id: str, body: ObjectTypeCreate, db: Session = Depends(get_db)):
    ot = ObjectType(id=str(uuid.uuid4()), ontology_id=ontology_id, **body.model_dump(exclude_none=True))
    db.add(ot); db.commit(); db.refresh(ot)
    return {"data": ObjectTypeOut.model_validate(ot).model_dump()}

@router.put("/{ontology_id}/object-types/{type_id}")
def update_object_type(ontology_id: str, type_id: str, body: ObjectTypeUpdate, db: Session = Depends(get_db)):
    ot = db.query(ObjectType).filter(ObjectType.id == type_id, ObjectType.ontology_id == ontology_id).first()
    if not ot: raise HTTPException(404, "ObjectType not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ot, k, v)
    db.commit(); db.refresh(ot)
    return {"data": ObjectTypeOut.model_validate(ot).model_dump()}

@router.delete("/{ontology_id}/object-types/{type_id}", status_code=204)
def delete_object_type(ontology_id: str, type_id: str, db: Session = Depends(get_db)):
    ot = db.query(ObjectType).filter(ObjectType.id == type_id, ObjectType.ontology_id == ontology_id).first()
    if not ot: raise HTTPException(404, "ObjectType not found")
    db.delete(ot); db.commit()


# ── ObjectInstance ───────────────────────────────────────────────
@router.get("/{ontology_id}/object-instances")
def list_instances(ontology_id: str, object_type_id: str = "", db: Session = Depends(get_db)):
    q = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == ontology_id)
    if object_type_id:
        q = q.filter(ObjectInstance.object_type_id == object_type_id)
    items = q.order_by(ObjectInstance.created_at.desc()).limit(200).all()
    return {"data": [ObjectInstanceOut.model_validate(o).model_dump() for o in items]}

@router.post("/{ontology_id}/object-instances", status_code=201)
def create_instance(ontology_id: str, body: ObjectInstanceCreate, db: Session = Depends(get_db)):
    oi = ObjectInstance(id=str(uuid.uuid4()), ontology_id=ontology_id, **body.model_dump(exclude_none=True))
    db.add(oi); db.commit(); db.refresh(oi)
    return {"data": ObjectInstanceOut.model_validate(oi).model_dump()}

@router.put("/{ontology_id}/object-instances/{instance_id}")
def update_instance(ontology_id: str, instance_id: str, body: ObjectInstanceUpdate, db: Session = Depends(get_db)):
    oi = db.query(ObjectInstance).filter(ObjectInstance.id == instance_id, ObjectInstance.ontology_id == ontology_id).first()
    if not oi: raise HTTPException(404, "ObjectInstance not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(oi, k, v)
    db.commit(); db.refresh(oi)
    return {"data": ObjectInstanceOut.model_validate(oi).model_dump()}

@router.delete("/{ontology_id}/object-instances/{instance_id}", status_code=204)
def delete_instance(ontology_id: str, instance_id: str, db: Session = Depends(get_db)):
    oi = db.query(ObjectInstance).filter(ObjectInstance.id == instance_id, ObjectInstance.ontology_id == ontology_id).first()
    if not oi: raise HTTPException(404, "ObjectInstance not found")
    db.delete(oi); db.commit()


# ── Interface ────────────────────────────────────────────────────
@router.get("/{ontology_id}/interfaces")
def list_interfaces(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(Interface).filter(Interface.ontology_id == ontology_id).all()
    return {"data": [InterfaceOut.model_validate(o).model_dump() for o in items]}


# ── LinkType ─────────────────────────────────────────────────────
@router.get("/{ontology_id}/link-types")
def list_link_types(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(LinkType).filter(LinkType.ontology_id == ontology_id).all()
    return {"data": [LinkTypeOut.model_validate(o).model_dump() for o in items]}


# ── Link ─────────────────────────────────────────────────────────
@router.get("/{ontology_id}/links")
def list_links(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(Link).filter(Link.ontology_id == ontology_id).limit(200).all()
    return {"data": [LinkOut.model_validate(o).model_dump() for o in items]}
