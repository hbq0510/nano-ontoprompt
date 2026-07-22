"""方案系统路由 — Plan CRUD + 执行 + 对比 + LLM 生成"""

import json, uuid, math, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.simulation import Scenario, ScenarioTick, ScenarioEvent
from app.models.plan import Plan, PlanRun
from app.models.v2.object_type import ObjectInstance, Link, LinkType
from app.schemas.plan import PlanCreate, PlanUpdate, PlanOut, PlanListItem, PlanRunOut, GenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Helpers: 用属性特征识别参与者类型（避免编码问题）─────────────
def _find_missile(participants):
    return next((p for p in participants if (p.properties or {}).get("direction_deg") is not None), None)

def _find_interceptor(participants):
    return next((p for p in participants if (p.properties or {}).get("range_km") is not None and not (p.properties or {}).get("detect_range_km")), None)

def _find_radar(participants):
    return next((p for p in participants if (p.properties or {}).get("detect_range_km") is not None), None)

def _find_lt_by_keyword(db, ontology_id, keyword):
    """查找包含特定关键词的 LinkType（keyword 用英文避免编码问题）"""
    lts = db.query(LinkType).filter(LinkType.ontology_id == ontology_id).all()
    kw = keyword.lower()
    for lt in lts:
        if kw in (lt.name_en or "").lower() or kw in (lt.name_cn or "").lower():
            return lt
    return None


# ═══════════════════════════════════════════════════════════════════
# Plan CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/scenarios/{scenario_id}/plans")
def list_plans(scenario_id: str, db: Session = Depends(get_db)):
    items = db.query(Plan).filter(Plan.scenario_id == scenario_id).order_by(Plan.created_at.desc()).all()
    return {"data": [PlanListItem.model_validate(p).model_dump() for p in items]}


