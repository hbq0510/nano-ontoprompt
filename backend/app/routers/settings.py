from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field
from app.deps import get_db, get_current_user
from app.models.rules_config import RulesConfig
from app.services.db_snapshot_service import DatabaseSnapshotService, SnapshotError, serialize_snapshot

router = APIRouter()


class RuleUpdate(BaseModel):
    rule_key: str
    rule_value: str


class SnapshotCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=40)


class SnapshotRestoreRequest(BaseModel):
    name: str


class SnapshotDeleteRequest(BaseModel):
    name: str


@router.get("/rules")
def get_rules(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rules = db.query(RulesConfig).order_by(RulesConfig.rule_key).all()
    return {"data": [
        {"id": r.id, "rule_key": r.rule_key, "rule_value": r.rule_value,
         "rule_label_cn": r.rule_label_cn, "rule_label_en": r.rule_label_en, "editable": r.editable}
        for r in rules
    ]}


@router.put("/rules")
def update_rules(body: List[RuleUpdate], db: Session = Depends(get_db), _=Depends(get_current_user)):
    for update in body:
        rule = db.query(RulesConfig).filter(RulesConfig.rule_key == update.rule_key, RulesConfig.editable == True).first()
        if rule:
            rule.rule_value = update.rule_value
    db.commit()
    return {"message": "Rules updated"}


@router.get("/snapshots")
def list_snapshots(_=Depends(get_current_user)):
    service = DatabaseSnapshotService()
    return {"data": [serialize_snapshot(item) for item in service.list_snapshots()]}


@router.post("/snapshots")
def create_snapshot(body: SnapshotCreateRequest, _=Depends(get_current_user)):
    service = DatabaseSnapshotService()
    try:
        snapshot = service.create_snapshot(body.label)
    except SnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"data": serialize_snapshot(snapshot), "message": "Snapshot created"}


@router.post("/snapshots/restore")
def restore_snapshot(body: SnapshotRestoreRequest, _=Depends(get_current_user)):
    service = DatabaseSnapshotService()
    try:
        snapshot = service.restore_snapshot(body.name)
    except SnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"data": serialize_snapshot(snapshot), "message": "Snapshot restored"}


@router.delete("/snapshots")
def delete_snapshot(body: SnapshotDeleteRequest, _=Depends(get_current_user)):
    service = DatabaseSnapshotService()
    try:
        service.delete_snapshot(body.name)
    except SnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Snapshot deleted"}
