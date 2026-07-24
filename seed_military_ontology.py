"""
军事防空反导本体种子脚本 — 都市圈反导防御战

直接写入 PostgreSQL/SQLite，不依赖 LLM

生成内容：
  - ObjectType: 雷达、拦截弹、导弹、HVA 等
  - ObjectInstance: 模板实例（带初始属性）
  - LinkType: DETECT_FLOW, FIRE_CHANNEL_FLOW, THREAT_FLOW
  - ObjectRule: 探测规则、火力分配规则、拦截判定规则
  - ObjectAction: 分配火力、发射拦截弹、评估结果

用法：docker compose exec backend python /app/../seed_military_ontology.py
"""

import uuid, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.ontology import OntologyProject
from app.models.v2.object_type import ObjectType, ObjectInstance, LinkType
from app.models.object_rule import ObjectRule
from app.models.object_action import ObjectAction
from app.models.simulation import Scenario
from app.models.user import User


def seed():
    db = SessionLocal()

    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        print("❌ 没有 admin 用户，请先注册/登录")
        return
    user_id = admin.id

    # ── 检查是否已存在军事本体 ──
    existing = db.query(OntologyProject).filter(OntologyProject.domain == "军事防空反导").first()
    if existing:
        print(f"⚠️ 军事防空反导本体已存在: {existing.id}")
        print("   如需重建，请先删除该本体项目")
        db.close()
        return

    # ── 创建本体项目 ──
    oid = str(uuid.uuid4())
    project = OntologyProject(
        id=oid,
        name="都市圈反导防御战",
        domain="军事防空反导",
        description="基于多层防空网（远程雷达+中段拦截+末段近防）的反导推演本体。支持饱和攻击下的火力分配与拦截概率评估。",
        build_mode="simple_llm",
        created_by=user_id,
        status="created",
    )
    db.add(project)

    # ═══════════════════════════════════════════════════════════════
    # 1. ObjectType 定义（本体 schema 层）
    # ═══════════════════════════════════════════════════════════════

    types_data = [
        {
            "name_cn": "远程预警雷达",
            "name_en": "EarlyWarningRadar",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "max_range_km": {"type": "number", "unit": "km"},
                "tracking_capacity": {"type": "number", "unit": "个"},
                "scan_interval_ms": {"type": "number", "unit": "ms"},
                "resolution_m": {"type": "number", "unit": "m"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "中段拦截弹",
            "name_en": "MidRangeInterceptor",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "max_range_km": {"type": "number", "unit": "km"},
                "min_range_km": {"type": "number", "unit": "km"},
                "kill_prob_single": {"type": "number", "unit": "概率"},
                "ammo_count": {"type": "number", "unit": "发"},
                "reload_time_ms": {"type": "number", "unit": "ms"},
                "max_altitude_km": {"type": "number", "unit": "km"},
                "speed_mach": {"type": "number", "unit": "Mach"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "近防炮",
            "name_en": "CIWS",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "max_range_km": {"type": "number", "unit": "km"},
                "kill_prob_single": {"type": "number", "unit": "概率"},
                "ammo_count": {"type": "number", "unit": "发"},
                "fire_rate_rpm": {"type": "number", "unit": "rpm"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "弹道导弹",
            "name_en": "BallisticMissile",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "speed_mach": {"type": "number", "unit": "Mach"},
                "rcs": {"type": "number", "unit": "m²"},
                "warhead_type": {"type": "string"},
                "apogee_km": {"type": "number", "unit": "km"},
                "target_latitude": {"type": "number", "unit": "deg"},
                "target_longitude": {"type": "number", "unit": "deg"},
                "direction_deg": {"type": "number", "unit": "deg"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "巡航导弹",
            "name_en": "CruiseMissile",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "speed_mach": {"type": "number", "unit": "Mach"},
                "rcs": {"type": "number", "unit": "m²"},
                "flight_altitude_m": {"type": "number", "unit": "m"},
                "direction_deg": {"type": "number", "unit": "deg"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "诱饵弹",
            "name_en": "Decoy",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "speed_mach": {"type": "number", "unit": "Mach"},
                "rcs": {"type": "number", "unit": "m²"},
                "is_decoy": {"type": "boolean"},
                "direction_deg": {"type": "number", "unit": "deg"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "HVA高价值目标",
            "name_en": "HighValueAsset",
            "property_schema": {
                "latitude": {"type": "number", "unit": "deg"},
                "longitude": {"type": "number", "unit": "deg"},
                "hardening_level": {"type": "number", "unit": "等级"},
                "value_score": {"type": "number", "unit": "分"},
                "radius_m": {"type": "number", "unit": "m"},
                "status": {"type": "string"},
            },
        },
    ]

    type_map = {}  # name_en -> ObjectType id
    for t in types_data:
        tid = str(uuid.uuid4())
        ot = ObjectType(
            id=tid, ontology_id=oid,
            name_cn=t["name_cn"], name_en=t["name_en"],
            property_schema=t["property_schema"],
        )
        db.add(ot)
        type_map[t["name_en"]] = tid

    db.flush()  # 确保 id 生成

    # ═══════════════════════════════════════════════════════════════
    # 2. ObjectInstance 模板实例（想定创建时从这些模板复制）
    # ═══════════════════════════════════════════════════════════════

    instances_data = [
        # (type_name_en, instance_name_cn, properties)
        ("EarlyWarningRadar", "Radar_A", {
            "latitude": 31.23, "longitude": 121.47,
            "max_range_km": 450, "tracking_capacity": 100,
            "scan_interval_ms": 2000, "resolution_m": 50,
            "status": "standby",
        }),
        ("MidRangeInterceptor", "HongQi-9", {
            "latitude": 31.20, "longitude": 121.50,
            "max_range_km": 200, "min_range_km": 5,
            "kill_prob_single": 0.70, "ammo_count": 20,
            "reload_time_ms": 5000, "max_altitude_km": 30,
            "speed_mach": 6, "status": "standby",
        }),
        ("CIWS", "CIWS_A", {
            "latitude": 31.22, "longitude": 121.48,
            "max_range_km": 3, "kill_prob_single": 0.60,
            "ammo_count": 3000, "fire_rate_rpm": 6000,
            "status": "standby",
        }),
        ("BallisticMissile", "DF-26B", {
            "latitude": 32.50, "longitude": 122.50,
            "speed_mach": 8, "rcs": 0.5,
            "warhead_type": "HE", "apogee_km": 100,
            "target_latitude": 31.23, "target_longitude": 121.47,
            "direction_deg": 220, "status": "flying",
        }),
        ("CruiseMissile", "CJ-10", {
            "latitude": 32.30, "longitude": 123.00,
            "speed_mach": 0.8, "rcs": 0.1,
            "flight_altitude_m": 50, "direction_deg": 240,
            "status": "flying",
        }),
        ("Decoy", "Decoy_A", {
            "latitude": 32.40, "longitude": 122.80,
            "speed_mach": 0.7, "rcs": 2.0,
            "is_decoy": True, "direction_deg": 230,
            "status": "flying",
        }),
        ("HighValueAsset", "HVA_PoliticalCenter", {
            "latitude": 31.23, "longitude": 121.47,
            "hardening_level": 3, "value_score": 100,
            "radius_m": 5000, "status": "protected",
        }),
    ]

    instance_map = {}  # name_cn -> ObjectInstance id
    for type_name_en, inst_name, props in instances_data:
        tid = type_map.get(type_name_en)
        if not tid:
            continue
        iid = str(uuid.uuid4())
        oi = ObjectInstance(
            id=iid, ontology_id=oid, object_type_id=tid,
            name_cn=inst_name, properties=props, confidence=0.95,
        )
        db.add(oi)
        instance_map[inst_name] = iid

    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 3. LinkType 定义
    # ═══════════════════════════════════════════════════════════════

    link_types_data = [
        {
            "name_cn": "探测流",
            "name_en": "DETECT_FLOW",
            "property_schema": {
                "snr": {"type": "number"},
                "dwell_time_ms": {"type": "number"},
                "is_locked": {"type": "boolean"},
                "lock_quality": {"type": "number"},
                "detection_range_km": {"type": "number"},
            },
        },
        {
            "name_cn": "火力通道流",
            "name_en": "FIRE_CHANNEL_FLOW",
            "property_schema": {
                "engagement_feasibility": {"type": "number"},
                "time_to_intercept_ms": {"type": "number"},
                "p_kill": {"type": "number"},
                "ammo_assigned": {"type": "number"},
                "salvo_count": {"type": "number"},
                "status": {"type": "string"},
            },
        },
        {
            "name_cn": "威胁流",
            "name_en": "THREAT_FLOW",
            "property_schema": {
                "leak_probability": {"type": "number"},
                "estimated_damage": {"type": "number"},
                "time_to_impact_ms": {"type": "number"},
                "warhead_lethality": {"type": "number"},
            },
        },
    ]

    link_type_map = {}
    for lt in link_types_data:
        lid = str(uuid.uuid4())
        lto = LinkType(
            id=lid, ontology_id=oid,
            name_cn=lt["name_cn"], name_en=lt["name_en"],
            property_schema=lt["property_schema"],
        )
        db.add(lto)
        link_type_map[lt["name_en"]] = lid

    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 4. ObjectRule 规则（Python 代码）
    # ═══════════════════════════════════════════════════════════════

    rules_data = [
        # 规则1：探测规则
        ("探测判定规则", type_map["EarlyWarningRadar"], None, """import math

def check(context):
    # 雷达探测范围内所有威胁目标
    radar_lat = context.get("latitude", 0)
    radar_lon = context.get("longitude", 0)
    radar_range = context.get("max_range_km", 0)
    capacity = context.get("tracking_capacity", 0)
    
    threats = []
    for other in context.get("all_instances", []):
        props = other.get("properties", {})
        if "speed_mach" in props and other.get("instance_id") != context.get("instance_id"):
            # 计算距离
            dlat = math.radians(props.get("latitude", 0) - radar_lat)
            dlon = math.radians(props.get("longitude", 0) - radar_lon)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(radar_lat)) * math.cos(math.radians(props.get("latitude", 0))) * math.sin(dlon/2)**2
            dist_km = 6371 * 2 * math.asin(math.sqrt(a))
            
            if dist_km <= radar_range:
                # 简化 SNR 计算
                rcs = props.get("rcs", 1.0)
                snr = (rcs / (dist_km ** 2)) * 10000
                is_locked = snr > 5.0
                threats.append({
                    "instance_id": other.get("instance_id"),
                    "distance_km": round(dist_km, 2),
                    "snr": round(snr, 2),
                    "is_locked": is_locked,
                })
    
    # 按 SNR 排序，只保留 capacity 个
    threats.sort(key=lambda x: x["snr"], reverse=True)
    locked = threats[:capacity]
    
    # 建议创建的探测流
    links_to_create = []
    for t in locked:
        if t["is_locked"]:
            links_to_create.append({
                "link_type": "DETECT_FLOW",
                "source_instance_id": context.get("instance_id"),
                "target_instance_id": t["instance_id"],
                "properties": {
                    "snr": t["snr"],
                    "is_locked": True,
                    "detection_range_km": t["distance_km"],
                }
            })
    
    return {
        "passed": len(locked) > 0,
        "message": f"锁定 {len(locked)} 个目标，共探测 {len(threats)} 个",
        "links_to_create": links_to_create,
        "properties_update": {"status": "tracking" if locked else "scanning"},
    }
"""),
        # 规则2：火力分配规则
        ("火力通道分配规则", type_map["MidRangeInterceptor"], None, """import math

def check(context):
    interceptor_lat = context.get("latitude", 0)
    interceptor_lon = context.get("longitude", 0)
    max_range = context.get("max_range_km", 0)
    min_range = context.get("min_range_km", 0)
    kill_prob = context.get("kill_prob_single", 0.5)
    ammo = context.get("ammo_count", 0)
    speed = context.get("speed_mach", 1) * 340  # m/s
    
    if ammo <= 0:
        return {"passed": False, "message": "弹药耗尽"}
    
    # 查找已被锁定的威胁
    locked_threats = []
    for link in context.get("related_instances", []):
        if link.get("link_type_id", "").endswith("DETECT_FLOW") or "探测" in str(link.get("link_type_id", "")):
            other = link
            other_props = other.get("properties", {})
            if other_props.get("is_locked"):
                locked_threats.append(other)
    
    # 如果没找到关联的威胁，遍历所有实例
    if not locked_threats:
        for other in context.get("all_instances", []):
            props = other.get("properties", {})
            if "speed_mach" in props and "rcs" in props:
                locked_threats.append(other)
    
    assignments = []
    for threat in locked_threats:
        props = threat.get("properties", {})
        t_lat = props.get("latitude", 0)
        t_lon = props.get("longitude", 0)
        t_speed = props.get("speed_mach", 1) * 340  # m/s
        
        dlat = math.radians(t_lat - interceptor_lat)
        dlon = math.radians(t_lon - interceptor_lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(interceptor_lat)) * math.cos(math.radians(t_lat)) * math.sin(dlon/2)**2
        dist_km = 6371 * 2 * math.asin(math.sqrt(a))
        
        if min_range <= dist_km <= max_range:
            # 简化 time_to_intercept: 距离 / 相对速度
            rel_speed = speed + t_speed * 0.001  # km/ms 近似
            time_ms = int(dist_km / rel_speed * 1000) if rel_speed > 0 else 999999
            
            salvo = min(2, ammo)
            p_kill = 1 - (1 - kill_prob) ** salvo
            
            assignments.append({
                "target_id": threat.get("instance_id"),
                "distance_km": round(dist_km, 2),
                "time_to_intercept_ms": time_ms,
                "p_kill": round(p_kill, 3),
                "salvo": salvo,
            })
    
    # 按威胁距离排序，近的优先
    assignments.sort(key=lambda x: x["distance_km"])
    
    links_to_create = []
    total_ammo_used = 0
    for a in assignments:
        if total_ammo_used + a["salvo"] > ammo:
            break
        links_to_create.append({
            "link_type": "FIRE_CHANNEL_FLOW",
            "source_instance_id": context.get("instance_id"),
            "target_instance_id": a["target_id"],
            "properties": {
                "time_to_intercept_ms": a["time_to_intercept_ms"],
                "p_kill": a["p_kill"],
                "ammo_assigned": a["salvo"],
                "salvo_count": a["salvo"],
                "status": "pending",
            }
        })
        total_ammo_used += a["salvo"]
    
    return {
        "passed": len(links_to_create) > 0,
        "message": f"分配 {len(links_to_create)} 个火力通道，消耗 {total_ammo_used} 发弹药",
        "links_to_create": links_to_create,
    }
"""),
        # 规则3：拦截判定规则
        ("拦截命中判定规则", None, None, """import math, random

def check(context):
    # 检查所有 FIRE_CHANNEL_FLOW，判断是否到达拦截时间
    # 这个规则挂在全局（不挂在特定类型上），需要检查所有实例的关联
    
    # 由于规则引擎按实例触发，我们在每个实例上检查它作为 source 的 FIRE_CHANNEL_FLOW
    # 实际上这个规则应该在动作执行器中处理，这里做个简化版
    
    return {"passed": False, "message": "拦截判定由动作执行器处理"}
"""),
    ]

    for name, type_id, inst_id, code in rules_data:
        if type_id is None and inst_id is None:
            continue  # 跳过全局规则（简化版不用）
        db.add(ObjectRule(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name, python_code=code,
            object_type_id=type_id, object_instance_id=inst_id,
        ))

    # ═══════════════════════════════════════════════════════════════
    # 5. ObjectAction 动作
    # ═══════════════════════════════════════════════════════════════

    actions_data = [
        # 动作1：发射拦截弹
        ("发射拦截弹", type_map["MidRangeInterceptor"], None, """import random

def execute(context):
    # context 包含 participants, active_links, tick, db, scenario_id, ontology_id
    participants = context.get("participants", [])
    active_links = context.get("active_links", [])
    tick = context.get("tick", 0)
    db = context.get("db")
    
    results = []
    links_to_update = []
    
    # 找到所有 pending 状态的 FIRE_CHANNEL_FLOW
    for link in active_links:
        if link.get("link_type_name", "").endswith("FIRE_CHANNEL_FLOW") or "火力" in str(link.get("link_type_name", "")):
            props = link.get("properties", {})
            if props.get("status") == "pending":
                # 标记为 guiding
                links_to_update.append({
                    "link_id": link.get("link_id"),
                    "status": "guiding",
                })
                
                # 消耗弹药
                interceptor_id = link.get("source_instance_id")
                for p in participants:
                    if p.get("instance_id") == interceptor_id:
                        current_ammo = p.get("properties", {}).get("ammo_count", 0)
                        salvo = props.get("salvo_count", 1)
                        # 这里不能直接修改，返回 properties_update
                        break
                
                results.append({
                    "status": "engaged",
                    "message": f"Tick {tick}: 火力通道建立，等待拦截",
                    "link_id": link.get("link_id"),
                })
    
    return {
        "status": "done",
        "results": results,
        "message": f"处理 {len(links_to_update)} 个火力通道",
    }
"""),
        # 动作2：拦截结果评估
        ("拦截结果评估", type_map["MidRangeInterceptor"], None, """import random

def execute(context):
    participants = context.get("participants", [])
    active_links = context.get("active_links", [])
    tick = context.get("tick", 0)
    
    results = []
    threats_destroyed = []
    
    for link in active_links:
        lt_name = link.get("link_type_name", "")
        if "FIRE_CHANNEL" in lt_name or "火力" in lt_name:
            props = link.get("properties", {})
            if props.get("status") == "guiding":
                # 检查是否到达拦截时间
                time_to_intercept = props.get("time_to_intercept_ms", 999999)
                # 简化：假设每个 tick 是 1000ms，我们在这个 tick 直接判定
                # 实际应该累计时间
                p_kill = props.get("p_kill", 0.5)
                hit = random.random() < p_kill
                
                if hit:
                    threats_destroyed.append(link.get("target_instance_id"))
                    results.append({
                        "status": "hit",
                        "message": f"Tick {tick}: 拦截命中！",
                        "target_id": link.get("target_instance_id"),
                    })
                else:
                    results.append({
                        "status": "miss",
                        "message": f"Tick {tick}: 拦截未命中",
                        "target_id": link.get("target_instance_id"),
                    })
    
    return {
        "status": "done",
        "results": results,
        "threats_destroyed": threats_destroyed,
        "message": f"评估完成: {len(results)} 次拦截",
    }
"""),
    ]

    for name, type_id, inst_id, code in actions_data:
        db.add(ObjectAction(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name, python_code=code,
            object_type_id=type_id, object_instance_id=inst_id,
        ))

    # ═══════════════════════════════════════════════════════════════
    # 6. 创建想定（Scenario）
    # ═══════════════════════════════════════════════════════════════

    # 收集所有参与实体
    all_instance_ids = list(instance_map.values())
    initial_state = []
    design_params_map = {}

    for type_name_en, inst_name, props in instances_data:
        iid = instance_map.get(inst_name)
        if not iid:
            continue
        initial_state.append({"instance_id": iid, "initial_properties": dict(props)})
        # 设计参数：排除坐标（坐标会实时更新），保留静态参数
        static_params = {k: v for k, v in props.items() if k not in ("latitude", "longitude")}
        design_params_map[iid] = static_params

    scenario_id = str(uuid.uuid4())
    scenario = Scenario(
        id=scenario_id,
        ontology_id=oid,
        name="都市圈想定 01",
        description="多层防空反导：远程雷达探测 → 中段拦截弹分配火力 → 近防炮末段补防。弹道导弹+巡航导弹+诱饵饱和攻击。",
        participant_instance_ids=all_instance_ids,
        initial_state=initial_state,
        design_params_map=design_params_map,
        max_ticks=80,
        tick_interval_ms=1000,
        stop_condition="intercept_success",
        status="draft",
        current_tick=0,
    )
    db.add(scenario)

    db.commit()
    db.close()

    print(f"✅ 都市圈反导防御战本体已创建！")
    print(f"   Ontology ID: {oid}")
    print(f"   ObjectType: {len(types_data)} 个")
    print(f"   ObjectInstance 模板: {len(instances_data)} 个")
    print(f"   LinkType: {len(link_types_data)} 个")
    print(f"   ObjectRule: {len(rules_data)} 条")
    print(f"   ObjectAction: {len(actions_data)} 个")
    print(f"   Scenario: {scenario_id[:8]} (参与实体: {len(all_instance_ids)})")
    print(f"\n📋 刷新前端页面 http://localhost:5173/ontologies 即可看到")


if __name__ == "__main__":
    seed()
