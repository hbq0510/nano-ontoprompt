"""
军事知识本体种子脚本 — 直接写入 PostgreSQL，不依赖 LLM

生成内容：
  - 25+ 实体（武器系统、部队单位、防御设施、军事概念）
  - 15+ 关系
  - 8 条逻辑规则（IF-THEN 威胁评估）
  - 8 个动作（战术响应 + Python 执行代码）

用法：docker compose exec backend python /app/../seed_military_ontology.py
      或直接在 backend 容器内执行
"""

import uuid, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.ontology import OntologyProject
from app.models.entity import Entity
from app.models.relation import Relation
from app.models.logic import LogicRule
from app.models.action import Action
from app.models.user import User


def seed():
    db = SessionLocal()

    # 找第一个 admin 用户
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        print("❌ 没有 admin 用户，请先注册/登录")
        return
    user_id = admin.id

    # ── 创建本体项目 ──
    oid = str(uuid.uuid4())
    project = OntologyProject(
        id=oid,
        name="军事威胁评估知识库",
        domain="军事",
        description="包含武器装备、部队编制、防御设施、交战规则和战术响应动作的军事领域知识本体。用于情报快速匹配和威胁评估。",
        build_mode="simple_llm",
        created_by=user_id,
        status="created",
    )
    db.add(project)
    db.flush()  # 确保 ontology_id 写入 PostgreSQL

    # ═══════════════════════════════════════════════════════════════
    # 实体
    # ═══════════════════════════════════════════════════════════════
    entities = [
        # 武器系统 (Weapon)
        ("洲际弹道导弹", "Weapon", "射程8000-15000km，可携带核弹头或常规弹头", {"射程_km": 12000, "弹头类型": "核/常规", "制导方式": "惯性+星光"}),
        ("中程弹道导弹", "Weapon", "射程3000-5500km，常规打击主力", {"射程_km": 4000, "弹头类型": "常规", "精度": "CEP<10m"}),
        ("巡航导弹", "Weapon", "低空突防，射程1500-2500km", {"射程_km": 2000, "飞行高度_m": 50, "制导": "地形匹配+GPS"}),
        ("反舰导弹", "Weapon", "用于打击水面舰艇目标", {"射程_km": 400, "速度": "超音速", "末段机动": True}),
        ("主战坦克", "Weapon", "地面突击核心装备，120/125mm主炮", {"口径_mm": 125, "装甲": "复合+反应装甲", "最大时速": "70km/h"}),
        ("步兵战车", "Weapon", "伴随坦克作战，搭载步兵班", {"载员": 8, "武器": "30mm机炮", "装甲": "铝合金+附加装甲"}),
        ("武装直升机", "Weapon", "对地攻击和反坦克作战", {"武器": "反坦克导弹+火箭弹", "航程_km": 500, "乘员": 2}),
        ("战斗机", "Weapon", "制空权争夺和对面打击", {"最大速度": "Mach2.0", "作战半径_km": 1200, "武器挂点": 10}),
        ("防空导弹系统", "Weapon", "区域防空和要地防空", {"最大射程_km": 200, "同时跟踪目标": 60, "拦截高度_m": 30000}),

        # 部队单位 (Unit)
        ("装甲师", "Unit", "以坦克为核心的地面突击力量，编制约10000人", {"坦克数量": 300, "人员编制": 10000, "主要装备": "主战坦克+步兵战车"}),
        ("机械化步兵旅", "Unit", "以步兵战车为机动平台的合成部队，约5000人", {"人员编制": 5000, "主要装备": "步兵战车+自行火炮", "机动方式": "履带式"}),
        ("炮兵旅", "Unit", "远程火力打击单元", {"火炮数量": 108, "主要装备": "155mm自行榴弹炮+火箭炮", "最大射程_km": 300}),
        ("导弹旅", "Unit", "战役战术导弹发射单位", {"发射车数量": 24, "主要装备": "中程弹道导弹+巡航导弹"}),
        ("航空兵团", "Unit", "固定翼作战飞机编制单位", {"飞机数量": 48, "机型": "战斗机+攻击机+预警机"}),
        ("特种作战大队", "Unit", "执行渗透、侦察、斩首等特殊任务", {"人员编制": 800, "作战能力": "渗透/斩首/侦察", "部署方式": "直升机+潜水"}),

        # 防御设施 (Facility)
        ("地下指挥所", "Facility", "核生化防护，可容纳200人持续指挥72小时", {"防护等级": "核生化", "容纳人数": 200, "自主供电_h": 72}),
        ("防空雷达站", "Facility", "远程预警和对空监视", {"探测距离_km": 450, "频率": "L/S波段", "可跟踪目标": 200}),
        ("前线弹药库", "Facility", "储存弹药和油料，支撑前线作战", {"弹药储量_吨": 5000, "安全距离_km": 50, "防护": "地下+钢筋混凝土"}),
        ("边境防线", "Facility", "由哨所、壕沟、雷区和火力点组成的防御体系", {"长度_km": 500, "哨所数量": 30, "纵深_km": 15}),
        ("海军基地", "Facility", "舰艇停泊和补给设施", {"可泊吨位": 100000, "船坞数量": 4, "油料储备_吨": 20000}),
        ("空军基地", "Facility", "战斗机起降和维护设施", {"跑道长度_m": 3500, "机库数量": 48, "油料储备_吨": 15000}),

        # 军事概念 (Concept)
        ("一级战备", "Concept", "最高战备状态，部队全员在位、武器弹药装填完毕", {"响应时间": "即时", "适用场景": "确认敌方即将攻击"}),
        ("防空识别区", "Concept", "为预警和拦截争取时间的空域范围", {"范围_km": 500, "法律依据": "国际惯例"}),
        ("火力覆盖", "Concept", "炮兵和航空兵对目标区域实施饱和射击", {"弹药消耗_吨每小时": 50, "覆盖面积_km2": 20}),
    ]

    entity_map: dict[str, str] = {}  # name -> id
    for name, etype, desc, props in entities:
        eid = str(uuid.uuid4())
        db.add(Entity(
            id=eid, ontology_id=oid, name_cn=name, type=etype,
            description=desc, properties=props, confidence=0.95,
        ))
        entity_map[name] = eid

    # ═══════════════════════════════════════════════════════════════
    # 关系
    # ═══════════════════════════════════════════════════════════════
    relations = [
        ("装甲师", "主战坦克", "装备"),
        ("装甲师", "步兵战车", "装备"),
        ("机械化步兵旅", "步兵战车", "装备"),
        ("机械化步兵旅", "防空导弹系统", "装备"),
        ("炮兵旅", "火力覆盖", "执行"),
        ("导弹旅", "中程弹道导弹", "装备"),
        ("导弹旅", "巡航导弹", "装备"),
        ("航空兵团", "战斗机", "装备"),
        ("航空兵团", "武装直升机", "装备"),
        ("特种作战大队", "武装直升机", "装备"),
        ("洲际弹道导弹", "地下指挥所", "发射控制来自"),
        ("反舰导弹", "海军基地", "部署于"),
        ("防空雷达站", "防空识别区", "监视"),
        ("防空导弹系统", "防空雷达站", "目标数据来自"),
        ("前线弹药库", "装甲师", "补给"),
        ("前线弹药库", "机械化步兵旅", "补给"),
        ("空军基地", "航空兵团", "驻扎"),
        ("海军基地", "反舰导弹", "部署于"),
        ("边境防线", "主战坦克", "防御依托"),
        ("一级战备", "装甲师", "触发"),
        ("一级战备", "机械化步兵旅", "触发"),
    ]

    for src_name, tgt_name, rel_type in relations:
        if src_name in entity_map and tgt_name in entity_map:
            db.add(Relation(
                id=str(uuid.uuid4()), ontology_id=oid,
                source_entity=entity_map[src_name],
                target_entity=entity_map[tgt_name],
                type=rel_type, confidence=0.90,
            ))

    # ═══════════════════════════════════════════════════════════════
    # 逻辑规则
    # ═══════════════════════════════════════════════════════════════
    rules = [
        ("弹道导弹威胁判定", "IF 洲际弹道导弹.状态 == '发射准备' OR 中程弹道导弹.状态 == '进入发射阵位' THEN 威胁等级=严重 AND 建议=启动反导系统", "弹道导弹发射前通常有特定征兆", ["洲际弹道导弹", "中程弹道导弹"]),
        ("装甲部队集结预警", "IF 装甲师.部署距离_km < 50 AND 机械化步兵旅.部署距离_km < 30 THEN 威胁等级=高", "装甲部队前出集结是进攻前兆", ["装甲师", "机械化步兵旅"]),
        ("防空压制判断", "IF 战斗机.活动状态 == '频繁越界' AND 防空雷达站.状态 == '受干扰' THEN 可能即将空袭", "压制防空是空袭的标准前奏", ["战斗机", "防空雷达站"]),
        ("后勤节点受威胁", "IF 前线弹药库.安全状态 == '暴露' THEN 前线部队补给能力降低70%", "弹药库是战役支撑点", ["前线弹药库"]),
        ("海军战力投送", "IF 反舰导弹.状态 == '激活' AND 海军基地.状态 == '戒备' THEN 敌方可能两栖登陆", "反舰武器激活+基地戒备=登陆前兆", ["反舰导弹", "海军基地"]),
        ("战备升级条件", "IF 防空识别区.入侵次数 > 5 OR 边境防线.越境事件 > 3 THEN 战备等级提升至一级战备", "多次侵犯是升级战备的触发器", ["防空识别区", "边境防线", "一级战备"]),
        ("导弹覆盖范围重叠", "IF 巡航导弹.射程_km >= 1500 AND 中程弹道导弹.射程_km >= 3000 THEN 形成纵深打击能力", "多种导弹射程覆盖形成梯次打击", ["巡航导弹", "中程弹道导弹"]),
        ("特种作战威胁", "IF 特种作战大队.状态 == '渗透' AND 地下指挥所.防护状态 != '最高' THEN 指挥节点风险=高", "特种部队渗透是指挥所的直接威胁", ["特种作战大队", "地下指挥所"]),
    ]

    rule_map: dict[str, str] = {}
    for name, formula, desc, linked in rules:
        rid = str(uuid.uuid4())
        rule = LogicRule(
            id=rid, ontology_id=oid, name_cn=name,
            formula=formula, description=desc, confidence=0.88,
        )
        rule.linked_entities = linked
        db.add(rule)
        rule_map[name] = rid

    # ═══════════════════════════════════════════════════════════════
    # 动作
    # ═══════════════════════════════════════════════════════════════
    actions = [
        (
            "启动反导防御", "弹道导弹威胁判定",
            "当弹道导弹威胁判定规则触发时，立即启动多层反导拦截系统",
            ["洲际弹道导弹", "防空导弹系统"],
            """def activate_missile_defense(context: dict) -> dict:
    threat_level = context.get('threat_level', 'unknown')
    incoming_count = context.get('missile_count', 0)
    if threat_level == 'critical' and incoming_count > 0:
        return {
            'status': 'engaged',
            'action': 'activate_multi_layer_intercept',
            'interceptors_deployed': min(incoming_count * 3, 100),
            'message': f'已启动{min(incoming_count * 3, 100)}枚拦截弹应对{incoming_count}枚来袭导弹'
        }
    return {'status': 'standby', 'action': 'monitor', 'message': '反导系统待命'}"""
        ),
        (
            "前推装甲预备队", "装甲部队集结预警",
            "当装甲部队集结预警规则触发时，向前线派出装甲预备队建立反冲击阵地",
            ["装甲师", "机械化步兵旅"],
            """def deploy_armor_reserve(context: dict) -> dict:
    enemy_distance_km = context.get('enemy_distance_km', 100)
    own_tank_count = context.get('own_tank_count', 0)
    if enemy_distance_km < 50 and own_tank_count >= 50:
        return {
            'status': 'deployed',
            'units': f'{own_tank_count // 3}辆坦克前推至防线',
            'position': '反冲击阵地',
            'message': f'敌方距离{enemy_distance_km}km，已前推装甲预备队'
        }
    return {'status': 'hold', 'message': '暂不调动预备队'}"""
        ),
        (
            "加强防空警戒", "防空压制判断",
            "当防空压制判断规则触发时，增加雷达扫描频率并提高拦截战备等级",
            ["防空雷达站", "防空导弹系统"],
            """def raise_air_defense_alert(context: dict) -> dict:
    radar_status = context.get('radar_status', 'normal')
    fighter_activity = context.get('fighter_activity', 0)
    if radar_status == 'jammed' or fighter_activity > 5:
        return {
            'status': 'high_alert',
            'scan_frequency': 'double',
            'interceptors_ready': True,
            'message': f'雷达受扰，战斗机活动{fighter_activity}架次，防空已升级至高等级戒备'
        }
    return {'status': 'normal', 'message': '防空系统常规运行'}"""
        ),
        (
            "加固后勤节点", "后勤节点受威胁",
            "当前线弹药库暴露时，立即实施伪装加固和物资分散",
            ["前线弹药库"],
            """def secure_logistics_node(context: dict) -> dict:
    depot_status = context.get('depot_status', 'normal')
    if depot_status == 'exposed':
        return {
            'status': 'securing',
            'actions': ['部署伪装网', '启动烟幕发生器', '物资分散转移至备用仓库'],
            'completion_time_h': 4,
            'message': '弹药库已暴露，正在加固和分散'
        }
    return {'status': 'normal', 'message': '后勤节点安全'}"""
        ),
        (
            "海军战备升级", "海军战力投送",
            "当反舰导弹激活且海军基地戒备时，启动反登陆作战预案",
            ["反舰导弹", "海军基地"],
            """def naval_counter_landing(context: dict) -> dict:
    anti_ship_status = context.get('anti_ship_status', 'inactive')
    base_alert = context.get('base_alert', 'normal')
    if anti_ship_status == 'active' and base_alert == 'alert':
        return {
            'status': 'counter_landing_ready',
            'deployments': ['反舰导弹进入发射阵位', '巡逻艇出港', '岸防炮就位'],
            'message': '反舰武器已激活，基地进入反登陆戒备'
        }
    return {'status': 'normal', 'message': '海军常规巡逻'}"""
        ),
        (
            "发布战备动员令", "战备升级条件",
            "当多次侵犯触发战备升级时，发布全面动员令",
            ["一级战备", "装甲师", "机械化步兵旅"],
            """def issue_mobilization_order(context: dict) -> dict:
    incursions = context.get('incursions', 0)
    if incursions > 3:
        return {
            'status': 'full_mobilization',
            'level': '一级战备',
            'units_affected': ['所有装甲部队', '机械化步兵部队', '航空兵'],
            'message': f'已发生{incursions}次侵犯事件，发布全面战备动员令'
        }
    return {'status': 'monitor', 'message': '继续监视'}"""
        ),
        (
            "申请空中支援", "装甲部队集结预警",
            "当发现大规模装甲集结时，申请对地攻击机支援",
            ["战斗机", "武装直升机"],
            """def request_air_support(context: dict) -> dict:
    enemy_armor_count = context.get('enemy_armor_count', 0)
    if enemy_armor_count > 50:
        return {
            'status': 'air_support_requested',
            'assets': ['对地攻击机4架', '武装直升机8架'],
            'target': f'敌方{enemy_armor_count}辆装甲目标',
            'message': '敌方大规模装甲集结，已申请空中火力支援'
        }
    return {'status': 'pending', 'message': '持续监视'}"""
        ),
        (
            "转移指挥所", "特种作战威胁",
            "当特种作战威胁高时，启动指挥所转移预案",
            ["地下指挥所", "特种作战大队"],
            """def relocate_command_post(context: dict) -> dict:
    threat_high = context.get('special_forces_threat', False)
    protection_level = context.get('protection_level', 'standard')
    if threat_high and protection_level != 'maximum':
        return {
            'status': 'relocating',
            'new_location': '备用指挥所',
            'time_to_operational_min': 30,
            'message': '特种部队威胁，指挥所转移至备用设施'
        }
    return {'status': 'stay', 'message': '指挥所安全'}"""
        ),
    ]

    for name, rule_name, exec_rule, linked_ents, func_code in actions:
        linked_logic = [rule_map[rule_name]] if rule_name in rule_map else []
        db.add(Action(
            id=str(uuid.uuid4()), ontology_id=oid,
            name_cn=name, name_en=name.replace(" ", "_"),
            execution_rule=exec_rule, function_code=func_code,
            linked_entities=linked_ents,
            linked_logic_ids=linked_logic,
            description=f"触发条件：{exec_rule[:50]}...",
            confidence=0.90,
        ))

    db.commit()
    db.close()

    print(f"✅ 军事威胁评估知识库已创建！")
    print(f"   Ontology ID: {oid}")
    print(f"   Ontology 名: 军事威胁评估知识库")
    print(f"   实体: {len(entities)} 个")
    print(f"   关系: {len(relations)} 个")
    print(f"   逻辑规则: {len(rules)} 条")
    print(f"   动作: {len(actions)} 个")
    print(f"\n📋 刷新前端页面 http://localhost:5173/ontologies 即可看到")


if __name__ == "__main__":
    seed()
