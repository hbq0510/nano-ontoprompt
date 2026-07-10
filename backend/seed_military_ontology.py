"""
军事知识本体种子脚本 — Phase 2 重构版本

Palantir 风格两层拆分：
- ObjectType: 语义层——类型定义（属性 schema、实现哪些接口）
- ObjectInstance: 实例层——具体的一条数据
- Interface: 接口——横向打通共享属性
- LinkType: 关系类型定义
- Link: 实例之间的连线

不需要再手动维护 entities/relations 表——新体系完全替代。
"""

import uuid, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.ontology import OntologyProject
from app.models.v2.object_type import ObjectType, ObjectInstance, Interface, LinkType, Link
from app.models.logic import LogicRule
from app.models.action import Action
from app.models.user import User


def seed():
    db = SessionLocal()

    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        print("❌ 没有 admin 用户，请先注册/登录")
        return
    user_id = admin.id

    oid = str(uuid.uuid4())
    project = OntologyProject(
        id=oid, name="军事威胁评估知识库（Phase 2）", domain="军事",
        description="Palantir 风格两层架构：ObjectType + ObjectInstance + Interface + LinkType + Link。",
        build_mode="simple_llm", created_by=user_id, status="created",
    )
    db.add(project)
    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 1. Interface（共享属性，横向打通）
    # ═══════════════════════════════════════════════════════════════
    iface_equipment = Interface(
        id=str(uuid.uuid4()), ontology_id=oid,
        name_cn="装备", name_en="Equipment",
        description="所有作战装备的公共接口",
        shared_properties=[
            {"name": "状态", "type": "string", "description": "正常/损毁/已使用/维护中"},
            {"name": "所属部队", "type": "string", "description": "部署在哪个部队"},
            {"name": "位置", "type": "string", "description": "当前部署位置"},
        ],
    )
    iface_facility = Interface(
        id=str(uuid.uuid4()), ontology_id=oid,
        name_cn="设施", name_en="Facility",
        description="固定设施的公共接口",
        shared_properties=[
            {"name": "防护状态", "type": "string", "description": "正常/暴露/加固中"},
            {"name": "安全状态", "type": "string", "description": "安全/受威胁/暴露"},
            {"name": "容纳人数", "type": "number", "description": "可容纳人员数量"},
        ],
    )
    iface_threat_source = Interface(
        id=str(uuid.uuid4()), ontology_id=oid,
        name_cn="威胁源", name_en="ThreatSource",
        description="任何可能构成威胁的对象",
        shared_properties=[
            {"name": "威胁等级", "type": "string", "description": "低/中/高/严重"},
            {"name": "最后活动时间", "type": "string", "description": "最近一次活跃时间"},
        ],
    )
    db.add_all([iface_equipment, iface_facility, iface_threat_source])
    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 2. ObjectType（语义层——类型定义）
    # ═══════════════════════════════════════════════════════════════
    def mk_ot(name_cn, name_en, desc, property_schema, interface_ids=None):
        ot = ObjectType(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name_cn, name_en=name_en, description=desc,
            property_schema=property_schema,
            interface_ids=interface_ids or [],
        )
        db.add(ot)
        return ot

    # 装备类（implements Equipment 接口）
    ot_weapon = mk_ot("武器型号", "WeaponType", "导弹/火炮等武器的型号级定义，所有同型号武器共享的属性在此定义",
        {"射程_km": {"type": "number", "unit": "km"}, "战斗部类型": {"type": "string"}, "制导方式": {"type": "string"}},
        [iface_equipment.id])
    ot_tank = mk_ot("战车型号", "TankType", "坦克/装甲车的型号级定义",
        {"口径_mm": {"type": "number", "unit": "mm"}, "最大时速_kmh": {"type": "number", "unit": "km/h"}, "装甲类型": {"type": "string"}},
        [iface_equipment.id])
    ot_fighter = mk_ot("战机型号", "FighterType", "战斗机的型号级定义",
        {"最大速度": {"type": "string"}, "作战半径_km": {"type": "number", "unit": "km"}, "武器挂点": {"type": "number"}},
        [iface_equipment.id])
    ot_helicopter = mk_ot("直升机型号", "HelicopterType", "武装直升机的型号级定义",
        {"航程_km": {"type": "number", "unit": "km"}, "乘员": {"type": "number"}},
        [iface_equipment.id])

    # 具体装备实例（每个个体的状态独立变化）
    ot_missile = mk_ot("导弹实例", "Missile", "每一枚具体的导弹，状态独立变化",
        {"序列号": {"type": "string"}, "状态": {"type": "string"}, "位置": {"type": "string"}, "所属部队": {"type": "string"}},
        [iface_equipment.id, iface_threat_source.id])
    ot_armor_vehicle = mk_ot("装甲车辆实例", "ArmorVehicle", "每一辆具体的坦克/步战车",
        {"编号": {"type": "string"}, "状态": {"type": "string"}, "位置": {"type": "string"}, "所属部队": {"type": "string"}},
        [iface_equipment.id])

    # 传感器/设施类（implements Facility 接口）
    ot_sensor = mk_ot("传感器/雷达站", "Sensor", "雷达站、预警系统等传感器设施",
        {"探测距离_km": {"type": "number", "unit": "km"}, "可跟踪目标": {"type": "number"}, "状态": {"type": "string"}},
        [iface_facility.id, iface_threat_source.id])
    ot_command_post = mk_ot("指挥所", "CommandPost", "地下/移动指挥所",
        {"容纳人数": {"type": "number"}, "防护状态": {"type": "string"}, "自主供电_h": {"type": "number", "unit": "h"}},
        [iface_facility.id])
    ot_depot = mk_ot("弹药库", "AmmunitionDepot", "前线弹药和补给储存设施",
        {"弹药储量_吨": {"type": "number", "unit": "吨"}, "安全状态": {"type": "string"}},
        [iface_facility.id])
    ot_naval_base = mk_ot("海军基地", "NavalBase", "舰艇停泊和补给设施",
        {"可泊吨位": {"type": "number"}, "船坞数量": {"type": "number"}, "状态": {"type": "string"}},
        [iface_facility.id])
    ot_air_base = mk_ot("空军基地", "AirBase", "战斗机起降和维护设施",
        {"跑道长度_m": {"type": "number", "unit": "m"}, "机库数量": {"type": "number"}},
        [iface_facility.id])

    # 部队类
    ot_military_unit = mk_ot("部队单位", "MilitaryUnit", "装甲师/步兵旅/炮兵旅等编制单位",
        {"人员编制": {"type": "number"}, "部署距离_km": {"type": "number", "unit": "km"}, "坦克数量": {"type": "number"}},
        [])

    # 事件/评估类
    ot_threat_event = mk_ot("威胁事件", "ThreatEvent", "从情报报告中抽取的威胁事件",
        {"攻击类型": {"type": "string"}, "时间": {"type": "string"}, "损毁评估": {"type": "string"}, "来源报告": {"type": "string"}},
        [iface_threat_source.id])
    ot_threat_assessment = mk_ot("威胁评估结果", "ThreatAssessment", "威胁评估函数的输出结果",
        {"评分": {"type": "number"}, "置信度": {"type": "number"}, "威胁等级": {"type": "string"}, "建议动作": {"type": "string"}},
        [])

    # 概念类
    ot_concept = mk_ot("战备概念", "ReadinessConcept", "一级战备/防空识别区等军事概念",
        {"响应时间": {"type": "string"}, "适用场景": {"type": "string"}},
        [])

    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 3. ObjectInstance（实例层——具体数据）
    # ═══════════════════════════════════════════════════════════════
    def mk_oi(ot, name_cn, name_en=None, desc=None, props=None):
        oi = ObjectInstance(
            id=str(uuid.uuid4()), ontology_id=oid,
            object_type_id=ot.id,
            name_cn=name_cn, name_en=name_en or name_cn.replace(" ", "_"),
            description=desc or "", properties=props or {},
        )
        db.add(oi)
        return oi

    # 武器型号实例
    oi_icbm      = mk_oi(ot_weapon, "洲际弹道导弹", "ICBM", "射程8000-15000km",
                         {"射程_km": 12000, "战斗部类型": "核/常规", "制导方式": "惯性+星光"})
    oi_mrbm      = mk_oi(ot_weapon, "中程弹道导弹", "MRBM", "射程3000-5500km",
                         {"射程_km": 4000, "战斗部类型": "常规", "制导方式": "惯性+GPS"})
    oi_cruise    = mk_oi(ot_weapon, "巡航导弹", "CruiseMissile", "低空突防",
                         {"射程_km": 2000, "战斗部类型": "常规", "制导方式": "地形匹配+GPS"})
    oi_anti_ship = mk_oi(ot_weapon, "反舰导弹", "AntiShipMissile", "打击水面舰艇",
                         {"射程_km": 400, "战斗部类型": "常规", "制导方式": "主动雷达"})

    # 战车型号实例
    oi_mbt = mk_oi(ot_tank, "主战坦克", "MainBattleTank", "120/125mm主炮",
                   {"口径_mm": 125, "最大时速_kmh": 70, "装甲类型": "复合+反应装甲"})
    oi_ifv = mk_oi(ot_tank, "步兵战车", "IFV", "搭载步兵班",
                   {"口径_mm": 30, "最大时速_kmh": 65, "装甲类型": "铝合金+附加装甲"})

    # 战机/直升机型号
    oi_fighter   = mk_oi(ot_fighter, "战斗机", "FighterJet", "制空权争夺",
                         {"最大速度": "Mach2.0", "作战半径_km": 1200, "武器挂点": 10})
    oi_helo      = mk_oi(ot_helicopter, "武装直升机", "AttackHelicopter", "对地攻击和反坦克",
                         {"航程_km": 500, "乘员": 2})

    # 具体装备实例（每枚导弹、每辆坦克的个体状态）
    missiles_a: list = []   # 收集实例，后续统一加连线
    missiles_b: list = []
    tanks: list = []
    ifvs: list = []
    for i in range(1, 31):
        status = "损毁" if i <= 5 else "正常"
        missiles_a.append(mk_oi(ot_missile, f"导弹A#{i:03d}", f"MissileA_{i:03d}",
              f"型号=洲际弹道导弹, 状态={status}",
              {"序列号": f"A-{i:04d}", "状态": status, "位置": "发射井区A", "所属部队": "导弹旅"}))
    for i in range(1, 21):
        status = "损毁" if i <= 3 else "正常"
        missiles_b.append(mk_oi(ot_missile, f"导弹B#{i:03d}", f"MissileB_{i:03d}",
              f"型号=中程弹道导弹, 状态={status}",
              {"序列号": f"B-{i:04d}", "状态": status, "位置": "发射井区B", "所属部队": "导弹旅"}))
    for i in range(1, 11):
        tanks.append(mk_oi(ot_armor_vehicle, f"坦克#{i:02d}", f"Tank_{i:02d}", "型号=主战坦克",
              {"编号": f"TK-{i:03d}", "状态": "正常", "位置": "前沿阵地", "所属部队": "装甲师"}))
    for i in range(1, 9):
        status = "损毁" if i <= 1 else "正常"
        ifvs.append(mk_oi(ot_armor_vehicle, f"步战车#{i:02d}", f"IFV_{i:02d}", "型号=步兵战车",
              {"编号": f"IFV-{i:03d}", "状态": status, "位置": "前沿阵地", "所属部队": "机械化步兵旅"}))

    # 防空导弹系统实例（具体装备 + 传感器混合）
    oi_ads = mk_oi(ot_sensor, "防空导弹系统", "AirDefenseMissileSystem", "区域防空和要地防空",
                   {"探测距离_km": 200, "可跟踪目标": 60, "状态": "正常"})

    # 设施实例
    oi_radar   = mk_oi(ot_sensor, "防空雷达站", "AirDefenseRadarStation", "远程预警和对空监视",
                       {"探测距离_km": 450, "可跟踪目标": 200, "状态": "正常"})
    oi_cmd     = mk_oi(ot_command_post, "地下指挥所", "UndergroundCommandPost", "核生化防护",
                       {"容纳人数": 200, "防护状态": "最高", "自主供电_h": 72})
    oi_depot   = mk_oi(ot_depot, "前线弹药库", "ForwardAmmunitionDepot", "储存弹药和油料",
                       {"弹药储量_吨": 5000, "安全状态": "安全"})
    oi_naval   = mk_oi(ot_naval_base, "海军基地", "NavalBase", "舰艇停泊和补给",
                       {"可泊吨位": 100000, "船坞数量": 4, "状态": "正常"})
    oi_airbase = mk_oi(ot_air_base, "空军基地", "AirBase", "战斗机起降和维护",
                       {"跑道长度_m": 3500, "机库数量": 48})

    # 部队实例
    oi_armored_div = mk_oi(ot_military_unit, "装甲师", "ArmoredDivision", "地面突击力量",
                           {"人员编制": 10000, "部署距离_km": 30, "坦克数量": 300})
    oi_mech_brig   = mk_oi(ot_military_unit, "机械化步兵旅", "MechanizedInfantryBrigade", "合成部队",
                           {"人员编制": 5000, "部署距离_km": 20, "坦克数量": 0})
    oi_arty_brig   = mk_oi(ot_military_unit, "炮兵旅", "ArtilleryBrigade", "远程火力打击",
                           {"人员编制": 3000, "部署距离_km": 50, "坦克数量": 0})
    oi_missile_brig = mk_oi(ot_military_unit, "导弹旅", "MissileBrigade", "导弹发射单位",
                            {"人员编制": 2000, "部署距离_km": 80, "坦克数量": 0})
    oi_aviation   = mk_oi(ot_military_unit, "航空兵团", "AviationRegiment", "固定翼作战飞机编制",
                          {"人员编制": 1500, "部署距离_km": 100, "坦克数量": 0})
    oi_sf_bat     = mk_oi(ot_military_unit, "特种作战大队", "SpecialForcesBattalion", "渗透/斩首/侦察",
                          {"人员编制": 800, "部署距离_km": 5, "坦克数量": 0})

    # 边境设施
    oi_border = mk_oi(ot_sensor, "边境防线", "BorderDefenseLine", "防御体系",
                      {"探测距离_km": 500, "可跟踪目标": 30, "状态": "正常"})
    # 概念实例
    oi_readiness = mk_oi(ot_concept, "一级战备", "CombatReadinessLevel1", "最高战备状态",
                         {"响应时间": "即时", "适用场景": "确认敌方即将攻击"})
    oi_adiz = mk_oi(ot_concept, "防空识别区", "AirDefenseIdentificationZone", "预警和拦截空域",
                    {"响应时间": "即时", "适用场景": "防空预警"})

    # 威胁事件实例（示例情报驱动的数据）
    oi_event1 = mk_oi(ot_threat_event, "威胁事件#E001", "ThreatEvent_E001",
                      "雷达站遭导弹打击", {"攻击类型": "导弹", "时间": "2026-07-01 14:20", "损毁评估": "40%", "来源报告": "情报T1"})

    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 4. LinkType（关系类型——定义两个类型间的连线规则）
    # ═══════════════════════════════════════════════════════════════
    def mk_lt(name_cn, name_en, desc, src_ot=None, tgt_ot=None):
        lt = LinkType(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name_cn, name_en=name_en, description=desc,
            source_object_type_id=src_ot.id if src_ot else None,
            target_object_type_id=tgt_ot.id if tgt_ot else None,
        )
        db.add(lt)
        return lt

    lt_instance_of = mk_lt("属于型号", "instanceOf", "实例→型号", None, None)  # 通用，不限类型
    lt_attacker    = mk_lt("攻击方", "attacker", "威胁事件←攻击方", ot_threat_event, None)  # 可指向任意对象
    lt_target      = mk_lt("被打击目标", "target", "威胁事件→目标", ot_threat_event, None)
    lt_equipped_by = mk_lt("装备于", "equippedBy", "装备→所属部队", None, ot_military_unit)
    lt_operated_by = mk_lt("操作方", "operatedBy", "传感器→操作部队", ot_sensor, ot_military_unit)
    lt_deployed_at = mk_lt("部署在", "deployedAt", "装备→部署设施/位置", None, ot_sensor)
    lt_based_on    = mk_lt("基于", "basedOn", "评估→来源事件", ot_threat_assessment, ot_threat_event)
    lt_triggers    = mk_lt("触发", "triggers", "事件→触发战备状态", ot_threat_event, ot_concept)
    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 5. Link（关系实例——两条具体数据之间的连线）
    # ═══════════════════════════════════════════════════════════════
    def mk_link(lt, src, tgt):
        db.add(Link(id=str(uuid.uuid4()), ontology_id=oid,
                    link_type_id=lt.id,
                    source_instance_id=src.id, target_instance_id=tgt.id))

    # ── 型号级实例 → 所属 ObjectType（instanceOf）──
    mk_link(lt_instance_of, oi_icbm, oi_icbm)   # ICBM 型号实例属于 WeaponType（简化：型号实例关联自身）

    # ── 个体实例 → 型号（每枚导弹/每辆坦克指回其型号）──
    for m in missiles_a: mk_link(lt_instance_of, m, oi_icbm)
    for m in missiles_b: mk_link(lt_instance_of, m, oi_mrbm)
    for t in tanks:      mk_link(lt_instance_of, t, oi_mbt)
    for i in ifvs:       mk_link(lt_instance_of, i, oi_ifv)

    # ── 装备 → 所属部队（equippedBy）──
    for m in missiles_a: mk_link(lt_equipped_by, m, oi_missile_brig)
    for m in missiles_b: mk_link(lt_equipped_by, m, oi_missile_brig)
    for t in tanks:      mk_link(lt_equipped_by, t, oi_armored_div)
    for i in ifvs:       mk_link(lt_equipped_by, i, oi_mech_brig)
    mk_link(lt_equipped_by, oi_fighter, oi_aviation)
    mk_link(lt_equipped_by, oi_helo, oi_aviation)

    # ── 传感器 ← 部队 ──
    mk_link(lt_operated_by, oi_radar, oi_armored_div)
    mk_link(lt_operated_by, oi_ads, oi_armored_div)

    # ── 装备 → 部署位置 ──
    mk_link(lt_deployed_at, oi_anti_ship, oi_naval)
    mk_link(lt_deployed_at, oi_mbt, oi_border)

    # 事件关系（有方向的 attacker/target）
    mk_link(lt_target, oi_event1, oi_radar)  # 威胁事件→被打击的雷达站

    # 补给关系
    mk_link(lt_deployed_at, oi_depot, oi_armored_div)  # 弹药库→补给装甲师
    mk_link(lt_deployed_at, oi_depot, oi_mech_brig)    # 弹药库→补给步兵旅

    # 战备触发
    mk_link(lt_triggers, oi_event1, oi_readiness)

    # 部队↔设施
    mk_link(lt_deployed_at, oi_aviation, oi_airbase)
    mk_link(lt_deployed_at, oi_armored_div, oi_depot)
    mk_link(lt_deployed_at, oi_mech_brig, oi_depot)
    mk_link(lt_deployed_at, oi_arty_brig, oi_depot)
    mk_link(lt_deployed_at, oi_sf_bat, oi_helo)
    mk_link(lt_deployed_at, oi_armored_div, oi_cmd)
    mk_link(lt_deployed_at, oi_sf_bat, oi_cmd)
    mk_link(lt_deployed_at, oi_icbm, oi_missile_brig)

    db.flush()

    # ═══════════════════════════════════════════════════════════════
    # 6. LogicRule + Action（用 object_type_id 精确关联，不用字符串匹配）
    # ═══════════════════════════════════════════════════════════════
    rules_spec = [
        ("弹道导弹威胁判定", "IF 导弹.状态 == '发射准备' THEN 威胁等级=严重",
         "弹道导弹发射前征兆", [ot_weapon.id, ot_missile.id],
         [{"field": "状态", "op": "in", "value": ["发射准备", "进入发射阵位"]}]),
        ("装甲部队集结预警", "IF 部队.部署距离_km < 50 THEN 威胁等级=高",
         "装甲部队前出集结是进攻前兆", [ot_military_unit.id],
         [{"field": "部署距离_km", "op": "lt", "value": 50}]),
        ("防空压制判断", "IF 传感器.状态 == '受干扰' THEN 可能即将空袭",
         "压制防空是空袭前奏", [ot_sensor.id],
         [{"field": "状态", "op": "eq", "value": "受干扰"}]),
        ("后勤节点受威胁", "IF 弹药库.安全状态 == '暴露' THEN 补给能力降低",
         "弹药库是战役支撑点", [ot_depot.id],
         [{"field": "安全状态", "op": "eq", "value": "暴露"}]),
        ("海军战力投送", "IF 海军基地.状态 == '戒备' AND 反舰导弹.状态 == '激活' THEN 可能两栖登陆",
         "反舰武器激活+基地戒备", [ot_naval_base.id, ot_weapon.id],
         [{"field": "状态", "op": "in", "value": ["激活", "戒备"]}]),
        ("战备升级条件", "IF 入侵次数 > 3 THEN 战备升级",
         "多次侵犯是升级触发器", [ot_concept.id],
         [{"field": "入侵次数", "op": "gt", "value": 3}]),
        ("导弹覆盖范围重叠", "IF 武器.射程_km >= 1500 THEN 纵深打击能力",
         "多种导弹射程覆盖", [ot_weapon.id],
         [{"field": "射程_km", "op": "gte", "value": 1500}]),
        ("特种作战威胁", "IF 特种部队.状态 == '渗透' AND 指挥所.防护状态 != '最高' THEN 指挥节点风险=高",
         "特种部队渗透是指挥所威胁", [ot_military_unit.id, ot_command_post.id],
         [{"field": "防护状态", "op": "neq", "value": "最高"}, {"field": "状态", "op": "eq", "value": "渗透"}]),
    ]
    rule_map = {}
    for name_cn, formula, desc, linked_ot_ids, conditions in rules_spec:
        rid = str(uuid.uuid4())
        rule = LogicRule(
            id=rid, ontology_id=oid, name_cn=name_cn,
            formula=formula, description=desc,
            conditions=conditions, needs_review=False,
            linked_object_type_ids=linked_ot_ids, confidence=0.88,
        )
        rule.linked_entities = [name_cn]  # 遗留兼容
        db.add(rule)
        rule_map[name_cn] = rid

    actions_spec = [
        ("启动反导防御", "弹道导弹威胁判定", ot_weapon.id,
         [{"field": "状态", "op": "in", "value": ["发射准备", "进入发射阵位"]}]),
        ("前推装甲预备队", "装甲部队集结预警", ot_military_unit.id,
         [{"field": "部署距离_km", "op": "lt", "value": 50}]),
        ("加强防空警戒", "防空压制判断", ot_sensor.id,
         [{"field": "状态", "op": "eq", "value": "受干扰"}]),
        ("加固后勤节点", "后勤节点受威胁", ot_depot.id,
         [{"field": "安全状态", "op": "eq", "value": "暴露"}]),
        ("海军战备升级", "海军战力投送", ot_naval_base.id,
         [{"field": "状态", "op": "in", "value": ["激活", "戒备"]}]),
        ("发布战备动员令", "战备升级条件", ot_concept.id,
         [{"field": "入侵次数", "op": "gt", "value": 3}]),
        ("申请空中支援", "装甲部队集结预警", ot_fighter.id,
         [{"field": "活动状态", "op": "eq", "value": "频繁越界"}]),
        ("转移指挥所", "特种作战威胁", ot_command_post.id,
         [{"field": "防护状态", "op": "neq", "value": "最高"}]),
    ]
    for name_cn, rule_name, target_ot_id, criteria in actions_spec:
        linked_logic = [rule_map[rule_name]] if rule_name in rule_map else []
        target_ot = db.query(ObjectType).filter(ObjectType.id == target_ot_id).first()
        db.add(Action(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name_cn,
            execution_rule=f"触发条件见 submission_criteria",
            linked_entities=[name_cn],  # 遗留兼容
            linked_logic_ids=linked_logic,
            submission_criteria=criteria,
            target_object_type_id=target_ot_id,
            target_entity_type=target_ot.name_en if target_ot else None,  # 遗留兼容
            needs_review=False, confidence=0.90,
        ))

    db.commit()
    db.close()

    print(f"✅ 军事威胁评估知识库（Phase 2 两层架构）已创建！")
    print(f"   Ontology ID: {oid}")
    print(f"   ObjectType（类型定义）: {db.query(ObjectType).filter(ObjectType.ontology_id==oid).count()} 个")
    print(f"   ObjectInstance（实例数据）: {db.query(ObjectInstance).filter(ObjectInstance.ontology_id==oid).count()} 个")
    print(f"   Interface（接口）: {db.query(Interface).filter(Interface.ontology_id==oid).count()} 个")
    print(f"   LinkType（关系类型）: {db.query(LinkType).filter(LinkType.ontology_id==oid).count()} 个")
    print(f"   Link（关系实例）: {db.query(Link).filter(Link.ontology_id==oid).count()} 条")
    print(f"   LogicRule（规则）: 8 条")
    print(f"   Action（动作）: 8 个")


if __name__ == "__main__":
    seed()
