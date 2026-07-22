"""情报系统路由 — CRUD + LLM 解析 + 推演集成 (延迟生效)"""

import json, uuid, logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.simulation import Scenario
from app.models.intelligence import Intelligence
from app.models.v2.object_type import ObjectInstance, Link, LinkType, ObjectType as OT

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


class IntelStatus:
    PENDING = "pending"   # 刚创建，未解析
    READY = "ready"       # 已解析，等待方案执行时在指定 tick 生效
    APPLIED = "applied"   # 方案已执行，在指定 tick 已生效

class IntelCreate(BaseModel):
    plan_id: Optional[str] = None
    tick: int
    text: str
    source: str = "manual"


class IntelOut(BaseModel):
    id: str; scenario_id: str; plan_id: Optional[str] = None; tick: int
    text: str; parsed: Optional[list] = None; status: str; source: Optional[str] = None
    created_at: Optional[str] = None
    model_config = {"from_attributes": True}

    @classmethod
    def from_obj(cls, it):
        return cls(id=it.id, scenario_id=it.scenario_id, plan_id=it.plan_id, tick=it.tick,
                   text=it.text, parsed=it.parsed, status=it.status, source=it.source,
                   created_at=it.created_at.isoformat() if it.created_at else None)


# ── CRUD ─────────────────────────────────────────────────────────

@router.get("/scenarios/{scenario_id}/intelligence")
def list_intelligence(scenario_id: str, plan_id: str = "", db: Session = Depends(get_db)):
    q = db.query(Intelligence).filter(Intelligence.scenario_id == scenario_id)
    if plan_id: q = q.filter(Intelligence.plan_id == plan_id)
    return {"data": [IntelOut.from_obj(i).model_dump() for i in q.order_by(Intelligence.tick).all()]}


