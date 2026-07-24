"""方案系统路由 — Plan CRUD + 执行 + 对比 + LLM 生成（防空反导版）"""

import json, uuid, math, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.simulation import Scenario, ScenarioTick, ScenarioEvent
from app.models.plan import Plan, PlanRun
from app.models.v2.object_type import ObjectInstance, Link, LinkType, ObjectType
from app.schemas.plan import PlanCreate, PlanUpdate, PlanOut, PlanListItem, PlanRunOut, GenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Helpers: 通过 ObjectType 识别参与者（避免 name_cn / 属性名匹配问题）──

def _load_ot_map(db, ontology_id):
    return {ot.id: ot.name_en or ot.name_cn or "" for ot in db.query(ObjectType).filter(ObjectType.ontology_id == ontology_id).all()}

def _find_by_type(participants, ot_map, type_names):
    return next((p for p in participants if ot_map.get(p.object_type_id, "") in type_names), None)

def _find_all_by_type(participants, ot_map, type_names):
    return [p for p in participants if ot_map.get(p.object_type_id, "") in type_names]

def _find_lt_by_keyword(db, ontology_id, keyword):
    """查找包含特定关键词的 LinkType"""
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
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    decisions = [d.model_dump() for d in body.decisions]
    plan = Plan(id=str(uuid.uuid4()), scenario_id=scenario_id, name=body.name,
                description=body.description, decisions=decisions,
                source=body.source or "manual", template_id=body.template_id, created_by=current_user.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
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
    if not plan:
        raise HTTPException(404, "Plan not found")
    return {"data": PlanOut.model_validate(plan).model_dump()}


@router.put("/scenarios/{scenario_id}/plans/{plan_id}")
def update_plan(scenario_id: str, plan_id: str, body: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan:
        raise HTTPException(404)
    if body.name is not None:
        plan.name = body.name
    if body.description is not None:
        plan.description = body.description
    if body.decisions is not None:
        plan.decisions = [d.model_dump() for d in body.decisions]
    if body.status is not None:
        plan.status = body.status
    if body.score is not None:
        plan.score = body.score
    db.commit()
    db.refresh(plan)
    return {"data": PlanOut.model_validate(plan).model_dump()}


@router.delete("/scenarios/{scenario_id}/plans/{plan_id}", status_code=204)
def delete_plan(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan:
        raise HTTPException(404)
    db.query(PlanRun).filter(PlanRun.plan_id == plan_id).delete()
    db.delete(plan)
    db.commit()


# ═══════════════════════════════════════════════════════════════════
# LLM 方案生成
# ═══════════════════════════════════════════════════════════════════

@router.post("/scenarios/{scenario_id}/plans/generate")
def generate_plans(scenario_id: str, body: GenerateRequest, db: Session = Depends(get_db)):
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(404)

    instances = db.query(ObjectInstance).filter(ObjectInstance.id.in_(scenario.participant_instance_ids or [])).all()
    constraints = _build_constraints(scenario, instances, db)

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
        db.add(plan)
        db.commit()
        db.refresh(plan)
        saved.append(PlanOut.model_validate(plan).model_dump())
    return {"data": saved}


# ═══════════════════════════════════════════════════════════════════
# 方案执行 — 统一调用 _simulate_tick 共享推演核心
# ═══════════════════════════════════════════════════════════════════

@router.post("/scenarios/{scenario_id}/plans/{plan_id}/run")
def run_plan(scenario_id: str, plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.scenario_id == scenario_id).first()
    if not plan:
        raise HTTPException(404)
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(404)

    # 导入共享的 tick 核心
    from app.routers.v2.simulation import _simulate_tick, _haversine, _apply_initial_state

    # 重置情报状态
    from app.models.intelligence import Intelligence as IntelModel
    for it in db.query(IntelModel).filter(IntelModel.scenario_id == scenario_id).all():
        if it.status == "applied":
            it.status = "ready"
    db.flush()

    # 清理旧数据
    db.query(Link).filter(Link.ontology_id == scenario.ontology_id).delete()
    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()

    # 删除情报创建的额外实例
    original_ids = set(scenario.participant_instance_ids or [])
    for extra in db.query(ObjectInstance).filter(
        ObjectInstance.ontology_id == scenario.ontology_id,
        ~ObjectInstance.id.in_(original_ids)
    ).all():
        db.delete(extra)
    db.flush()

    # 重置参与者到初始状态
    _apply_initial_state(db, scenario)
    db.flush()

    run = PlanRun(id=str(uuid.uuid4()), plan_id=plan_id, scenario_id=scenario_id,
                  status="running", started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)

    scenario.status = "running"
    scenario.current_tick = 0
    db.commit()

    decisions = plan.decisions or []
    decision_idx = 0
    max_ticks = scenario.max_ticks or 50
    tick_count = 0
    decision_log: list[dict] = []
    all_events: list[dict] = []

    # 记录初始弹药快照（用于评分）
    participants = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()
    ot_map = _load_ot_map(db, scenario.ontology_id)
    initial_ammo_map = {}
    for p in participants:
        if ot_map.get(p.object_type_id, "") in ("MidRangeInterceptor", "CIWS"):
            initial_ammo_map[p.id] = int((p.properties or {}).get("ammo_count", 0))

    for tick in range(1, max_ticks + 1):
        tick_count = tick

        # 检查并执行决策（在 tick 前修改属性，影响本轮推演）
        while decision_idx < len(decisions):
            d = decisions[decision_idx]
            triggered = _check_trigger(d, db, scenario, tick, decision_log, ot_map)
            if triggered:
                _apply_decision_effect(d, db, scenario, ot_map)
                decision_log.append({"tick": tick, "decision": d, "status": "triggered"})
                all_events.append({"tick": tick, "type": "decision",
                                   "desc": f"决策触发: {d.get('action')} [{d.get('target', '')}]"})
                decision_idx += 1
            else:
                break

        # 运行 tick（共享核心逻辑）
        tick_events, instance_states, active_links, _ = _simulate_tick(db, scenario, scenario.ontology_id, tick, auto_fire=False)
        all_events.extend(tick_events)
        scenario.current_tick = tick

        # 保存 tick 快照（供前端地图显示）
        db.add(ScenarioTick(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            tick=tick,
            instance_states=instance_states,
            active_links=active_links,
            events=[e.get("description", str(e)) for e in tick_events],
        ))
        # 保存事件到 ScenarioEvent
        for e in tick_events:
            db.add(ScenarioEvent(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                tick=tick,
                event_type=e.get("event_type", "unknown"),
                source_instance_id=e.get("source_instance_id"),
                target_instance_id=e.get("target_instance_id"),
                description=e.get("description", ""),
                extra=e.get("extra", {}),
            ))

        db.flush()
        # 检查停止
        stop_reason = _eval_stop(scenario, decisions, decision_idx, db, ot_map)
        if stop_reason:
            all_events.append({"tick": tick, "type": "stop", "desc": stop_reason})
            break

    # 评分
    score = _eval_score(plan, decision_log, all_events, tick_count, scenario, db, ot_map, initial_ammo_map)
    plan.status = "evaluated"
    plan.score = score
    run.status = "success"
    run.tick_count = tick_count
    run.result = score
    run.decision_log = decision_log
    run.events = all_events
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
    if not plan:
        raise HTTPException(404)
    plan.source = "template"
    plan.template_id = f"tpl_{plan.id[:8]}"
    db.commit()
    return {"data": PlanOut.model_validate(plan).model_dump()}


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _build_constraints(scenario, instances, db):
    c = {"participants": [], "scenario": {"name": scenario.name, "max_ticks": scenario.max_ticks}}
    ot_map = _load_ot_map(db, scenario.ontology_id)
    for inst in instances:
        props = dict(inst.properties or {})
        info = {"id": inst.id, "name": inst.name_cn, "props": props}
        ot_name = ot_map.get(inst.object_type_id, "")
        if ot_name in ("BallisticMissile", "CruiseMissile", "Decoy"):
            c.setdefault("missiles", []).append(info)
        elif ot_name == "EarlyWarningRadar":
            c.setdefault("sensors", []).append(info)
        elif ot_name in ("MidRangeInterceptor", "CIWS"):
            c.setdefault("interceptors", []).append(info)
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
        if not call_kwargs:
            raise RuntimeError("No LLM config")
        # 从 ontology 获取实际类型名，用于 prompt 指引
        ot_map = _load_ot_map(db, scenario.ontology_id)
        missile_types = [n for n in ot_map.values() if n in ("BallisticMissile", "CruiseMissile", "Decoy")] or ["BallisticMissile"]
        interceptor_types = [n for n in ot_map.values() if n in ("MidRangeInterceptor", "CIWS")] or ["MidRangeInterceptor"]
        sensor_types = [n for n in ot_map.values() if n == "EarlyWarningRadar"] or ["EarlyWarningRadar"]

        prompt = f"""请为以下防空拦截想定生成{count}种不同的拦截方案。请用中文回答。

想定信息: {json.dumps(constraints['scenario'], ensure_ascii=False)}
可用资源: {json.dumps(constraints, ensure_ascii=False)[:1500]}
策略偏好: {strategy}

重要：只能使用以下触发条件:
- "distance<N" (威胁距拦截系统小于N公里, 例如"distance<400")
- "detected" (传感器已探测到威胁)
- "intercept_success" (拦截成功)
- "intercept_failed" (拦截失败)
- "tick>=N" (推演进行到第N帧)

支持的动作: launch(发射拦截), track(跟踪), stop(停止)
可用实体类型: 拦截系统={interceptor_types}, 传感器={sensor_types}, 威胁={missile_types}

输出必须是严格JSON:
{{"plans":[{{"name":"方案名称(中文)","description":"方案描述(中文)","decisions":[{{"trigger":"distance<400","target":"{interceptor_types[0]}","action":"launch","params":{{"count":2,"mode":"salvo"}}}}]}}]}}
decisions数组不能为空！只返回JSON, 不要其他文字。"""
        raw = llm_service._call_llm(**call_kwargs, messages=[{"role": "system", "content": "You are a military simulation expert. Output JSON."}, {"role": "user", "content": prompt}])
        data = json.loads(raw) if isinstance(raw, str) else raw
        return (data.get("plans", []) if isinstance(data, dict) else data)[:count]
    except Exception as e:
        logger.warning(f"LLM failed: {e}")
        raise


def _rule_generate(constraints, count, strategy):
    templates = [
        {"name": "齐射保守方案", "description": "双弹齐射，提高杀伤概率",
         "decisions": [
             {"trigger": "distance<400", "target": "interceptor", "action": "launch", "params": {"count": 2, "mode": "salvo"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "单发经济方案", "description": "先打一发，失败后再补射",
         "decisions": [
             {"trigger": "distance<300", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_failed", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "探测优先方案", "description": "先建立稳定跟踪，再近距齐射",
         "decisions": [
             {"trigger": "detected", "target": "radar", "action": "track", "params": {"mode": "continuous"}},
             {"trigger": "distance<350", "target": "interceptor", "action": "launch", "params": {"count": 2, "mode": "rapid"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
        {"name": "远程拦截方案", "description": "最远距离发射，争取更多拦截窗口",
         "decisions": [
             {"trigger": "distance<600", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "long_range"}},
             {"trigger": "intercept_failed", "target": "interceptor", "action": "launch", "params": {"count": 1, "mode": "single"}},
             {"trigger": "intercept_success", "target": "", "action": "stop", "params": {}}]},
    ]
    if strategy == "conservative":
        templates = templates[:2]
    elif strategy == "aggressive":
        templates = [templates[3], templates[0]]
    return templates[:count]


def _check_trigger(decision, db, scenario, tick, log, ot_map):
    trigger = (decision.get("trigger") or "").strip()
    if not trigger:
        return False

    participants = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()

    if trigger.startswith("distance<"):
        threshold = float(trigger.split("<")[1])
        interceptor = _find_by_type(participants, ot_map, {"MidRangeInterceptor", "CIWS"})
        missiles = _find_all_by_type(participants, ot_map, {"BallisticMissile", "CruiseMissile", "Decoy"})
        if interceptor and missiles:
            ip = interceptor.properties or {}
            for m in missiles:
                mp = m.properties or {}
                d = _haversine_simple(ip.get("latitude", 0), ip.get("longitude", 0),
                                      mp.get("latitude", 0), mp.get("longitude", 0))
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
            if l.get("decision", {}).get("action") == "stop":
                return True
        return False

    if trigger == "intercept_failed":
        # 检查是否有火力通道 miss（计划外拦截任务失败）
        fire_lt = _find_lt_by_keyword(db, scenario.ontology_id, "fire")
        if fire_lt:
            missed = db.query(Link).filter(
                Link.ontology_id == scenario.ontology_id,
                Link.link_type_id == fire_lt.id,
            ).all()
            for l in missed:
                if (l.properties or {}).get("status") == "miss":
                    return True
        return False

    if trigger.startswith("tick>="):
        return tick >= int(trigger.split(">=")[1])

    return False


def _apply_decision_effect(decision, db, scenario, ot_map):
    """决策触发时：创建火力通道 Link（真正控制拦截）"""
    action = (decision.get("action") or "").strip()
    participants = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()

    if action == "launch":
        interceptor = _find_by_type(participants, ot_map, {"MidRangeInterceptor", "CIWS"})
        missiles = _find_all_by_type(participants, ot_map, {"BallisticMissile", "CruiseMissile", "Decoy"})
        if not interceptor or not missiles:
            return

        ip = interceptor.properties or {}
        i_lat, i_lon = ip.get("latitude", 0), ip.get("longitude", 0)
        i_range = ip.get("max_range_km", 0)

        # 找最近的、未被摧毁的威胁（不做射程检查：方案 trigger 已控制发射时机）
        alive = [m for m in missiles if (m.properties or {}).get("status") != "destroyed"]
        if not alive:
            return
        target_list = []
        for m in alive:
            mp = m.properties or {}
            d = _haversine_simple(i_lat, i_lon, mp.get("latitude", 0), mp.get("longitude", 0))
            target_list.append((d, m))
        target_list.sort(key=lambda x: x[0])
        dist_km, target = target_list[0]

        # 方案参数
        count = int((decision.get("params") or {}).get("count", 1))
        mode = (decision.get("params") or {}).get("mode", "single")

        # 计算杀伤概率（距离越近概率越高，齐射翻倍）
        base_pk = ip.get("kill_prob_single", 0.7)
        p_kill = min(0.98, base_pk * (1 + 0.5 * (i_range - dist_km) / max(i_range, 1)))
        if count > 1:
            p_kill = 1 - (1 - p_kill) ** count  # 齐射：至少一发命中的概率

        # 时间估算（秒 → 毫秒）
        speed_ms = ip.get("speed_mach", 6) * 343
        rel_speed = speed_ms + (target.properties or {}).get("speed_mach", 5) * 343
        time_ms = int(dist_km * 1000 / max(rel_speed, 1))

        # 创建火力通道 Link
        fire_lt = _find_lt_by_keyword(db, scenario.ontology_id, "fire")
        if fire_lt:
            existing = db.query(Link).filter(
                Link.ontology_id == scenario.ontology_id,
                Link.link_type_id == fire_lt.id,
                Link.source_instance_id == interceptor.id,
                Link.target_instance_id == target.id,
            ).first()
            if not existing:
                db.add(Link(
                    id=str(uuid.uuid4()),
                    ontology_id=scenario.ontology_id,
                    link_type_id=fire_lt.id,
                    source_instance_id=interceptor.id,
                    target_instance_id=target.id,
                    properties={
                        "status": "guiding",
                        "time_to_intercept_ms": time_ms,
                        "salvo_count": count,
                        "p_kill": round(p_kill, 3),
                        "mode": mode,
                        "decision_made": True,
                    },
                ))
                # 扣除弹药
                i_props = dict(interceptor.properties or {})
                i_props["ammo_count"] = max(0, i_props.get("ammo_count", 0) - count)
                interceptor.properties = i_props

    elif action == "track":
        for p in participants:
            if ot_map.get(p.object_type_id, "") == "EarlyWarningRadar":
                props = dict(p.properties or {})
                props["max_range_km"] = min(600, props.get("max_range_km", 0) * 1.1)  # 跟踪增强探测
                p.properties = props
                break


def _eval_stop(scenario, decisions, decision_idx, db, ot_map):
    if decision_idx >= len(decisions):
        return "All decisions executed"

    participants = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()
    missiles = _find_all_by_type(participants, ot_map, {"BallisticMissile", "CruiseMissile", "Decoy"})
    hvas = _find_all_by_type(participants, ot_map, {"HighValueAsset"})

    # 所有威胁被摧毁 → 停止
    active_missiles = [m for m in missiles if (m.properties or {}).get("status") != "destroyed"]
    if not active_missiles:
        return "所有威胁已被拦截"

    # 威胁到达 HVA → 停止
    for hva in hvas:
        h_lat = (hva.properties or {}).get("latitude", 0)
        h_lon = (hva.properties or {}).get("longitude", 0)
        for m in active_missiles:
            m_lat = (m.properties or {}).get("latitude", 0)
            m_lon = (m.properties or {}).get("longitude", 0)
            if _haversine_simple(h_lat, h_lon, m_lat, m_lon) < 5:
                return f"威胁「{m.name_cn}」突防成功"

    return None


def _eval_score(plan, decision_log, events, tick_count, scenario, db, ot_map, initial_ammo_map=None):
    """基于推演结果计算评分"""
    participants = db.query(ObjectInstance).filter(ObjectInstance.ontology_id == scenario.ontology_id).all()

    # 统计威胁
    threats = _find_all_by_type(participants, ot_map, {"BallisticMissile", "CruiseMissile", "Decoy"})
    destroyed = sum(1 for t in threats if (t.properties or {}).get("status") == "destroyed")
    total_threats = len(threats)

    # 统计弹药消耗（优先使用运行前记录的快照）
    interceptors = _find_all_by_type(participants, ot_map, {"MidRangeInterceptor", "CIWS"})
    remaining_ammo = sum(int((p.properties or {}).get("ammo_count", 0)) for p in interceptors)
    if initial_ammo_map:
        initial_ammo = sum(initial_ammo_map.values())
    else:
        # 回退：从 initial_state 中提取
        initial_ammo = 0
        for init in (scenario.initial_state or []):
            init_props = init.get("initial_properties", {})
            if init_props.get("ammo_count"):
                initial_ammo += int(init_props["ammo_count"])
    ammo_used = max(0, initial_ammo - remaining_ammo)

    # HVA 生存状态
    hva_ok = True
    hvas = _find_all_by_type(participants, ot_map, {"HighValueAsset"})
    for hva in hvas:
        h_lat = (hva.properties or {}).get("latitude", 0)
        h_lon = (hva.properties or {}).get("longitude", 0)
        for t in threats:
            if (t.properties or {}).get("status") == "destroyed":
                continue
            t_lat = (t.properties or {}).get("latitude", 0)
            t_lon = (t.properties or {}).get("longitude", 0)
            if _haversine_simple(h_lat, h_lon, t_lat, t_lon) < 5:
                hva_ok = False
                break
        if not hva_ok:
            break

    # 命中 / 未命中事件数
    hit_count = sum(1 for e in events if e.get("event_type") == "action_exec" and "命中" in (e.get("description") or ""))
    miss_count = sum(1 for e in events if e.get("event_type") == "action_exec" and "未命中" in (e.get("description") or ""))

    kill_prob = round(destroyed / total_threats, 3) if total_threats > 0 else 0.0
    efficiency = round(kill_prob / (ammo_used + 1) * 100, 2) if ammo_used >= 0 else 0.0

    return {
        "kill_probability": kill_prob,
        "ammo_used": ammo_used,
        "time_ticks": tick_count,
        "decisions_executed": len(decision_log),
        "threats_destroyed": destroyed,
        "threats_total": total_threats,
        "hva_survived": hva_ok,
        "hits": hit_count,
        "misses": miss_count,
        "efficiency": efficiency,
    }


def _haversine_simple(lat1, lon1, lat2, lon2):
    """简化距离计算（km）—— plans 内部用，避免循环导入"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c
