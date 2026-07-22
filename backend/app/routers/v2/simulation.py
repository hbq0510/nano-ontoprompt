"""推演系统路由 — Scenario CRUD + 推演控制"""

import json
import uuid
import logging
from sqlalchemy import text as sa_text
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.ontology import OntologyProject
from app.models.simulation import Scenario, ScenarioTick, ScenarioEvent
from app.schemas.simulation import (
    ScenarioCreate, ScenarioUpdate, ScenarioOut, ScenarioListItem,
    TickOut, EventOut, SimulationStepResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


# ═══════════════════════════════════════════════════════════════════
# Scenario CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ontology_id}/scenarios")
def list_scenarios(ontology_id: str, db: Session = Depends(get_db)):
    """列出某个本体空间下的所有想定"""
    items = (
        db.query(Scenario)
        .filter(Scenario.ontology_id == ontology_id)
        .order_by(Scenario.updated_at.desc())
        .all()
    )
    result = []
    for s in items:
        result.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "status": s.status,
            "current_tick": s.current_tick,
            "max_ticks": s.max_ticks,
            "participant_count": len(s.participant_instance_ids or []),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return {"data": result}


@router.post("/{ontology_id}/scenarios", status_code=201)
def create_scenario(
    ontology_id: str,
    body: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新想定"""
    # 验证 ontology 存在
    ont = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not ont:
        raise HTTPException(404, "Ontology not found")

    scenario = Scenario(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        name=body.name,
        description=body.description,
        participant_instance_ids=body.participant_instance_ids,
        initial_state=body.initial_state,
        tick_interval_ms=body.tick_interval_ms,
        max_ticks=body.max_ticks,
        stop_condition=body.stop_condition or "max_ticks",
        loop=body.loop,
        created_by=current_user.id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return {"data": ScenarioOut.model_validate(scenario).model_dump()}


@router.get("/{ontology_id}/scenarios/{scenario_id}")
def get_scenario(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    return {"data": ScenarioOut.model_validate(scenario).model_dump()}


@router.put("/{ontology_id}/scenarios/{scenario_id}")
def update_scenario(
    ontology_id: str,
    scenario_id: str,
    body: ScenarioUpdate,
    db: Session = Depends(get_db),
):
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    if scenario.status == "running":
        raise HTTPException(400, "运行中的想定不能编辑")

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(scenario, k, v)
    db.commit()
    db.refresh(scenario)
    return {"data": ScenarioOut.model_validate(scenario).model_dump()}


@router.delete("/{ontology_id}/scenarios/{scenario_id}", status_code=204)
def delete_scenario(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    # 级联删除 ticks & events
    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()
    db.delete(scenario)
    db.commit()


# ═══════════════════════════════════════════════════════════════════
# 推演控制
# ═══════════════════════════════════════════════════════════════════

@router.post("/{ontology_id}/scenarios/{scenario_id}/start")
def start_simulation(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    """开始推演 — 重置 tick 为 0，清除旧数据"""
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    # 清除旧 tick、event 和 Link
    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()
    # 清除该 ontology 下所有场景 Link（避免残留影响下次推演）
    from app.models.v2.object_type import Link
    db.query(Link).filter(Link.ontology_id == ontology_id).delete()

    # 重置到初始状态
    scenario.current_tick = 0
    scenario.status = "running"

    # 按初始状态写入 entity 的 properties
    _apply_initial_state(db, scenario)

    db.commit()

    return {
        "data": {
            "scenario_id": scenario_id,
            "status": "running",
            "current_tick": 0,
        }
    }


@router.post("/{ontology_id}/scenarios/{scenario_id}/tick")
def step_simulation(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    """推进一步 — 执行一帧：规则检查 → 动作执行 → 状态更新 → 保存快照"""
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    if scenario.status not in ("running", "paused"):
        raise HTTPException(400, "想定未在运行中，请先调用 /start")

    if scenario.current_tick >= scenario.max_ticks:
        scenario.status = "finished"
        db.commit()
        return {"data": {"tick": scenario.current_tick, "events": [], "finished": True}}

    next_tick = scenario.current_tick + 1
    events: list[dict] = []

    # ── 1. 对每个参与实例，执行规则 ──
    from app.engine.rule_engine import RuleEngine
    from app.models.v2.object_type import ObjectInstance, Link

    engine = RuleEngine(db, ontology_id)
    participants = (
        db.query(ObjectInstance)
        .filter(ObjectInstance.id.in_(scenario.participant_instance_ids or []))
        .all()
    )

    # 📡 检查该 tick 是否有待处理情报
    from app.routers.v2.intelligence import check_and_apply_intel
    intel_events = check_and_apply_intel(scenario_id, None, next_tick, db)
    for ie in intel_events:
        events.append(ie["desc"] if isinstance(ie, dict) else str(ie))

    fired_rules: list[dict] = []  # (rule_id, instance_id, result)
    property_updates: dict[str, dict] = {}  # instance_id → {prop: value}

    for instance in participants:
        rule_results = engine.check_all(instance)
        for rr in rule_results:
            # 应用规则返回的属性更新（如导弹位置移动）
            if rr.get("properties_update"):
                inst_updates = property_updates.setdefault(instance.id, {})
                inst_updates.update(rr["properties_update"])

            if rr.get("passed"):
                fired_rules.append({
                    "rule_id": rr.get("rule_id"),
                    "rule_name": rr.get("rule_name"),
                    "instance_id": instance.id,
                    "instance_name": instance.name_cn,
                    "result": rr,
                })

    # ── 1.5 应用属性更新到实例 ──
    for inst_id, updates in property_updates.items():
        inst = db.query(ObjectInstance).filter(ObjectInstance.id == inst_id).first()
        if inst:
            inst.properties = {**dict(inst.properties or {}), **updates}
            events.append({
                "tick": next_tick,
                "event_type": "state_change",
                "source_instance_id": inst_id,
                "description": f"实例「{inst.name_cn}」属性更新: {json.dumps(updates, ensure_ascii=False)}",
            })
            db.add(ScenarioEvent(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                tick=next_tick,
                event_type="state_change",
                source_instance_id=inst_id,
                description=events[-1]["description"],
                extra={"updates": updates},
            ))

    # 提交属性更新
    db.flush()

    # ── 2. 对命中规则，执行关联的动作 ──
    from app.engine.action_executor import ActionExecutor

    executor = ActionExecutor(db, ontology_id)

    for fr in fired_rules:
        # 收集当前所有参与者快照作为上下文
        participant_snapshot = _snapshot_instances(db, scenario, participants)
        active_links_snapshot = _snapshot_links(db, ontology_id, scenario)

        context = {
            "instance_id": fr["instance_id"],
            "instance_name": fr["instance_name"],
            "rule_result": fr["result"],
            "tick": next_tick,
            "participants": participant_snapshot,
            "active_links": active_links_snapshot,
            "db": db,  # 动作可以直接操作数据库
            "ontology_id": ontology_id,
            "scenario_id": scenario_id,
        }
        action_results = executor.run_for_rule(fr["rule_id"], context)
        for ar in action_results:
            # 如果动作结果里有 links_to_create，自动创建 Link
            links_created = 0
            if ar.get("links_to_create"):
                links_created = executor._create_links(ar["links_to_create"])

            desc = f"规则「{fr['rule_name']}」命中 → 动作「{ar.get('action_name', '')}」执行: {ar.get('status', '')}"
            if links_created:
                desc += f"，创建了 {links_created} 条边"

            events.append({
                "tick": next_tick,
                "event_type": "action_exec",
                "source_instance_id": fr["instance_id"],
                "description": desc,
                "extra": {
                    "rule_id": fr["rule_id"],
                    "rule_name": fr["rule_name"],
                    "action_id": ar.get("action_id"),
                    "action_name": ar.get("action_name"),
                    "action_result": ar,
                    "links_created": links_created,
                },
            })
            # 记录 DB event
            db.add(ScenarioEvent(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                tick=next_tick,
                event_type="action_exec",
                source_instance_id=fr["instance_id"],
                description=desc,
                extra=events[-1]["extra"],
            ))

    # 记录所有规则检查事件
    for fr in fired_rules:
        desc = f"实例「{fr['instance_name']}」规则「{fr['rule_name']}」通过"
        if fr["result"].get("message"):
            desc += f": {fr['result']['message']}"
        events.append({
            "tick": next_tick,
            "event_type": "rule_check",
            "source_instance_id": fr["instance_id"],
            "description": desc,
        })
        db.add(ScenarioEvent(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            tick=next_tick,
            event_type="rule_check",
            source_instance_id=fr["instance_id"],
            description=desc,
            extra={"rule_id": fr["rule_id"], "rule_name": fr["rule_name"]},
        ))

    # ── 3. 保存当前 tick 的状态快照 ──
    instance_states = _snapshot_instances(db, scenario, participants)
    active_links = _snapshot_links(db, ontology_id, scenario)

    db.add(ScenarioTick(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        tick=next_tick,
        instance_states=instance_states,
        active_links=active_links,
        events=[e["description"] for e in events],
    ))

    # ── 4. 更新推演状态 + 检查停止条件 ──
    scenario.current_tick = next_tick
    if next_tick >= scenario.max_ticks:
        scenario.status = "finished"

    # 检查自定义停止条件
    stop_reason = _check_stop_condition(scenario, active_links, instance_states, db, ontology_id, events)
    if stop_reason:
        scenario.status = "finished"
        events.append({
            "tick": next_tick,
            "event_type": "stop_condition",
            "description": f"停止条件触发: {stop_reason}",
        })
        db.add(ScenarioEvent(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            tick=next_tick,
            event_type="stop_condition",
            description=stop_reason,
        ))

    db.commit()

    finished = scenario.status == "finished"

    return {
        "data": SimulationStepResult(
            tick=next_tick,
            events=events,
            instance_states=instance_states,
            active_links=active_links,
            finished=finished,
        ).model_dump(),
    }


@router.post("/{ontology_id}/scenarios/{scenario_id}/pause")
def pause_simulation(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    """暂停推演"""
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    scenario.status = "paused"
    db.commit()
    return {"data": {"status": "paused", "current_tick": scenario.current_tick}}


@router.post("/{ontology_id}/scenarios/{scenario_id}/resume")
def resume_simulation(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    """继续推演 — 从暂停状态恢复，不清除历史"""
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    if scenario.status != "paused":
        raise HTTPException(400, "只有已暂停的想定才能继续")
    scenario.status = "running"
    db.commit()
    return {"data": {"status": "running", "current_tick": scenario.current_tick}}


@router.post("/{ontology_id}/scenarios/{scenario_id}/reset")
def reset_simulation(ontology_id: str, scenario_id: str, db: Session = Depends(get_db)):
    """重置推演到初始状态"""
    scenario = (
        db.query(Scenario)
        .filter(Scenario.id == scenario_id, Scenario.ontology_id == ontology_id)
        .first()
    )
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()
    scenario.current_tick = 0
    scenario.status = "draft"
    _apply_initial_state(db, scenario)
    db.commit()
    return {"data": {"status": "draft", "current_tick": 0}}


# ═══════════════════════════════════════════════════════════════════
# 时间线查询
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ontology_id}/scenarios/{scenario_id}/timeline")
def get_timeline(
    ontology_id: str,
    scenario_id: str,
    from_tick: int = 0,
    db: Session = Depends(get_db),
):
    """获取推演时间线（所有 tick 快照）"""
    ticks = (
        db.query(ScenarioTick)
        .filter(
            ScenarioTick.scenario_id == scenario_id,
            ScenarioTick.tick >= from_tick,
        )
        .order_by(ScenarioTick.tick)
        .all()
    )
    return {"data": [TickOut.model_validate(t).model_dump() for t in ticks]}


@router.get("/{ontology_id}/scenarios/{scenario_id}/events")
def get_events(
    ontology_id: str,
    scenario_id: str,
    from_tick: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """获取推演事件列表"""
    events = (
        db.query(ScenarioEvent)
        .filter(
            ScenarioEvent.scenario_id == scenario_id,
            ScenarioEvent.tick >= from_tick,
        )
        .order_by(ScenarioEvent.tick, ScenarioEvent.created_at)
        .limit(limit)
        .all()
    )
    return {"data": [EventOut.model_validate(e).model_dump() for e in events]}


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

def _check_stop_condition(scenario, active_links, instance_states, db, ontology_id, events=None):
    """
    检查停止条件是否满足。返回停止原因字符串，None 表示不停止。

    条件类型:
      - max_ticks: 已在外部处理，此处不重复
      - intercept_success: 出现"拦截"类型的 Link
      - intercept_fail: 导弹飞出防御圈（暂无导弹在拦截射程内）或达到 max_ticks
      - target_lost: 雷达丢失所有目标（无探测Link）
    """
    cond = (scenario.stop_condition or "max_ticks").strip()

    if cond == "intercept_success":
        # 检查本 tick 是否创建了拦截 Link
        for evt in (events or []):
            desc = (evt.get("description") or "")
            extra = evt.get("extra") or {}
            if evt.get("event_type") == "action_exec" and "拦截" in desc:
                return f"拦截成功！拦截Link已建立（Tick {scenario.current_tick}）"
        return None

    elif cond == "intercept_fail":
        # 导弹是否还在防御圈内？检查是否有导弹在拦截实例射程内
        from app.models.v2.object_type import ObjectInstance
        import math
        interceptors = [s for s in (instance_states or []) if "拦截" in (s.get("instance_name", "") or "") or "红旗" in (s.get("instance_name", "") or "")]
        missiles = [s for s in (instance_states or []) if "导弹" in (s.get("instance_name", "") or "") or "26B" in (s.get("instance_name", "") or "")]
        if not missiles:
            return "目标已消失（无导弹实体）"
        # 检查是否有拦截Link已经建立
        has_intercept = False
        for link in (active_links or []):
            lt = db.query(LinkType).filter(LinkType.id == link.get("link_type_id", "")).first() if isinstance(link.get("link_type_id"), str) else None
            if lt and ("拦截" in (lt.name_cn or "") or "intercept" in (lt.name_en or "").lower()):
                has_intercept = True
                break
        if not has_intercept and scenario.current_tick >= scenario.max_ticks:
            return "拦截失败：未能在规定时间内拦截目标"

    elif cond == "target_lost":
        # 没有探测Link表示丢失目标
        has_detect = False
        for link in (active_links or []):
            lt_id = link.get("link_type_id", "")
            lt = db.query(LinkType).filter(LinkType.id == lt_id).first() if isinstance(lt_id, str) else None
            if lt and ("探测" in (lt.name_cn or "") or "detect" in (lt.name_en or "").lower()):
                has_detect = True
                break
        if not has_detect and active_links:
            # 有Link但没有探测类型的
            pass
        # 简单判断：如果一个导弹都没有且已经有一些tick了
        missiles = [s for s in (instance_states or []) if "导弹" in (s.get("instance_name", "") or "")]
        if not missiles:
            return "目标丢失：雷达丢失所有导弹目标"

    return None


def _apply_initial_state(db: Session, scenario: Scenario):
    """将想定的初始状态写入各实例的 properties"""
    from app.models.v2.object_type import ObjectInstance

    for init in (scenario.initial_state or []):
        inst_id = init.get("instance_id")
        init_props = init.get("initial_properties", {})
        if not inst_id:
            continue
        inst = db.query(ObjectInstance).filter(ObjectInstance.id == inst_id).first()
        if inst:
            inst.properties = {**dict(inst.properties or {}), **init_props}


def _snapshot_instances(db: Session, scenario: Scenario, participants) -> list[dict]:
    """拍下当前所有参与实例的状态"""
    snapshots = []
    for inst in participants:
        snapshots.append({
            "instance_id": inst.id,
            "instance_name": inst.name_cn,
            "object_type_id": inst.object_type_id,
            "properties": dict(inst.properties or {}),
        })
    return snapshots


def _snapshot_links(db: Session, ontology_id: str, scenario: Scenario) -> list[dict]:
    """拍下当前所有活跃的 Link"""
    from app.models.v2.object_type import Link

    participant_ids = set(scenario.participant_instance_ids or [])
    links = (
        db.query(Link)
        .filter(Link.ontology_id == ontology_id)
        .all()
    )
    result = []
    for link in links:
        # 只要 Link 的任一端是参与者就纳入快照
        if link.source_instance_id in participant_ids or link.target_instance_id in participant_ids:
            result.append({
                "link_id": link.id,
                "link_type_id": link.link_type_id,
                "source_instance_id": link.source_instance_id,
                "target_instance_id": link.target_instance_id,
                "properties": dict(link.properties or {}),
            })
    return result
