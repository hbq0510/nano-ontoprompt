"""
军事情报危险评估引擎 — 纯规则引擎，不调 LLM。

对已提取的实体和关系做关键词匹配，加权计算危险分数，
映射到危险等级，生成战术建议。
"""

from __future__ import annotations

# ── 关键词定义 ──────────────────────────────────────────────────────

ENEMY_KEYWORDS = [
    "敌军", "敌方", "敌人", "反对势力", "威胁目标", "入侵者",
    "武装分子", "敌方部队", "敌对阵营", "侵略", "敌对", "入侵部队",
    "不明身份", "敌方舰", "敌舰", "敌机", "敌阵",
]

WEAPON_KEYWORDS = [
    "导弹", "战机", "军舰", "坦克", "兵团", "轰炸机", "潜艇",
    "航母", "驱逐舰", "巡洋舰", "护卫舰", "登陆舰", "战斗机",
    "武装直升机", "火炮", "火箭炮", "鱼雷", "水雷", "核武器",
    "特种部队", "装甲师", "机械化旅", "防空导弹",
]

FRIENDLY_KEYWORDS = [
    "我军", "友军", "己方", "我军部队", "友方", "盟军", "联军",
    "我方", "红方", "蓝方",
]

DEFENSE_KEYWORDS = [
    "基地", "指挥部", "雷达站", "防空阵地", "预警系统", "哨所",
    "防线", "巡逻队", "护卫舰", "巡逻机", "侦察卫星", "前哨",
    "防御工事", "拦截系统", "反导系统",
]

THREAT_RELATION_KEYWORDS = [
    "威胁", "攻击", "摧毁", "瞄准", "锁定", "入侵", "挑衅",
    "敌意", "宣战", "炮击", "轰炸", "发射",
]

HOSTILE_MOVEMENT_KEYWORDS = [
    "集结", "部署", "机动", "接近", "进入", "调动", "移动至",
    "越过", "推进", "包围", "渗透", "登陆",
]

DEFENSE_RELATION_KEYWORDS = [
    "防御", "保护", "守卫", "拦截", "巡逻", "预警", "侦察",
    "监视", "戒备",
]


# ── 核心函数 ────────────────────────────────────────────────────────

# 防御设施被破坏的上下文关键词
BAD_CONTEXT_JAM = ["干扰", "压制", "屏蔽", "失效", "瘫痪", "失灵", "中断"]
BAD_CONTEXT_DESTROY = ["摧毁", "击毁", "炸毁", "歼", "消灭", "命中", "打击", "轰炸"]
BAD_CONTEXT_CAPTURE = ["占领", "攻陷", "突破", "失联", "断联", "渗透", "突入"]


def _check_defense_compromised(entity_name: str, entity_type: str, intel_text: str) -> int:
    """
    检查防御实体是否在情报上下文中被破坏。
    返回应加回的分数修正值（正数）。
    """
    combined = f"{entity_name} {entity_type}"
    if not _match_any(combined, DEFENSE_KEYWORDS):
        return 0  # 不是防御实体，不修正

    if _match_any(intel_text, BAD_CONTEXT_DESTROY):
        return 6 + 2  # 摧毁比干扰更严重：原本-2变+6，净修正+8
    elif _match_any(intel_text, BAD_CONTEXT_JAM):
        return 4 + 2  # 干扰：原本-2变+4，净修正+6
    elif _match_any(intel_text, BAD_CONTEXT_CAPTURE):
        return 4 + 2  # 被占领/突破同干扰级别
    return 0