@router.post("/scenarios/{scenario_id}/plans", status_code=201)
def create_plan(scenario_id: str, body: PlanCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario: raise HTTPException(404, "Scenario not found")
    decisions = [d.model_dump() for d in body.decisions]
    plan = Plan(id=str(uuid.uuid4()), scenario_id=scenario_id, name=body.name,
                description=body.description, decisions=decisions,
                source=body.source or "manual", template_id=body.template_id, created_by=current_user.id)
    db.add(plan); db.commit(); db.refresh(plan)
    return {"data": PlanOut.model_validate(plan).model_dump()}


@router.get("/scenarios/{scenario_id}/plans/compare")
def compare_plans(scenario_id: str, db: Session = Depends(get_db)):
    plans = db.query(Plan).filter(Plan.scenario_id == scenario_id, Plan.status == "evaluated").all()
    items = [{"plan_id": p.id, "plan_name": p.name, "score": p.score or {}, "status": p.status} for p in plans]
    best = max(items, key=lambda x: x["score"].get("kill_probability", 0) or 0) if items else None
    return {"data": {"items": items, "best": best}}


@router.get("/scenarios/{scenario_id}/plans/{plan_id}")
def get_plan(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan: raise HTTPException(404, "Plan not found")
    return {"data": PlanOut.model_validate(plan).model_dump()}


@router.put("/scenarios/{scenario_id}/plans/{plan_id}")
def update_plan(scenario_id: str, plan_id: str, body: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan: raise HTTPException(404)
    if body.name is not None: plan.name = body.name
    if body.description is not None: plan.description = body.description
    if body.decisions is not None: plan.decisions = [d.model_dump() for d in body.decisions]
    if body.status is not None: plan.status = body.status
    if body.score is not None: plan.score = body.score
    db.commit(); db.refresh(plan)
    return {"data": PlanOut.model_validate(plan).model_dump()}


@router.delete("/scenarios/{scenario_id}/plans/{plan_id}", status_code=204)
def delete_plan(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan: raise HTTPException(404)
    db.query(PlanRun).filter(PlanRun.plan_id == plan_id).delete()
    db.delete(plan); db.commit()


# ═══════════════════════════════════════════════════════════════════
# LLM 方案生成
# ═══════════════════════════════════════════════════════════════════

@router.post("/scenarios/{scenario_id}/plans/generate")
def generate_plans(scenario_id: str, body: GenerateRequest, db: Session = Depends(get_db)):
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario: raise HTTPException(404)

    instances = db.query(ObjectInstance).filter(ObjectInstance.id.in_(scenario.participant_instance_ids or [])).all()
    constraints = _build_constraints(scenario, instances)

    generated = []
    try:
        generated = _llm_generate(scenario, constraints, body.count, body.strategy, db)
    except Exception as e:
        logger.warning(f"LLM generation failed, using rules: {e}")
        generated = _rule_generate(constraints, body.count, body.strategy)

    saved = []
    for g in generated:
        plan = Plan(id=str(uuid.uuid4()), scenario_id=scenario_id, name=g["name"],
                    description=g.get("description", ""), decisions=g.get("decisions", []),
                    source="llm", status="proposed", score={})
        db.add(plan); db.commit(); db.refresh(plan)
        saved.append(PlanOut.model_validate(plan).model_dump())
    return {"data": saved}


# ═══════════════════════════════════════════════════════════════════
# 方案执行
# ═══════════════════════════════════════════════════════════════════

@router.post("/scenarios/{scenario_id}/plans/{plan_id}/run")
def run_plan(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan: raise HTTPException(404)
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario: raise HTTPException(404)

    # 重置所有情报状态为 ready（每个方案独立运行）
    from app.models.intelligence import Intelligence as IntelModel
    all_intel = db.query(IntelModel).filter(IntelModel.scenario_id == scenario_id).all()
    for it in all_intel:
        if it.status == "applied":
            it.status = "ready"
    db.flush()

    # Cleanup: 删除旧 run 的数据 + 重置实体
    db.query(Link).filter(Link.ontology_id == scenario.ontology_id).delete()
    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()

    # 删除之前情报创建的额外实例（保留原始参与者）
    original_ids = set(scenario.participant_instance_ids or [])
    extra_instances = db.query(ObjectInstance).filter(
        ObjectInstance.ontology_id == scenario.ontology_id,
        ~ObjectInstance.id.in_(original_ids)
    ).all()
    for extra in extra_instances:
        db.delete(extra)
    db.flush()

    # 重置参与者到初始位置 + 设计参数
    participants = db.query(ObjectInstance).filter(
        ObjectInstance.ontology_id == scenario.ontology_id).all()
    design_map = scenario.design_params_map or {}
    for inst in participants:
        # 恢复固定设计参数
        dm = design_map.get(inst.id, {})
        if dm:
            inst.properties = dict(dm)
        # 覆盖初始位置
        init = next((x for x in (scenario.initial_state or []) if x.get("instance_id") == inst.id), None)
        if init and init.get("initial_properties"):
            pos = init["initial_properties"]
            inst.properties = {**dict(inst.properties or {}), "latitude": pos.get("latitude", 0), "longitude": pos.get("longitude", 0),
                              "altitude_km": pos.get("altitude_km", 200)}
    db.flush()
    logger.info(f"Plan runner: {len(participants)} participants (design params + positions reset)")

    run = PlanRun(id=str(uuid.uuid4()), plan_id=plan_id, scenario_id=scenario_id,
                  status="running", started_at=datetime.now(timezone.utc))
    db.add(run); db.commit(); db.refresh(run)
    scenario.status = "running"; scenario.current_tick = 0; db.commit()

    decisions = plan.decisions or []
    decision_idx = 0
    max_ticks = scenario.max_ticks or 50
    tick_count = 0
    decision_log: list[dict] = []
    all_events: list[dict] = []

    for tick in range(1, max_ticks + 1):
        tick_count = tick
        tick_events = []

        # 📡 检查情报插入
        from app.routers.v2.intelligence import check_and_apply_intel
        intel_events = check_and_apply_intel(scenario_id, plan_id, tick, db)
        tick_events.extend(intel_events)

        # 📡 检查该 tick 是否有待处理的 add_instance 情报
        from app.routers.v2.intelligence import check_and_apply_intel
        intel_events = check_and_apply_intel(scenario_id, plan_id, tick, db)
        tick_events.extend(intel_events)
        # 重新加载所有实例（情报可能创建了新实体，不在 participant_ids 里）
        participants = db.query(ObjectInstance).filter(
            ObjectInstance.ontology_id == scenario.ontology_id).all()

        # Move all movable entities (遍历所有实例，不只参与者)
        all_entities = db.query(ObjectInstance).filter(
            ObjectInstance.ontology_id == scenario.ontology_id).all()
        for inst in all_entities:
            props = inst.properties or {}
            speed = float(props.get("speed_mach", 0) or 0)
            direction = props.get("direction_deg")
            if speed > 0 and direction is not None:
                lat = float(props.get("latitude", 0) or 0)
                lon = float(props.get("longitude", 0) or 0)
                step_km = 3.43 * speed
                rad = math.radians(float(direction))
                dlat = (step_km * math.cos(rad)) / 111.0
                dlon = (step_km * math.sin(rad)) / (111.0 * math.cos(math.radians(lat)))
                inst.properties = {**dict(props), "latitude": round(lat + dlat, 4), "longitude": round(lon + dlon, 4)}
                tick_events.append({"tick": tick, "type": "move", "desc": f"{inst.name_cn} moved"})

        # Check decision triggers
        while decision_idx < len(decisions):
            d = decisions[decision_idx]
            triggered = _check_trigger(d, participants, db, scenario, tick, decision_log)
            if triggered:
                tick_events.append({"tick": tick, "type": "decision", "desc": f"Decision: {d.get('action')}", "decision": d})
                decision_log.append({"tick": tick, "decision": d, "status": "triggered"})
                _execute_decision(d, participants, db, scenario)
                decision_idx += 1
            else:
                break

        all_events.extend(tick_events)
        scenario.current_tick = tick
        instance_states = [{"instance_id": i.id, "instance_name": i.name_cn, "properties": dict(i.properties or {})} for i in participants]
        db.add(ScenarioTick(id=str(uuid.uuid4()), scenario_id=scenario_id, tick=tick, instance_states=instance_states,
                            active_links=[], events=[e["desc"] for e in tick_events]))
        db.flush()

        # Check stop
        stop_reason = _eval_stop(scenario, decisions, decision_idx, participants, db)
        if stop_reason:
            all_events.append({"tick": tick, "type": "stop", "desc": stop_reason})
            break

    score = _eval_score(plan, decision_log, all_events, tick_count, scenario, db)
    plan.status = "evaluated"; plan.score = score
    run.status = "success"; run.tick_count = tick_count; run.result = score
    run.decision_log = decision_log; run.events = all_events
    run.finished_at = datetime.now(timezone.utc)
    scenario.status = "finished"
    db.commit()
    return {"data": {"plan": PlanOut.model_validate(plan).model_dump(), "run": PlanRunOut.model_validate(run).model_dump()}}


# ═══════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════

@router.get("/plans/templates")
def list_templates(db: Session = Depends(get_db)):
    templates = db.query(Plan).filter(Plan.source == "template").order_by(Plan.updated_at.desc()).all()
    return {"data": [PlanListItem.model_validate(t).model_dump() for t in templates]}

@router.post("/scenarios/{scenario_id}/plans/{plan_id}/save-template")
def save_as_template(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan: raise HTTPException(404)
    plan.source = "template"; plan.template_id = f"tpl_{plan.id[:8]}"
    db.commit()
    return {"data": PlanOut.model_validate(plan).model_dump()}


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _build_constraints(scenario, instances):
    c = {"participants": [], "scenario": {"name": scenario.name, "max_ticks": scenario.max_ticks}}
    for inst in instances:
        props = dict(inst.properties or {})
        info = {"id": inst.id, "name": inst.name_cn, "props": props}
        if props.get("direction_deg"): c.setdefault("missiles", []).append(info)
        elif props.get("detect_range_km"): c.setdefault("sensors", []).append(info)
        elif props.get("range_km"): c.setdefault("interceptors", []).append(info)
        c["participants"].append(info)
    c["missile_count"] = len(c.get("missiles", []))
    c["interceptor_count"] = len(c.get("interceptors", []))
    c["sensor_count"] = len(c.get("sensors", []))
    return c


def _llm_generate(scenario, constraints, count, strategy, db):
    try:
        from app.services import llm_service
        from app.services.model_config_selector import llm_call_kwargs, select_llm_model_config
        call_kwargs = llm_call_kwargs(select_llm_model_config(db, purpose_tags=("分析", "提取", "FK检测", "plan", "strategy"), allow_vlm=False))
        if not call_kwargs: raise RuntimeError("No LLM config")
        prompt = f"""请为以下防空拦截想定生成{count}种不同的拦截方案。请用中文回答。

想定信息: {json.dumps(constraints['scenario'], ensure_ascii=False)}
可用资源: {json.dumps(constraints, ensure_ascii=False)[:1500]}
策略偏好: {strategy}

重要：只能使用以下触发条件:
- "distance<N" (导弹距拦截弹小于N公里, 例如"distance<400")
- "detected" (雷达已探测到目标)
- "intercept_success" (拦截成功)
- "intercept_failed" (拦截失败)
- "tick>=N" (推演进行到第N帧)

支持的动作: launch(发射), track(跟踪), stop(停止)
动作对象: interceptor(拦截弹), radar(雷达)

输出JSON格式:
{{"plans":[{{"name":"方案名称(中文)","description":"方案描述(中文)","decisions":[{{"trigger":"distance<400","target":"interceptor","action":"launch","params":{{"count":2,"mode":"salvo"}}}}]}}]}}
只返回JSON, 不要其他文字。"""
        raw = llm_service._call_llm(**call_kwargs, messages=[{"role":"system","content":"You are a military simulation expert. Output JSON."}, {"role":"user","content":prompt}])
        data = json.loads(raw) if isinstance(raw, str) else raw
        return (data.get("plans", []) if isinstance(data, dict) else data)[:count]
    except Exception as e:
        logger.warning(f"LLM failed: {e}"); raise


def _rule_generate(constraints, count, strategy):
    templates = [
        {"name": "Conservative Salvo", "description": "Launch 2 interceptors simultaneously for high kill probability",
         "decisions": [
             {"trigger": "distance<400", "target": "interceptor", "action": "launch", "params": {"count": 2, "mode": "salvo"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "Single Shot Economical", "description": "Fire 1 first, fire 2nd only if first fails",
         "decisions": [
             {"trigger": "distance<300", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_failed", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "Detection-First", "description": "Track first, then rapid fire when in range",
         "decisions": [
             {"trigger": "detected", "target": "radar", "action": "track", "params": {"mode": "continuous"}},
             {"trigger": "distance<350", "target": "interceptor", "action": "launch", "params": {"count": 2, "mode": "rapid"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "Aggressive Long-Range", "description": "Launch at max range for larger engagement window",
         "decisions": [
             {"trigger": "distance<600", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "long_range"}},
             {"trigger": "intercept_failed", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
    ]
    if strategy == "conservative": templates = templates[:2]
    elif strategy == "aggressive": templates = [templates[3], templates[0]]
    return templates[:count]


def _check_trigger(decision, participants, db, scenario, tick, log):
    trigger = (decision.get("trigger") or "").strip()
    if not trigger: return False

    if trigger.startswith("distance<"):
        threshold = float(trigger.split("<")[1])
        i = _find_interceptor(participants)
        if i:
            ip = i.properties or {}
            # Check ALL missiles, not just the first one
            all_missiles = [p for p in participants if (p.properties or {}).get("direction_deg") is not None]
            for m in all_missiles:
                mp = m.properties or {}
                d = math.sqrt(((mp.get("latitude",0)-ip.get("latitude",0))*111)**2 + ((mp.get("longitude",0)-ip.get("longitude",0))*111*math.cos(math.radians(ip.get("latitude",0))))**2)
                if d < threshold:
                    return True
        return False

    if trigger == "detected":
        lt = _find_lt_by_keyword(db, scenario.ontology_id, "detect")
        if lt:
            return db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id).count() > 0
        return False

    if trigger == "intercept_success":
        for l in (log or []):
            if l.get("decision", {}).get("action") == "stop": return True
        return False

    if trigger == "intercept_failed":
        return len(log) > 0 and log[-1].get("status") != "triggered"

    if trigger.startswith("tick>="):
        return tick >= int(trigger.split(">=")[1])

    return False


def _execute_decision(decision, participants, db, scenario):
    action = (decision.get("action") or "").strip()
    if action == "launch":
        i = _find_interceptor(participants)
        all_missiles = [p for p in participants if (p.properties or {}).get("direction_deg") is not None]
        if i and all_missiles:
            lt = _find_lt_by_keyword(db, scenario.ontology_id, "intercept")
            if lt:
                # Create link for the CLOSEST missile
                ip = i.properties or {}
                closest = min(all_missiles, key=lambda p: math.sqrt(((p.properties.get("latitude",0)-ip.get("latitude",0))*111)**2 + ((p.properties.get("longitude",0)-ip.get("longitude",0))*111*math.cos(math.radians(ip.get("latitude",0))))**2))
                existing = db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id,
                                                   Link.source_instance_id == i.id, Link.target_instance_id == closest.id).first()
                if not existing:
                    db.add(Link(id=str(uuid.uuid4()), ontology_id=scenario.ontology_id, link_type_id=lt.id,
                                source_instance_id=i.id, target_instance_id=closest.id,
                                properties={"count": decision.get("params", {}).get("count", 1), "tick": scenario.current_tick}))
                    db.flush()
    elif action == "track":
        r = _find_radar(participants)
        all_missiles = [p for p in participants if (p.properties or {}).get("direction_deg") is not None]
        if r and all_missiles:
            lt = _find_lt_by_keyword(db, scenario.ontology_id, "detect")
            if lt:
                closest = min(all_missiles, key=lambda p: math.sqrt(((p.properties.get("latitude",0)-r.properties.get("latitude",0))*111)**2 + ((p.properties.get("longitude",0)-r.properties.get("longitude",0))*111*math.cos(math.radians(r.properties.get("latitude",0))))**2))
                existing = db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id,
                                                   Link.source_instance_id == r.id, Link.target_instance_id == closest.id).first()
                if not existing:
                    db.add(Link(id=str(uuid.uuid4()), ontology_id=scenario.ontology_id, link_type_id=lt.id,
                                source_instance_id=r.id, target_instance_id=closest.id,
                                properties={"mode": decision.get("params", {}).get("mode", "continuous"), "tick": scenario.current_tick}))
                    db.flush()


def _eval_stop(scenario, decisions, decision_idx, participants, db):
    if decision_idx >= len(decisions): return "All decisions executed"
    m = _find_missile(participants)
    i = _find_interceptor(participants)
    if m and i:
        mp = m.properties or {}; ip = i.properties or {}
        d = math.sqrt(((mp.get("latitude",0)-ip.get("latitude",0))*111)**2 + ((mp.get("longitude",0)-ip.get("longitude",0))*111*math.cos(math.radians(ip.get("latitude",0))))**2)
        if d < 10: return "Missile flew past defense point"
    lt = _find_lt_by_keyword(db, scenario.ontology_id, "intercept")
    if lt:
        if db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id).count() > 0:
            return "Interception successful"
    return None


def _eval_score(plan, decision_log, events, tick_count, scenario, db):
    score = {"kill_probability": 0.0, "ammo_used": 0, "time_ticks": tick_count, "decisions_executed": len(decision_log)}
    lt = _find_lt_by_keyword(db, scenario.ontology_id, "intercept")
    has_intercept = False
    if lt:
        links = db.query(Link).filter(Link.ontology_id == scenario.ontology_id, Link.link_type_id == lt.id).all()
        for l in links:
            has_intercept = True
            score["ammo_used"] = int((l.properties or {}).get("count", 1))
    score["kill_probability"] = 1.0 if has_intercept else 0.0
    score["efficiency"] = round(1.0 / (score["ammo_used"] + tick_count * 0.01), 3) if has_intercept else 0.0
    return score