@router.post("/scenarios/{scenario_id}/intelligence", status_code=201)
def create_intelligence(scenario_id: str, body: IntelCreate, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    it = Intelligence(id=str(uuid.uuid4()), scenario_id=scenario_id, plan_id=body.plan_id,
                      tick=body.tick, text=body.text, source=body.source, created_by=current_user.id)
    db.add(it); db.commit(); db.refresh(it)
    return {"data": IntelOut.from_obj(it).model_dump()}


@router.delete("/scenarios/{scenario_id}/intelligence/{intel_id}", status_code=204)
def delete_intelligence(scenario_id: str, intel_id: str, db: Session = Depends(get_db)):
    it = db.query(Intelligence).filter(Intelligence.id == intel_id, Intelligence.scenario_id == scenario_id).first()
    if not it: raise HTTPException(404)
    db.delete(it); db.commit()


# ── LLM 解析 ─────────────────────────────────────────────────────

@router.post("/scenarios/{scenario_id}/intelligence/{intel_id}/parse")
def parse_intelligence(scenario_id: str, intel_id: str, db: Session = Depends(get_db)):
    it = db.query(Intelligence).filter(Intelligence.id == intel_id, Intelligence.scenario_id == scenario_id).first()
    if not it: raise HTTPException(404)
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario: raise HTTPException(404)

    # 先试模板匹配，再试 LLM
    parsed = _template_parse(it.text, scenario, db)
    if parsed:
        it.parsed = parsed; it.status = "ready"; db.commit()
        return {"data": IntelOut.from_obj(it).model_dump()}

    # 模板不匹配时尝试 LLM（超时 30s）
    try:
        all_insts = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()
        context = {
            "participants": [{"id": i.id, "name": i.name_cn, "type": i.object_type_id,
                              "type_name": (db.query(OT).filter(OT.id==i.object_type_id).first().name_cn if db.query(OT).filter(OT.id==i.object_type_id).first() else ""),
                              "props": dict(i.properties or {})} for i in all_insts],
            "available_types": {ot.id: {"name_cn": ot.name_cn, "name_en": ot.name_en, "schema": ot.property_schema}
                               for ot in db.query(OT).filter(OT.ontology_id == scenario.ontology_id).all()},
            "links": [{"id": l.id, "link_type_id": l.link_type_id, "source": l.source_instance_id, "target": l.target_instance_id} for l in db.query(Link).filter(Link.ontology_id == scenario.ontology_id).all()],
        }
        lt_map = {lt.id: {"name_cn": lt.name_cn, "name_en": lt.name_en} for lt in db.query(LinkType).filter(LinkType.ontology_id == scenario.ontology_id).all()}
        it.status = "parsing"; db.commit()
        it.parsed = _llm_parse(it.text, context, lt_map, db)
        it.status = "ready"; db.commit()
    except Exception as e:
        logger.warning(f"LLM parse failed: {e}")
        it.status = "pending"; db.commit()
        raise HTTPException(500, f"LLM解析失败: {e}")
    return {"data": IntelOut.from_obj(it).model_dump()}


@router.post("/scenarios/{scenario_id}/intelligence/{intel_id}/apply")
def apply_intelligence(scenario_id: str, intel_id: str, db: Session = Depends(get_db)):
    it = db.query(Intelligence).filter(Intelligence.id == intel_id, Intelligence.scenario_id == scenario_id).first()
    if not it: raise HTTPException(404)
    if it.status != "parsed": raise HTTPException(400, "请先解析情报")
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    # 使用 deferred_only=True: add_instance 等 tick 到了再创建
    applied = _apply_operations(it.parsed or [], scenario, db, deferred_only=True)
    # 标记为 parsed（不是 applied），方案执行时会在指定 tick 处理
    it.status = "ready"; db.commit()
    return {"data": {"applied": applied, "intel": IntelOut.from_obj(it).model_dump(), "note": "情报已解析。方案执行时在指定tick自动生效"}}


# ── 引擎集成 ─────────────────────────────────────────────────────

def check_and_apply_intel(scenario_id: str, plan_id: str | None, current_tick: int, db: Session):
    """推演循环调用: 检查该 tick 的待处理情报, 自动解析+应用。add_instance 在指定 tick 创建"""
    pending = db.query(Intelligence).filter(
        Intelligence.scenario_id == scenario_id,
        Intelligence.tick == current_tick,
        Intelligence.status == "ready",  # 只处理已解析的 (解析需先行完成)
    ).all()
    events = []
    for it in pending:
        try:
                scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
                applied = _apply_operations(it.parsed or [], scenario, db, deferred_only=True)
                if applied:
                    it.status = "applied"; db.commit()
                    events.append({"tick": current_tick, "type": "intelligence",
                                   "desc": f"情报生效: {it.text[:50]}", "applied": applied})
        except Exception as e:
            logger.warning(f"Intel check at tick {current_tick}: {e}")
    return events


# ── 模板解析 (快速，不依赖 LLM) ─────────────────────────────────

def _template_parse(text: str, scenario, db) -> list | None:
    """用关键词匹配解析情报。返回 operations 或 None（表示无法匹配，需 LLM）"""
    import re
    text_lower = text.lower()

    # 匹配"新导弹"
    if any(kw in text_lower for kw in ("new missile", "新导弹", "新目标", "发现导弹")):
        # 提取坐标
        lat_match = re.search(r'lat\s*[:=]?\s*([\d.]+)', text_lower) or re.search(r'([\d.]+)\s*[n°]', text_lower)
        lon_match = re.search(r'lon\s*[:=]?\s*([\d.]+)', text_lower) or re.search(r'([\d.]+)\s*[e°]', text_lower)
        speed_match = re.search(r'speed\s*(?:mach)?\s*[:=]?\s*([\d.]+)', text_lower) or re.search(r'mach\s*([\d.]+)', text_lower)
        heading_match = re.search(r'head(?:ing)?\s*[:=]?\s*([\d.]+)', text_lower) or re.search(r'dir(?:ection)?\s*[:=]?\s*([\d.]+)', text_lower)
        alt_match = re.search(r'alt(?:itude)?\s*[:=]?\s*([\d.]+)', text_lower)

        lat = float(lat_match.group(1)) if lat_match else 30.5
        lon = float(lon_match.group(1)) if lon_match else 122.0
        speed = float(speed_match.group(1)) if speed_match else 5.0
        heading = float(heading_match.group(1)) if heading_match else 200.0
        alt = float(alt_match.group(1)) if alt_match else 100.0

        # 找导弹 ObjectType
        obj_type_id = None
        from app.models.v2.object_type import ObjectType as OT2
        for t in db.query(OT2).filter(OT2.ontology_id == scenario.ontology_id).all():
            if "direction_deg" in (t.property_schema or {}):
                obj_type_id = t.id; break

        return [{"action": "add_instance", "name_cn": "巡航导弹B",
                 "props": {"latitude": lat, "longitude": lon, "speed_mach": speed,
                          "direction_deg": heading, "altitude_km": alt, "status": "飞行中"}}]

    # 匹配"弹药不足"
    if any(kw in text_lower for kw in ("弹药", "ammo", "弹药不足", "low ammo")):
        count_match = re.search(r'(\d+)\s*(?:发|枚|rounds|shots)', text_lower) or re.search(r'only\s*(\d+)', text_lower)
        count = int(count_match.group(1)) if count_match else 1
        # 找拦截弹实例
        for pid in (scenario.participant_instance_ids or []):
            inst = db.query(ObjectInstance).filter(ObjectInstance.id == pid).first()
            if inst and (inst.properties or {}).get("range_km") and not (inst.properties or {}).get("detect_range_km"):
                return [{"action": "update_instance", "instance_id": inst.id, "props": {"ammo_count": count}}]

    # 匹配"雷达被干扰"
    if any(kw in text_lower for kw in ("雷达", "radar", "干扰", "jam", "诱饵")):
        radar = None
        missile = None
        radar2 = None
        for pid in (scenario.participant_instance_ids or []):
            inst = db.query(ObjectInstance).filter(ObjectInstance.id == pid).first()
            if inst:
                nm = (inst.name_cn or "").lower()
                if any(k in nm for k in ("雷达", "radar")):
                    if not radar: radar = inst
                    elif not radar2: radar2 = inst
                if any(k in nm for k in ("26b", "导弹", "missile")):
                    missile = inst
        ops = []
        if radar:
            # Delete old detection link
            lt = next((l for l in db.query(LinkType).filter(LinkType.ontology_id == scenario.ontology_id).all()
                      if any(k in (l.name_en or "").lower() for k in ("detect", "探测"))), None)
            if lt:
                old_links = db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id,
                                                   Link.source_instance_id == radar.id).all()
                for old in old_links:
                    ops.append({"action": "delete_link", "link_id": old.id})
            # Create new detection from backup radar if exists
            if radar2 and missile and lt:
                ops.append({"action": "create_link", "link_type": lt.name_cn or "探测", "source": radar2.id, "target": missile.id,
                            "props": {"detect_time": f"Tick {scenario.current_tick}", "status": "backup"}})
        if ops: return ops

    return None  # 无匹配，需要 LLM


