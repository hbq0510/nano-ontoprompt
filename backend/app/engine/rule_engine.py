"""
规则引擎 — 从数据库读取规则 Python 代码字符串，执行并返回结果。

用法：
    engine = RuleEngine(db_session, ontology_id)
    results = engine.check_all(instance)
"""

import math
import json
from typing import Any


class RuleEngine:
    """执行 ObjectRule 中存储的 Python 规则函数"""

    def __init__(self, db, ontology_id: str):
        self.db = db
        self.ontology_id = ontology_id

    def check_all(self, instance) -> list[dict]:
        """
        给定一个 ObjectInstance，查找所有适用于它的规则（本体层 + 实体层），
        逐个执行并返回结果列表。
        """
        from app.models.object_rule import ObjectRule

        rules = (
            self.db.query(ObjectRule)
            .filter(ObjectRule.ontology_id == self.ontology_id)
            .filter(
                (ObjectRule.object_type_id == instance.object_type_id)  # 本体层
                | (ObjectRule.object_instance_id == instance.id)         # 实体层
            )
            .all()
        )

        results = []
        for rule in rules:
            if not rule.python_code or not rule.python_code.strip():
                continue
            result = self._execute_rule(rule, instance)
            result["rule_id"] = rule.id
            result["rule_name"] = rule.name_cn
            results.append(result)

        return results

    def _execute_rule(self, rule, instance) -> dict:
        """安全执行一条规则的 Python 代码"""
        code = rule.python_code.strip()
        context = self._build_context(instance)

        try:
            # 创建受限的执行环境
            local_ns: dict[str, Any] = {}
            exec(code, {"__builtins__": _safe_builtins(), "math": math, "json": json}, local_ns)

            # 找到 check 函数
            check_fn = local_ns.get("check")
            if not callable(check_fn):
                return {"passed": False, "error": "规则代码中未定义 check(context) 函数"}

            result = check_fn(context)
            if not isinstance(result, dict):
                return {"passed": False, "error": "check() 必须返回 dict"}
            if "passed" not in result:
                result["passed"] = True
            return result

        except Exception as e:
            return {"passed": False, "error": f"规则执行异常: {str(e)}"}

    def _build_context(self, instance) -> dict:
        """构建传给 check(context) 函数的上下文数据"""
        from app.models.v2.object_type import ObjectType
        from app.models.v2.object_type import ObjectInstance as OI

        context = dict(instance.properties or {})

        # 附加实例基础信息
        context["instance_id"] = instance.id
        context["instance_name"] = instance.name_cn

        # 查找该实例所属的本体类型，注入 schema 里的默认值
        ot = self.db.query(ObjectType).filter(ObjectType.id == instance.object_type_id).first()
        if ot:
            context["type_name"] = ot.name_cn
            context["type_name_en"] = ot.name_en
            context["property_schema"] = dict(ot.property_schema or {})

        # 查找所有同 ontology 的其他实例（规则可遍历做距离判断等）
        all_instances = self.db.query(OI).filter(
            OI.ontology_id == self.ontology_id,
            OI.id != instance.id,
        ).all()
        all_others: list[dict] = []
        for oi in all_instances:
            all_others.append({
                "instance_id": oi.id,
                "instance_name": oi.name_cn,
                "object_type_id": oi.object_type_id,
                "type_name": self._get_type_name(oi.object_type_id),
                "properties": dict(oi.properties or {}),
            })
        context["all_instances"] = all_others

        # 已有 Link 关联的实例（用于判断是否已建立关系）
        try:
            from app.models.v2.object_type import Link
            links = (
                self.db.query(Link)
                .filter(
                    Link.ontology_id == self.ontology_id,
                    (Link.source_instance_id == instance.id) | (Link.target_instance_id == instance.id),
                )
                .all()
            )
            related: list[dict] = []
            for link in links:
                related_id = (
                    link.target_instance_id
                    if link.source_instance_id == instance.id
                    else link.source_instance_id
                )
                other = self.db.query(OI).filter(OI.id == related_id).first()
                if other:
                    related.append({
                        "instance_id": other.id,
                        "instance_name": other.name_cn,
                        "properties": dict(other.properties or {}),
                        "link_type_id": link.link_type_id,
                    })
            context["related_instances"] = related
        except Exception:
            context["related_instances"] = []

        return context

    def _get_type_name(self, type_id: str) -> str:
        from app.models.v2.object_type import ObjectType
        ot = self.db.query(ObjectType).filter(ObjectType.id == type_id).first()
        return ot.name_cn if ot else ""


def _safe_builtins() -> dict:
    """返回一个受限的内建函数集合，防止规则代码执行危险操作"""
    import builtins
    safe = {
        "True": True, "False": False, "None": None,
        "abs": builtins.abs, "all": builtins.all, "any": builtins.any,
        "bool": builtins.bool, "dict": builtins.dict, "enumerate": builtins.enumerate,
        "filter": builtins.filter, "float": builtins.float, "int": builtins.int,
        "isinstance": builtins.isinstance, "len": builtins.len, "list": builtins.list,
        "map": builtins.map, "max": builtins.max, "min": builtins.min,
        "pow": builtins.pow, "print": builtins.print, "range": builtins.range,
        "round": builtins.round, "set": builtins.set, "sorted": builtins.sorted,
        "str": builtins.str, "sum": builtins.sum, "tuple": builtins.tuple,
        "type": builtins.type, "zip": builtins.zip,
        "isinstance": builtins.isinstance,
        "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
        "__import__": builtins.__import__,  # 允许 import math 等
    }
    return safe