def calculate_danger(
    entities: list[dict], relations: list[dict], intel_text: str = ""
) -> tuple[float, str]:
    """
    计算危险分数和等级。
    intel_text 可选：传入情报原文可检测"防御实体被破坏"的语义。

    Returns:
        (danger_score: float 0-100, danger_level: str)
    """
    raw_score = 0.0
    # 归一化分母只计"进攻性实体"（武器+敌方），防御实体不计入
    offensive_count = 0
    # 记录哪些实体被判定为"已被破坏"
    compromised_names: set = set()

    # 实体评分
    for e in entities:
        name = (e.get("name_cn") or "").strip()
        etype = (e.get("type") or "").strip()
        combined = f"{name} {etype}"

        if _match_any(combined, ENEMY_KEYWORDS):
            raw_score += 4
            offensive_count += 1
        elif _match_any(combined, WEAPON_KEYWORDS):
            raw_score += 4
            offensive_count += 1
        elif _match_any(combined, FRIENDLY_KEYWORDS):
            raw_score -= 1
        elif _match_any(combined, DEFENSE_KEYWORDS):
            if intel_text and _check_defense_compromised(name, etype, intel_text):
                raw_score += 4
                offensive_count += 1
                compromised_names.add(name)
            else:
                raw_score -= 2

    # 关系评分
    # 构建 name→id 映射（从 matched_entities 推断）
    entity_name_to_id: dict = {}
    for e in entities:
        entity_name_to_id[e.get("name_cn", "")] = e.get("id", "")

    for r in relations:
        rtype = (r.get("type") or "").strip()
        source = (r.get("source") or "").strip()
        target = (r.get("target") or "").strip()
        combined = f"{rtype} {source} {target}"

        # 如果关系涉及的防御实体已被破坏，跳过防御关系扣分
        skip_defense_penalty = False
        if _match_any(rtype, DEFENSE_RELATION_KEYWORDS):
            for cname in compromised_names:
                cid = entity_name_to_id.get(cname, "")
                if cid and (cid == source or cid == target):
                    skip_defense_penalty = True
                    break

        if _match_any(rtype, THREAT_RELATION_KEYWORDS):
            raw_score += 6
        elif _match_any(combined, HOSTILE_MOVEMENT_KEYWORDS):
            raw_score += 3
        elif _match_any(rtype, DEFENSE_RELATION_KEYWORDS) and not skip_defense_penalty:
            raw_score -= 3

    # 归一化：分母 = max(进攻性实体数, 2)，保底防单实体满分，但不设太高避免稀释严重威胁
    denominator = max(offensive_count, 2) * 4
    normalized = min(max(raw_score / denominator, 0.0), 1.0) * 100

    # 等级映射
    if normalized <= 20:
        level = "low"
    elif normalized <= 45:
        level = "medium"
    elif normalized <= 70:
        level = "high"
    else:
        level = "critical"

    return round(normalized, 1), level


def generate_recommendations(
    danger_level: str, entities: list[dict], relations: list[dict]
) -> list[str]:
    """根据危险等级和上下文生成战术建议。最多返回 5 条。"""
    recs: list[str] = []

    # 基础建议（按等级）
    base_by_level = {
        "low": ["保持监视", "常规巡逻"],
        "medium": ["加强侦察力度", "提高警戒等级", "通知前线部队待命"],
        "high": ["部署防御力量", "通知指挥部", "启动应急响应"],
        "critical": ["立即发起反击", "请求增援", "全境进入战备状态"],
    }
    recs.extend(base_by_level.get(danger_level, []))

    # 上下文增强
    all_names = " ".join(e.get("name_cn", "") for e in entities)
    all_types = " ".join(e.get("type", "") for e in entities)
    all_rel_types = " ".join(r.get("type", "") for r in relations)
    combined = f"{all_names} {all_types} {all_rel_types}"

    if _match_any(combined, ["导弹"]):
        recs.append("启动反导防御系统")
    if _match_any(combined, ["雷达", "预警"]):
        recs.append("加强雷达扫描频率")
    if _match_any(combined, ["入侵", "越过"]):
        recs.append("封锁相关区域")
    if len(entities) > 15:
        recs.append("启动多兵种联合作战预案")
    if danger_level in ("high", "critical") and _count_matches(all_rel_types, THREAT_RELATION_KEYWORDS) > 3:
        recs.append("通知上级指挥机构")
    if _match_any(combined, ["航母", "舰队"]):
        recs.append("部署反舰力量")
    if _match_any(combined, ["登陆", "两栖"]):
        recs.append("加强海岸防御")
    if _match_any(combined, ["指挥部", "指挥中心"]) and danger_level in ("high", "critical"):
        recs.append("转移指挥所位置")

    # 去重 + 限 5 条
    seen: set[str] = set()
    result: list[str] = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result[:5]


# ── 辅助函数 ────────────────────────────────────────────────────────

def _match_any(text: str, keywords: list[str]) -> bool:
    """检查 text 中是否包含任意关键词。"""
    for kw in keywords:
        if kw in text:
            return True
    return False


def _count_matches(text: str, keywords: list[str]) -> int:
    """统计 text 中包含的关键词数量。"""
    return sum(1 for kw in keywords if kw in text)
