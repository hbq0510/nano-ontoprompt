"""推演系统路由 — Scenario CRUD + 推演控制"""

import json
import math
import random
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
        design_params_map=body.design_params_map,
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

    db.query(ScenarioTick).filter(ScenarioTick.scenario_id == scenario_id).delete()
    db.query(ScenarioEvent).filter(ScenarioEvent.scenario_id == scenario_id).delete()
    from app.models.v2.object_type import Link
    db.query(Link).filter(Link.ontology_id == ontology_id).delete()

    scenario.current_tick = 0
    scenario.status = "running"
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
    """推进一步 — 调用共享的 _simulate_tick 核心"""
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

    # 运行共享核心
    events, instance_states, active_links, destroyed_threat_ids = _simulate_tick(
        db, scenario, ontology_id, next_tick
    )

    # 保存 tick 快照
    db.add(ScenarioTick(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        tick=next_tick,
        instance_states=instance_states,
        active_links=active_links,
        events=[e.get("description", str(e)) for e in events],
    ))

    # 保存事件到 ScenarioEvent 表（供前端事件面板显示）
    for e in events:
        db.add(ScenarioEvent(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            tick=next_tick,
            event_type=e.get("event_type", "unknown"),
            source_instance_id=e.get("source_instance_id"),
            target_instance_id=e.get("target_instance_id"),
            description=e.get("description", ""),
            extra=e.get("extra", {}),
        ))

    scenario.current_tick = next_tick
    if next_tick >= scenario.max_ticks:
        scenario.status = "finished"

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
# 共享推演核心 — 物理推进 → 探测 → 火力分配 → 拦截执行 → 威胁评估
# ═══════════════════════════════════════════════════════════════════

