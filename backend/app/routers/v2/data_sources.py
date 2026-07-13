"""数据源 CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.deps import get_db, get_current_user
from app.models.v2.data_source import DataSource
import uuid

router = APIRouter(dependencies=[Depends(get_current_user)])

class DataSourceCreate(BaseModel):
    name: str
    db_config: dict = {}
    registered_table: Optional[str] = None

@router.get("/{ontology_id}/data-sources")
def list_sources(ontology_id: str, db: Session = Depends(get_db)):
    items = db.query(DataSource).filter(DataSource.ontology_id == ontology_id).all()
    return [{"id": s.id, "name": s.name, "db_config": s.db_config, "registered_table": s.registered_table, "created_at": s.created_at.isoformat() if s.created_at else None} for s in items]

@router.post("/{ontology_id}/data-sources", status_code=201)
def create_source(ontology_id: str, body: DataSourceCreate, db: Session = Depends(get_db)):
    ds = DataSource(id=str(uuid.uuid4()), ontology_id=ontology_id, name=body.name, db_config=body.db_config, registered_table=body.registered_table)
    db.add(ds); db.commit(); db.refresh(ds)
    return {"id": ds.id, "name": ds.name}

@router.delete("/{ontology_id}/data-sources/{source_id}", status_code=204)
def delete_source(ontology_id: str, source_id: str, db: Session = Depends(get_db)):
    ds = db.query(DataSource).filter(DataSource.id == source_id, DataSource.ontology_id == ontology_id).first()
    if not ds: raise HTTPException(404, "Not found")
    db.delete(ds); db.commit()
