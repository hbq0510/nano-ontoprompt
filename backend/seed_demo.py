"""一次性 Demo 数据播种脚本"""
import uuid, json
from datetime import datetime, timezone
from app.database import SessionLocal, engine, Base
# 先导入所有模型
from app.models import user, ontology, entity, logic as logic_model, action, relation, extraction_task, rules_config, entity_template
from app.models.v2 import dataset as v2_dataset, pipeline as v2_pipeline, connection as v2_connection
from app.models.v2.logic import OntologyLogicRule, OntologyStateMachine
from app.models.v2.action import OntologyActionType, OntologyActionRun
from app.models.v2.object_type import ObjectType, ObjectInstance, Interface, LinkType, Link
from app.models.object_rule import ObjectRule
from app.models.object_action import ObjectAction
from app.models.skill import Skill, SkillTrigger
from app.models.intel_snapshot import IntelSnapshot
from app.models.ontology import OntologyProject

Base.metadata.create_all(bind=engine)

db = SessionLocal()
admin_id = "287cf37b-ea25-4212-ba21-11705ebc2576"

# --- 创建全新的本体空间 ---
new_oid = str(uuid.uuid4())
project = OntologyProject(
    id=new_oid, name="防空反导 Demo", domain="军事",
    description="都市圈反导防御战 — 规则引擎演示",
    status="created", build_mode="manual",
    created_by=admin_id,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)
db.add(project)
db.commit()
print(f"新建本体空间: {new_oid}")
oid = new_oid

# --- 三个本体 ---
radar_id      = str(uuid.uuid4())
intercept_id  = str(uuid.uuid4())
threat_id     = str(uuid.uuid4())

ot1 = ObjectType(id=radar_id, ontology_id=oid, name_cn="雷达站", name_en="Radar",
    property_schema={"位置": {"type": "string"}, "扫描扇区": {"type": "string"}, "最大跟踪目标数": {"type": "number", "unit": "个"}})
ot2 = ObjectType(id=intercept_id, ontology_id=oid, name_cn="拦截单元", name_en="Interceptor",
    property_schema={"类型": {"type": "string"}, "弹药数量": {"type": "number", "unit": "发"}, "单发毁伤率": {"type": "number"}})
ot3 = ObjectType(id=threat_id, ontology_id=oid, name_cn="威胁目标", name_en="Threat",
    property_schema={"坐标_X": {"type": "number"}, "坐标_Y": {"type": "number"}, "速度": {"type": "number"}, "战斗部类型": {"type": "string"}})
db.add_all([ot1, ot2, ot3])
db.flush()

# --- 三个关系类型 ---
lt1_id = str(uuid.uuid4())
lt2_id = str(uuid.uuid4())
lt3_id = str(uuid.uuid4())

db.add(LinkType(id=lt1_id, ontology_id=oid, name_cn="探测流", name_en="DETECT_FLOW",
    source_object_type_id=radar_id, target_object_type_id=threat_id,
    property_schema={"snr": {"type": "number"}, "is_locked": {"type": "boolean"}}))
db.add(LinkType(id=lt2_id, ontology_id=oid, name_cn="火力通道流", name_en="FIRE_CHANNEL_FLOW",
    source_object_type_id=intercept_id, target_object_type_id=threat_id,
    property_schema={"p_kill": {"type": "number"}, "time_to_intercept": {"type": "number", "unit": "ms"}}))
db.add(LinkType(id=lt3_id, ontology_id=oid, name_cn="威胁流", name_en="THREAT_FLOW",
    source_object_type_id=threat_id, target_object_type_id=None, property_schema={}))
db.flush()

# --- 三个实体实例 ---
radar_inst_id      = str(uuid.uuid4())
intercept_inst_id  = str(uuid.uuid4())
threat_inst_id     = str(uuid.uuid4())

db.add(ObjectInstance(id=radar_inst_id, ontology_id=oid, object_type_id=radar_id,
    name_cn="雷达站A-001", name_en="RadarA001",
    properties={"位置": "华东", "扫描扇区": "120度", "最大跟踪目标数": 50}))
db.add(ObjectInstance(id=intercept_inst_id, ontology_id=oid, object_type_id=intercept_id,
    name_cn="拦截单元B-001", name_en="InterceptorB001",
    properties={"类型": "远距相控阵", "弹药数量": 20, "单发毁伤率": 0.75}))
db.add(ObjectInstance(id=threat_inst_id, ontology_id=oid, object_type_id=threat_id,
    name_cn="巡航导弹X-001", name_en="CruiseX001",
    properties={"坐标_X": 100, "坐标_Y": 200, "速度": 850, "战斗部类型": "HE"}))
db.flush()

# --- 不预建 Link！Link 由规则命中后的动作来创建 ---
# --- 一条规则（挂在雷达站本体层） ---
rule_id = str(uuid.uuid4())
db.add(ObjectRule(id=rule_id, ontology_id=oid, name_cn="探测规则：判断目标是否在扫描范围",
    description="遍历所有威胁目标实例，判断其坐标是否在雷达扫描扇区内，匹配则标记为已捕获",
    python_code='''import math

def check(context: dict) -> dict:
    # 雷达自身参数
    radar_x = context.get("位置", "")
    max_track = context.get("最大跟踪目标数", 50)

    # 遍历同本体空间内的所有实例
    all_instances = context.get("all_instances", [])
    threats = [i for i in all_instances if i.get("type_name") == "威胁目标"]

    detected = []
    for t in threats:
        tx = t.get("properties", {}).get("坐标_X", 0)
        ty = t.get("properties", {}).get("坐标_Y", 0)
        # 简化判断：坐标非零即认为在探测范围内
        if int(tx or 0) > 0 and int(ty or 0) > 0:
            detected.append({
                "instance_id": t["instance_id"],
                "instance_name": t["instance_name"],
                "坐标_X": tx,
                "坐标_Y": ty,
            })

    if len(detected) > 0:
        return {
            "passed": True,
            "message": f"探测到 {len(detected)} 个威胁目标",
            "snr": 18.5,
            "is_locked": True,
            "detected_threats": detected,
        }
    return {"passed": False, "message": "未探测到任何威胁目标"}
''', object_type_id=radar_id))

# --- 一条动作（挂在雷达站，关联上面那条规则） ---
db.add(ObjectAction(id=str(uuid.uuid4()), ontology_id=oid, name_cn="动作：创建探测流",
    description="对每个探测到的威胁目标，创建一条 DETECT_FLOW Link",
    python_code='''def execute(context: dict) -> dict:
    rule_result = context.get("rule_result", {})
    threats = rule_result.get("detected_threats", [])
    snr = rule_result.get("snr", 0)
    is_locked = rule_result.get("is_locked", False)
    radar_id = context.get("instance_id", "")

    if not threats:
        return {"status": "skipped", "message": "无威胁目标"}

    created = []
    for t in threats:
        created.append({
            "link_type": "DETECT_FLOW",
            "source_instance_id": radar_id,
            "target_instance_id": t["instance_id"],
            "properties": {"snr": snr, "is_locked": is_locked},
        })

    return {
        "status": "done",
        "message": f"已为 {len(created)} 个威胁目标建立探测流",
        "links_to_create": created,
    }
''', object_type_id=radar_id, object_rule_id=rule_id))

db.commit()
db.close()
print("全部创建完成！")
print(f"threat_inst_id = {threat_inst_id}   (巡航导弹X-001)")
print(f"radar_inst_id  = {radar_inst_id}   (雷达站A-001)")
