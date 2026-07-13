"""Phase 2 — ObjectType / ObjectInstance / Interface / LinkType / Link 的 CRUD 路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
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

    # 触发规则检查
    trigger_report = None
    try:
        from app.engine.trigger_service import TriggerService
        trigger = TriggerService(db)
        trigger_report = trigger.on_instance_updated(oi)
    except Exception:
        pass  # 规则引擎异常不阻断正常更新

    result = ObjectInstanceOut.model_validate(oi).model_dump()
    if trigger_report:
        result["_trigger_report"] = trigger_report
    return {"data": result}

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

@router.post("/{ontology_id}/interfaces", status_code=201)
def create_interface(ontology_id: str, body: InterfaceCreate, db: Session = Depends(get_db)):
    iface = Interface(id=str(uuid.uuid4()), ontology_id=ontology_id, **body.model_dump(exclude_none=True))
    db.add(iface); db.commit(); db.refresh(iface)
    return {"data": InterfaceOut.model_validate(iface).model_dump()}

@router.put("/{ontology_id}/interfaces/{iface_id}")
def update_interface(ontology_id: str, iface_id: str, body: InterfaceUpdate, db: Session = Depends(get_db)):
    iface = db.query(Interface).filter(Interface.id == iface_id, Interface.ontology_id == ontology_id).first()
    if not iface: raise HTTPException(404, "Interface not found")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(iface, k, v)
    db.commit(); db.refresh(iface)
    return {"data": InterfaceOut.model_validate(iface).model_dump()}

@router.delete("/{ontology_id}/interfaces/{iface_id}", status_code=204)
def delete_interface(ontology_id: str, iface_id: str, db: Session = Depends(get_db)):
    iface = db.query(Interface).filter(Interface.id == iface_id, Interface.ontology_id == ontology_id).first()
    if not iface: raise HTTPException(404, "Interface not found")
    db.delete(iface); db.commit()


# ── LinkType ─────────────────────────────────────────────────────
@router.get("/{ontology_id}/link-types")
def list_link_types(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(LinkType).filter(LinkType.ontology_id == ontology_id).all()
    return {"data": [LinkTypeOut.model_validate(o).model_dump() for o in items]}

@router.post("/{ontology_id}/link-types", status_code=201)
def create_link_type(ontology_id: str, body: LinkTypeCreate, db: Session = Depends(get_db)):
    lt = LinkType(id=str(uuid.uuid4()), ontology_id=ontology_id, **body.model_dump(exclude_none=True))
    db.add(lt); db.commit(); db.refresh(lt)
    return {"data": LinkTypeOut.model_validate(lt).model_dump()}

@router.put("/{ontology_id}/link-types/{lt_id}")
def update_link_type(ontology_id: str, lt_id: str, body: LinkTypeUpdate, db: Session = Depends(get_db)):
    lt = db.query(LinkType).filter(LinkType.id == lt_id, LinkType.ontology_id == ontology_id).first()
    if not lt: raise HTTPException(404, "LinkType not found")
    for k, v in body.model_dump(exclude_none=True).items(): setattr(lt, k, v)
    db.commit(); db.refresh(lt)
    return {"data": LinkTypeOut.model_validate(lt).model_dump()}

@router.delete("/{ontology_id}/link-types/{lt_id}", status_code=204)
def delete_link_type(ontology_id: str, lt_id: str, db: Session = Depends(get_db)):
    lt = db.query(LinkType).filter(LinkType.id == lt_id, LinkType.ontology_id == ontology_id).first()
    if not lt: raise HTTPException(404, "LinkType not found")
    db.delete(lt); db.commit()


# ── Link ─────────────────────────────────────────────────────────
@router.get("/{ontology_id}/links")
def list_links(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(Link).filter(Link.ontology_id == ontology_id).limit(200).all()
    return {"data": [LinkOut.model_validate(o).model_dump() for o in items]}

@router.delete("/{ontology_id}/links/{link_id}", status_code=204)
def delete_link(ontology_id: str, link_id: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id, Link.ontology_id == ontology_id).first()
    if not link: raise HTTPException(404, "Link not found")
    db.delete(link); db.commit()


# ── 规则触发（手动执行） ──────────────────────────────────────────
@router.post("/{ontology_id}/instances/{instance_id}/trigger-rules")
def trigger_rules(ontology_id: str, instance_id: str, db: Session = Depends(get_db)):
    """手动触发某个实例的规则检查，返回规则执行结果"""
    from app.models.v2.object_type import ObjectInstance
    from app.engine.trigger_service import TriggerService

    oi = db.query(ObjectInstance).filter(
        ObjectInstance.id == instance_id, ObjectInstance.ontology_id == ontology_id
    ).first()
    if not oi:
        raise HTTPException(404, "ObjectInstance not found")

    trigger = TriggerService(db)
    report = trigger.on_instance_updated(oi)
    return report


class ConfirmLinksBody(BaseModel):
    links: list[dict] = []

@router.post("/{ontology_id}/confirm-links")
def confirm_links(ontology_id: str, body: ConfirmLinksBody, db: Session = Depends(get_db)):
    """用户确认后，实际写入 Link 表"""
    import uuid as _uuid
    created = 0
    for item in body.links:
        lt = db.query(LinkType).filter(
            LinkType.ontology_id == ontology_id, LinkType.name_en == item.get("link_type", "")
        ).first()
        if not lt:
            continue
        existing = db.query(Link).filter(
            Link.ontology_id == ontology_id,
            Link.link_type_id == lt.id,
            Link.source_instance_id == item.get("source_instance_id", ""),
            Link.target_instance_id == item.get("target_instance_id", ""),
        ).first()
        if existing:
            continue
        db.add(Link(
            id=str(_uuid.uuid4()), ontology_id=ontology_id,
            link_type_id=lt.id,
            source_instance_id=item.get("source_instance_id", ""),
            target_instance_id=item.get("target_instance_id", ""),
            properties=item.get("properties", {}),
        ))
        created += 1
    if created:
        db.commit()
    return {"created": created}
