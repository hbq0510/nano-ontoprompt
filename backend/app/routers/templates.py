"""
实体类型模板 API — 为每个本体定义实体类型的字段结构。

端点全部挂在 /api/v1/ontologies/{ontology_id}/templates 下。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.ontology import OntologyProject
from app.models.entity_template import EntityTemplate
from app.schemas.entity_template import (
    EntityTemplateCreate,
    EntityTemplateUpdate,
    EntityTemplateOut,
)
import uuid

router = APIRouter()


def _get_project(ontology_id: str, db: Session) -> OntologyProject:
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "本体项目不存在")
    return project


# ── 列表 ────────────────────────────────────────────────────────────

@router.get("")
def list_templates(
    ontology_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """获取某个本体下的所有实体类型模板。"""
    _get_project(ontology_id, db)
    templates = (
        db.query(EntityTemplate)
        .filter(EntityTemplate.ontology_id == ontology_id)
        .order_by(EntityTemplate.type_name.asc())
        .all()
    )
    return {
        "data": [EntityTemplateOut.model_validate(t).model_dump() for t in templates]
    }


# ── 单个 ────────────────────────────────────────────────────────────

@router.get("/{template_id}")
def get_template(
    ontology_id: str,
    template_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """获取单个模板详情。"""
    _get_project(ontology_id, db)
    t = db.query(EntityTemplate).filter(EntityTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    return {"data": EntityTemplateOut.model_validate(t).model_dump()}


# ── 创建 ────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_template(
    ontology_id: str,
    body: EntityTemplateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """为指定本体创建一个新的实体类型模板。"""
    _get_project(ontology_id, db)

    # 检查同一本体下 type_name 唯一
    existing = (
        db.query(EntityTemplate)
        .filter(
            EntityTemplate.ontology_id == ontology_id,
            EntityTemplate.type_name == body.type_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(400, f"类型「{body.type_name}」的模板已存在")

    t = EntityTemplate(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        type_name=body.type_name,
        type_name_en=body.type_name_en,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"data": EntityTemplateOut.model_validate(t).model_dump()}


# ── 更新 ────────────────────────────────────────────────────────────

@router.put("/{template_id}")
def update_template(
    ontology_id: str,
    template_id: str,
    body: EntityTemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """更新模板（部分更新）。"""
    _get_project(ontology_id, db)
    t = db.query(EntityTemplate).filter(EntityTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")

    if body.type_name is not None:
        t.type_name = body.type_name
    if body.type_name_en is not None:
        t.type_name_en = body.type_name_en
    if body.description is not None:
        t.description = body.description
    if body.fields is not None:
        t.fields = [f.model_dump() for f in body.fields]

    db.commit()
    db.refresh(t)
    return {"data": EntityTemplateOut.model_validate(t).model_dump()}


# ── 删除 ────────────────────────────────────────────────────────────

@router.delete("/{template_id}")
def delete_template(
    ontology_id: str,
    template_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """删除一个模板。"""
    _get_project(ontology_id, db)
    t = db.query(EntityTemplate).filter(EntityTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"data": {"deleted": True, "template_id": template_id}}