# ── LLM ───────────────────────────────────────────────────────────

def _llm_parse(text: str, context: dict, lt_map: dict, db) -> list:
    try:
        from app.services import llm_service
        from app.services.model_config_selector import llm_call_kwargs, select_llm_model_config
        kw = llm_call_kwargs(select_llm_model_config(db, purpose_tags=("分析", "提取", "intelligence"), allow_vlm=False))
        if not kw: raise RuntimeError("No LLM config")

        prompt = f"""You are a military simulation parser. Convert this intelligence text into JSON operations.

INTELLIGENCE: {text}

Available ObjectType IDs: {json.dumps({k: f"{v.get('name_cn','')} ({', '.join(v.get('schema',{}).keys())})" for k,v in context.get('available_types',{}).items()}, ensure_ascii=False)[:500]}
Participants: {json.dumps(context['participants'], ensure_ascii=False)[:600]}

Return a JSON operation. Supported:
1. add_instance: {{"action":"add_instance","name_cn":"Name","props":{{"latitude":30.5,"longitude":122,"speed_mach":5,"direction_deg":200,"altitude_km":100}}}}
2. update_instance: {{"action":"update_instance","instance_id":"ID","props":{{"key":"value"}}}}
3. create_link: {{"action":"create_link","link_type":"Detect","source":"ID","target":"ID","props":{{}}}}
4. delete_link: {{"action":"delete_link","link_id":"LINK_ID"}}

For NEW missile: use add_instance with latitude/longitude/speed_mach/direction_deg.
Output ONLY the JSON object or array. No explanation."""

        raw = llm_service._call_llm(**kw, messages=[
            {"role": "system", "content": "Output ONLY a JSON object or array. No explanation."},
            {"role": "user", "content": prompt},
        ])
        text_raw = raw.strip()
        if "```" in text_raw:
            text_raw = text_raw.split("```")[1].replace("json", "", 1).strip()
        ops = json.loads(text_raw)
        if isinstance(ops, dict):
            if "action" in ops: ops = [ops]
            else: ops = ops.get("operations", ops.get("actions", []))
        return ops if isinstance(ops, list) else []
    except Exception as e:
        logger.warning(f"LLM parse error: {e}, raw={raw[:200] if 'raw' in dir() else ''}")
        raise