def _simulate_tick(db, scenario, ontology_id, tick, auto_fire=True):
    """
    执行单个 tick 的推演逻辑。
    auto_fire=False 时跳过自动火力分配（方案系统自己控制发射时机和数量）。
    返回: (events, instance_states, active_links, destroyed_threat_ids)
    """
    from app.models.v2.object_type import ObjectInstance, Link, LinkType, ObjectType

    events = []
    tick_interval = scenario.tick_interval_ms or 1000

    # ── 加载参与者与类型映射 ──
    participants = (
        db.query(ObjectInstance)
        .filter(ObjectInstance.id.in_(scenario.participant_instance_ids or []))
        .all()
    )
    ot_map = {ot.id: ot.name_en or ot.name_cn or "" for ot in db.query(ObjectType).filter(ObjectType.ontology_id == ontology_id).all()}

    # 按类型分组
    threats = []
    interceptors = []
    sensors = []
    hvas = []
    for p in participants:
        ot_name = ot_map.get(p.object_type_id, "")
        if ot_name in ("BallisticMissile", "CruiseMissile", "Decoy"):
            threats.append(p)
        elif ot_name in ("MidRangeInterceptor", "CIWS"):
            interceptors.append(p)
        elif ot_name == "EarlyWarningRadar":
            sensors.append(p)
        elif ot_name == "HighValueAsset":
            hvas.append(p)

    # ── 1. 物理推进（只移动导弹/诱饵） ──
    for t in threats:
        props = dict(t.properties or {})
        speed_mach = props.get("speed_mach", 0)
        speed = speed_mach * 343  # 马赫 → m/s
        if speed:
            lat = props.get("latitude", 0)
            lon = props.get("longitude", 0)
            heading = props.get("direction_deg", 0)
            # 简化的平面位移（小距离近似）
            d_m = speed * (tick_interval / 1000.0)
            d_lat = d_m / 111320.0 * math.cos(math.radians(heading))
            d_lon = d_m / (111320.0 * math.cos(math.radians(lat))) * math.sin(math.radians(heading))
            props["latitude"] = lat + d_lat
            props["longitude"] = lon + d_lon
            t.properties = props
            events.append({
                "tick": tick, "event_type": "state_change",
                "source_instance_id": t.id,
                "description": f"{t.name_cn} 移动到 ({props['latitude']:.6f}, {props['longitude']:.6f})",
                "extra": {"new_pos": (props["latitude"], props["longitude"])},
            })

    # ── 2. 探测（基于距离与雷达 range） ──
    detect_lt = _find_lt(db, ontology_id, "detect")
    for sensor in sensors:
        s_props = dict(sensor.properties or {})
        s_lat = s_props.get("latitude", 0)
        s_lon = s_props.get("longitude", 0)
        s_range = s_props.get("max_range_km", 0) * 1000  # 米

        for t in threats:
            t_props = dict(t.properties or {})
            t_lat = t_props.get("latitude", 0)
            t_lon = t_props.get("longitude", 0)
            dist = _haversine(s_lat, s_lon, t_lat, t_lon)

            if dist <= s_range:
                # 检查是否已存在探测链接
                existing = db.query(Link).filter(
                    Link.ontology_id == ontology_id,
                    Link.link_type_id == detect_lt.id if detect_lt else "",
                    Link.source_instance_id == sensor.id,
                    Link.target_instance_id == t.id,
                ).first() if detect_lt else None

                if not existing:
                    db.add(Link(
                        id=str(uuid.uuid4()),
                        ontology_id=ontology_id,
                        link_type_id=detect_lt.id,
                        source_instance_id=sensor.id,
                        target_instance_id=t.id,
                        properties={"distance_m": dist, "detected_at_tick": tick},
                    ))
                    events.append({
                        "tick": tick, "event_type": "action_exec",
                        "source_instance_id": sensor.id,
                        "target_instance_id": t.id,
                        "description": f"{sensor.name_cn} 探测到目标 {t.name_cn}，距离 {dist/1000:.1f} km",
                        "extra": {"distance_m": dist},
                    })

    db.flush()

    # ── 2.5. 威胁评估（威胁 → HVA 的 THREAT_FLOW）──
    threat_lt = _find_lt(db, ontology_id, "threat")
    if threat_lt:
        for t in threats:
            t_props = dict(t.properties or {})
            if t_props.get("status") == "destroyed":
                continue
            t_lat, t_lon = t_props.get("latitude", 0), t_props.get("longitude", 0)
            for hva in hvas:
                h_lat, h_lon = (hva.properties or {}).get("latitude", 0), (hva.properties or {}).get("longitude", 0)
                dist = _haversine(t_lat, t_lon, h_lat, h_lon)
                if dist < 500000:  # 500km 内视为有威胁
                    existing = db.query(Link).filter(
                        Link.ontology_id == ontology_id,
                        Link.link_type_id == threat_lt.id,
                        Link.source_instance_id == t.id,
                        Link.target_instance_id == hva.id,
                    ).first()
                    if not existing:
                        db.add(Link(
                            id=str(uuid.uuid4()),
                            ontology_id=ontology_id,
                            link_type_id=threat_lt.id,
                            source_instance_id=t.id,
                            target_instance_id=hva.id,
                            properties={"distance_m": dist, "threat_level": "high" if dist < 200000 else "medium"},
                        ))
                        events.append({
                            "tick": tick, "event_type": "action_exec",
                            "source_instance_id": t.id, "target_instance_id": hva.id,
                            "description": f"威胁评估: {t.name_cn} 威胁 {hva.name_cn}，距离 {dist/1000:.1f} km",
                            "extra": {"distance_m": dist},
                        })
    db.flush()

    # ── 3. 火力分配 ──
    fire_lt = _find_lt(db, ontology_id, "fire")
    # 收集已锁定目标（已有探测链接）
    locked_threats = []
    for t in threats:
        if detect_lt:
            det = db.query(Link).filter(
                Link.ontology_id == ontology_id,
                Link.link_type_id == detect_lt.id,
                Link.target_instance_id == t.id,
            ).first()
            if det:
                locked_threats.append(t)

    # 收集已有火力通道覆盖的目标（避免重复分配）
    covered_target_ids = set()
    if fire_lt:
        for fl in db.query(Link).filter(
            Link.ontology_id == ontology_id,
            Link.link_type_id == fire_lt.id,
        ).all():
            if (fl.properties or {}).get("status") in ("guiding", "pending"):
                covered_target_ids.add(fl.target_instance_id)

    for interceptor in interceptors:
        i_props = dict(interceptor.properties or {})
        ammo = int(i_props.get("ammo_count", 0))
        if ammo <= 0:
            continue
        i_lat = i_props.get("latitude", 0)
        i_lon = i_props.get("longitude", 0)
        i_range = i_props.get("max_range_km", 0) * 1000

        # 简单分配：为每个尚未覆盖且未摧毁的目标分配一枚拦截弹
        for threat in locked_threats:
            if threat.id in covered_target_ids:
                continue
            t_props = dict(threat.properties or {})
            if t_props.get("status") == "destroyed":
                continue
            t_lat = t_props.get("latitude", 0)
        for threat in locked_threats:
            if threat.id in covered_target_ids:
                continue
            t_props = dict(threat.properties or {})
            t_lat = t_props.get("latitude", 0)
            t_lon = t_props.get("longitude", 0)
            dist = _haversine(i_lat, i_lon, t_lat, t_lon)
            if dist > i_range:
                continue

            # 计算飞行时间（考虑拦截弹与导弹相向而行的相对速度）
            threat_speed_km_s = (t_props.get("speed_mach", 0) * 343) / 1000.0
            relative_speed = 3.0 + threat_speed_km_s  # 拦截弹 3km/s + 导弹速度
            time_to_intercept = int(dist / 1000.0 / relative_speed * 1000)  # 毫秒
            salvo = min(ammo, 2)  # 一次最多分配 2 发

            if auto_fire:
                # 扣除弹药（立即扣除，避免重复）
                i_props["ammo_count"] = max(0, ammo - salvo)
                interceptor.properties = i_props
                ammo = i_props["ammo_count"]

                # 创建火力通道（guiding 状态）
                db.add(Link(
                    id=str(uuid.uuid4()),
                    ontology_id=ontology_id,
                    link_type_id=fire_lt.id if fire_lt else "",
                    source_instance_id=interceptor.id,
                    target_instance_id=threat.id,
                    properties={
                        "status": "guiding",
                        "time_to_intercept_ms": time_to_intercept,
                        "salvo_count": salvo,
                        "p_kill": 0.5 + min(0.4, 200000 / max(dist, 1000)),
                    },
                ))
                covered_target_ids.add(threat.id)
                events.append({
                    "tick": tick, "event_type": "action_exec",
                    "source_instance_id": interceptor.id,
                    "target_instance_id": threat.id,
                    "description": f"{interceptor.name_cn} 分配火力通道拦截 {threat.name_cn}（飞行时间 {time_to_intercept} ms）",
                    "extra": {"salvo": salvo, "time_to_intercept_ms": time_to_intercept},
                })

                if ammo <= 0:
                    break

    db.flush()

    # ── 4. 更新飞行中的拦截弹（guiding → pending） ──
    if fire_lt:
        for fl in db.query(Link).filter(
            Link.ontology_id == ontology_id,
            Link.link_type_id == fire_lt.id,
        ).all():
            fp = dict(fl.properties or {})
            if fp.get("status") == "guiding":
                remaining = fp.get("time_to_intercept_ms", 0) - tick_interval
                fp["time_to_intercept_ms"] = max(0, remaining)
                if fp["time_to_intercept_ms"] <= 0:
                    fp["status"] = "pending"
                fl.properties = fp

    db.flush()

    # ── 5. 拦截执行（pending → hit/miss） ──
    destroyed_threat_ids = set()
    if fire_lt:
        for fl in db.query(Link).filter(
            Link.ontology_id == ontology_id,
            Link.link_type_id == fire_lt.id,
        ).all():
            f_props = dict(fl.properties or {})
            if f_props.get("status") == "pending":
                p_kill = f_props.get("p_kill", 0.5)
                hit = random.random() < p_kill
                if hit:
                    f_props["status"] = "hit"
                    destroyed_threat_ids.add(fl.target_instance_id)
                    # 更新目标实例状态为已摧毁
                    target_inst = db.query(ObjectInstance).filter(ObjectInstance.id == fl.target_instance_id).first()
                    if target_inst:
                        tp = dict(target_inst.properties or {})
                        tp["status"] = "destroyed"
                        target_inst.properties = tp
                    events.append({
                        "tick": tick, "event_type": "action_exec",
                        "source_instance_id": fl.source_instance_id,
                        "target_instance_id": fl.target_instance_id,
                        "description": "拦截命中！目标已摧毁",
                        "extra": {"p_kill": p_kill, "result": "hit"},
                    })
                else:
                    f_props["status"] = "miss"
                    events.append({
                        "tick": tick, "event_type": "action_exec",
                        "source_instance_id": fl.source_instance_id,
                        "target_instance_id": fl.target_instance_id,
                        "description": "拦截未命中",
                        "extra": {"p_kill": p_kill, "result": "miss"},
                    })
                fl.properties = f_props

    # ── 6. 威胁评估：导弹到达 HVA？ ──
    for t in threats:
        if t.id in destroyed_threat_ids:
            continue
        t_props = dict(t.properties or {})
        t_lat = t_props.get("latitude", 0)
        t_lon = t_props.get("longitude", 0)
        for hva in hvas:
            h_props = dict(hva.properties or {})
            h_lat = h_props.get("latitude", 0)
            h_lon = h_props.get("longitude", 0)
            dist = _haversine(t_lat, t_lon, h_lat, h_lon)
            if dist < 500:  # 500m 内视为命中
                destroyed_threat_ids.add(t.id)
                t_props["status"] = "destroyed"
                t.properties = t_props
                events.append({
                    "tick": tick, "event_type": "action_exec",
                    "source_instance_id": t.id,
                    "target_instance_id": hva.id,
                    "description": f"导弹 {t.name_cn} 命中高价值目标 {hva.name_cn}！",
                    "extra": {"distance_m": dist},
                })
                break

    db.flush()

    # ── 7. 保存快照 ──
    instance_states = _snapshot_instances(db, scenario, participants)
    active_links = _snapshot_links(db, ontology_id, scenario)

    return events, instance_states, active_links, destroyed_threat_ids


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

