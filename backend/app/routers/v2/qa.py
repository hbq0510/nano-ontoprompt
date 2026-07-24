"""场景智能问答 — 多轮对话，基于场景上下文回答用户问题"""

import json, logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


class QARequest(BaseModel):
    question: str
    plan_id: str | None = None
    conversation_history: list[dict] = []  # [{role: "user"|"assistant", content: "..."}]


@router.post("/scenarios/{scenario_id}/qa")
def scenario_qa(scenario_id: str, body: QARequest, db: Session = Depends(get_db)):
    from app.models.simulation import Scenario, ScenarioEvent
    from app.models.plan import Plan
    from app.models.v2.object_type import ObjectInstance, Link, LinkType

    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        return {"answer": "场景不存在，请检查想定ID。"}

    # ── 收集场景上下文 ──
    instances = db.query(ObjectInstance).filter(
        ObjectInstance.ontology_id == scenario.ontology_id
    ).all()

    instance_lines = []
    for i in instances:
        props = i.properties or {}
        key_info = {k: v for k, v in props.items() if k in (
            "latitude", "longitude", "speed_mach", "direction_deg",
            "detect_range_km", "range_km", "status", "altitude_km"
        )}
        instance_lines.append(f"  - {i.name_cn}: {json.dumps(key_info, ensure_ascii=False)}")

    # 活跃关系
    links = db.query(Link).filter(Link.ontology_id == scenario.ontology_id).all()
    lt_map = {}
    for lt in db.query(LinkType).filter(LinkType.ontology_id == scenario.ontology_id).all():
        lt_map[lt.id] = lt.name_cn or lt.name_en or lt.id
    link_lines = []
    for l in links:
        src = next((i for i in instances if i.id == l.source_instance_id), None)
        tgt = next((i for i in instances if i.id == l.target_instance_id), None)
        link_lines.append(f"  - {src.name_cn if src else '?'} --{lt_map.get(l.link_type_id, '?')}--> {tgt.name_cn if tgt else '?'}")

    # 方案信息
    plan_block = ""
    if body.plan_id:
        plan = db.query(Plan).filter(Plan.id == body.plan_id, Plan.scenario_id == scenario_id).first()
        if plan:
            plan_block = f"\n当前方案: {plan.name}\n决策链: {json.dumps(plan.decisions, ensure_ascii=False)}\n评分: {json.dumps(plan.score or {}, ensure_ascii=False)}"

    # 最近事件
    events = db.query(ScenarioEvent).filter(
        ScenarioEvent.scenario_id == scenario_id
    ).order_by(ScenarioEvent.tick.desc()).limit(15).all()

    context = f"""你是军事推演AI助手。根据以下场景信息用中文简洁回答，控制在200字以内。

═══ 场景状态 ═══
名称: {scenario.name}
描述: {scenario.description or '无'}
进度: Tick {scenario.current_tick}/{scenario.max_ticks}  状态: {scenario.status}
停止条件: {getattr(scenario, 'stop_condition', 'max_ticks')}

═══ 参与实体 ═══
{chr(10).join(instance_lines) if instance_lines else '  无'}

═══ 活跃关系 ═══
{chr(10).join(link_lines) if link_lines else '  无'}

═══ 最近事件 ═══
{chr(10).join(f'  T{e.tick}: {e.description}' for e in reversed(events)) if events else '  无'}
{plan_block}

══════════════════
请基于以上数据回答用户问题。如果问到你不知道的信息，诚实说明。"""

    # ── 构建消息 ──
    messages = [{"role": "system", "content": context}]
    for msg in body.conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": body.question})

    # ── 调用 LLM ──
    try:
        from app.services import llm_service
        from app.services.model_config_selector import llm_call_kwargs, select_llm_model_config
        call_kwargs = llm_call_kwargs(select_llm_model_config(
            db, purpose_tags=("分析", "提取", "FK检测"), allow_vlm=False
        ))
        if call_kwargs:
            answer = llm_service._call_llm(**call_kwargs, messages=messages)
            answer_text = answer.strip() if isinstance(answer, str) else str(answer)
            if answer_text:
                return {"answer": answer_text}
    except Exception as e:
        logger.warning(f"LLM QA failed: {e}")

    # ── Fallback: 规则匹配 ──
    return {"answer": _rule_based_answer(body.question, scenario, instances, link_lines)}


def _rule_based_answer(question: str, scenario, instances, link_lines) -> str:
    """无LLM时的规则兜底回答"""
    q = question.lower()

    if any(w in q for w in ("实体", "几个", "多少", "有哪些")):
        names = [i.name_cn for i in instances]
        return f"当前场景共有 {len(instances)} 个实体: {', '.join(names)}。Tick {scenario.current_tick}/{scenario.max_ticks}。"

    if any(w in q for w in ("关系", "连接", "连线", "边", "link")):
        if link_lines:
            return f"当前有 {len(link_lines)} 条活跃关系:\n" + "\n".join(link_lines)
        return f"当前没有活跃关系。Tick {scenario.current_tick}/{scenario.max_ticks}。"

    if any(w in q for w in ("位置", "在哪", "坐标", "经纬")):
        for i in instances:
            props = i.properties or {}
            lat = props.get("latitude")
            lon = props.get("longitude")
            if lat and lon:
                return f"{i.name_cn} 当前坐标: 北纬{lat}°, 东经{lon}°。"

    if any(w in q for w in ("速度", "马赫", "多快", "mach", "speed")):
        for i in instances:
            props = i.properties or {}
            speed = props.get("speed_mach")
            if speed:
                return f"{i.name_cn} 当前速度: {speed} 马赫。"

    if any(w in q for w in ("状态", "status", "进度", "到哪了")):
        return f"场景「{scenario.name}」当前进度: Tick {scenario.current_tick}/{scenario.max_ticks}，状态: {scenario.status}。共 {len(instances)} 个实体。"

    if any(w in q for w in ("雷达", "探测", "检测", "detect", "radar")):
        for i in instances:
            props = i.properties or {}
            rng = props.get("detect_range_km")
            if rng:
                return f"{i.name_cn} 探测范围: {rng}km。{'已有探测目标' if any('探测' in l for l in link_lines) else '当前未探测到目标'}。"

    if any(w in q for w in ("拦截", "intercept", "发射", "红旗")):
        for i in instances:
            props = i.properties or {}
            rng = props.get("range_km")
            if rng:
                return f"{i.name_cn} 射程: {rng}km。{'已建立拦截关系' if any('拦截' in l for l in link_lines) else '当前未拦截'}。"

    return f"当前场景「{scenario.name}」Tick {scenario.current_tick}/{scenario.max_ticks}，共 {len(instances)} 个实体，{len(link_lines)} 条活跃关系。\n你可以问: 实体信息 / 位置 / 速度 / 关系 / 状态 等。"