# ── 操作执行 ──────────────────────────────────────────────────────

def _apply_operations(ops: list, scenario, db, deferred_only: bool = False) -> list:
    """执行操作。deferred_only=True 时只创建 add_instance (延迟到 tick 生效)"""
    applied = []
    for op in (ops or []):
        action = op.get("action", "")
        try:
            if action == "update_instance":
                if deferred_only: continue
                inst = db.query(ObjectInstance).filter(ObjectInstance.id == op["instance_id"]).first()
                if inst:
                    dm = dict(scenario.design_params_map or {})
                    dm[op["instance_id"]] = {**dm.get(op["instance_id"], {}), **op.get("props", {})}
                    scenario.design_params_map = dm
                    inst.properties = {**dict(inst.properties or {}), **op.get("props", {})}
                    applied.append({"action": "update_instance", "id": op["instance_id"][:8]})

            elif action == "create_link":
                if deferred_only: continue
                lt_name = op.get("link_type", "")
                lt = next((l for l in db.query(LinkType).filter(LinkType.ontology_id == scenario.ontology_id).all()
                          if lt_name in (l.name_cn or "") or lt_name == (l.name_en or "")), None)
                if lt and op.get("source") and op.get("target"):
                    exist = db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id,
                                                   Link.source_instance_id == op["source"],
                                                   Link.target_instance_id == op["target"]).first()
                    if not exist:
                        db.add(Link(id=str(uuid.uuid4()), ontology_id=scenario.ontology_id, link_type_id=lt.id,
                                     source_instance_id=op["source"], target_instance_id=op["target"],
                                     properties=op.get("props", {})))
                        applied.append({"action": "create_link", "type": lt_name})

            elif action == "add_instance":
                obj_type_id = op.get("object_type_id", "")
                if not obj_type_id:
                    for t in db.query(OT).filter(OT.ontology_id == scenario.ontology_id).all():
                        if "direction_deg" in (t.property_schema or {}):
                            obj_type_id = t.id; break
                    if not obj_type_id and scenario.participant_instance_ids:
                        p0 = db.query(ObjectInstance).filter(
                            ObjectInstance.id == scenario.participant_instance_ids[0]).first()
                        if p0: obj_type_id = p0.object_type_id
                if obj_type_id:
                    props = op.get("props", {})
                    new_inst = ObjectInstance(id=str(uuid.uuid4()), ontology_id=scenario.ontology_id,
                                              object_type_id=obj_type_id, name_cn=op.get("name_cn", "新目标"),
                                              properties=props, confidence=0.9)
                    db.add(new_inst); db.flush()
                    dm = dict(scenario.design_params_map or {})
                    dm[new_inst.id] = {k: v for k, v in props.items() if k not in ("latitude", "longitude", "altitude_km")}
                    scenario.design_params_map = dm
                    # 不修改 participant_instance_ids，让 cleanup 时能清理
                    # 方案执行器的 all_entities 遍历所有实例，所以新实例也会被处理
                    applied.append({"action": "add_instance", "id": new_inst.id[:8], "name": new_inst.name_cn})

            elif action == "delete_link":
                if deferred_only: continue
                l = db.query(Link).filter(Link.id == op["link_id"]).first()
                if l: db.delete(l); applied.append({"action": "delete_link"})

        except Exception as e:
            logger.warning(f"Apply op failed: {e}")
    if applied:
        db.flush()
    return applied