def _haversine(lat1, lon1, lat2, lon2):
    """计算两点间距离（米）"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_lt(db, ontology_id, keyword):
    """查找包含特定关键词的 LinkType"""
    from app.models.v2.object_type import LinkType
    lts = db.query(LinkType).filter(LinkType.ontology_id == ontology_id).all()
    kw = keyword.lower()
    for lt in lts:
        if kw in (lt.name_en or "").lower() or kw in (lt.name_cn or "").lower():
            return lt
    return None


def _apply_initial_state(db, scenario):
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


def _snapshot_instances(db, scenario, participants):
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


def _snapshot_links(db, ontology_id, scenario):
    """拍下当前所有活跃的 Link"""
    from app.models.v2.object_type import Link, LinkType
    participant_ids = set(scenario.participant_instance_ids or [])
    links = db.query(Link).filter(Link.ontology_id == ontology_id).all()
    lt_cache = {}
    result = []
    for link in links:
        if link.source_instance_id in participant_ids or link.target_instance_id in participant_ids:
            if link.link_type_id not in lt_cache:
                lt = db.query(LinkType).filter(LinkType.id == link.link_type_id).first()
                lt_cache[link.link_type_id] = (lt.name_en or lt.name_cn or "") if lt else ""
            result.append({
                "link_id": link.id,
                "link_type_id": link.link_type_id,
                "link_type_name": lt_cache[link.link_type_id],
                "source_instance_id": link.source_instance_id,
                "target_instance_id": link.target_instance_id,
                "properties": dict(link.properties or {}),
            })
    return result


def _check_stop_condition(scenario, active_links, instance_states, db, ontology_id, events=None):
    """检查停止条件。返回停止原因字符串，None 表示不停止。"""
    cond = (scenario.stop_condition or "max_ticks").strip()

    if cond == "intercept_success":
        for evt in (events or []):
            desc = (evt.get("description") or "")
            if evt.get("event_type") == "action_exec" and "拦截命中" in desc:
                return f"拦截成功！（Tick {scenario.current_tick}）"
        return None

    elif cond == "intercept_fail":
        has_pending = False
        for link in (active_links or []):
            props = link.get("properties", {})
            if props.get("status") in ("guiding", "pending"):
                has_pending = True
                break
        if not has_pending and scenario.current_tick >= scenario.max_ticks:
            return "拦截失败：未能在规定时间内拦截目标"

    elif cond == "target_lost":
        has_detect = False
        for link in (active_links or []):
            lt_id = link.get("link_type_id", "")
            from app.models.v2.object_type import LinkType
            lt = db.query(LinkType).filter(LinkType.id == lt_id).first() if isinstance(lt_id, str) else None
            if lt and ("探测" in (lt.name_cn or "") or "detect" in (lt.name_en or "").lower()):
                has_detect = True
                break
        if not has_detect and active_links:
            pass
        missiles = [s for s in (instance_states or []) if "导弹" in (s.get("instance_name", "") or "")]
        if not missiles:
            return "目标丢失：雷达丢失所有导弹目标"

    return None
