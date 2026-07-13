"""
动作执行器 — 规则命中后，执行关联的 Python 动作函数。

用法：
    executor = ActionExecutor(db_session, ontology_id)
    results = executor.run_for_rule(rule_id, context)
"""

import math
import json
from typing import Any


class ActionExecutor:
    """执行 ObjectAction 中存储的 Python 动作函数"""

    def __init__(self, db, ontology_id: str):
        self.db = db
        self.ontology_id = ontology_id

    def run_for_rule(self, rule_id: str, context: dict) -> list[dict]:
        """执行所有关联到某条规则的 action"""
        from app.models.object_action import ObjectAction

        actions = (
            self.db.query(ObjectAction)
            .filter(
                ObjectAction.ontology_id == self.ontology_id,
                ObjectAction.object_rule_id == rule_id,
            )
            .all()
        )

        results = []
        for action in actions:
            if not action.python_code or not action.python_code.strip():
                continue
            result = self._execute_action(action, context)
            result["action_id"] = action.id
            result["action_name"] = action.name_cn
            results.append(result)

        return results

    def run_for_type(self, type_id: str, context: dict) -> list[dict]:
        """执行所有直接挂在本体上的 action"""
        from app.models.object_action import ObjectAction

        actions = (
            self.db.query(ObjectAction)
            .filter(
                ObjectAction.ontology_id == self.ontology_id,
                ObjectAction.object_type_id == type_id,
                ObjectAction.object_rule_id.is_(None),
            )
            .all()
        )

        results = []
        for action in actions:
            if not action.python_code or not action.python_code.strip():
                continue
            result = self._execute_action(action, context)
            result["action_id"] = action.id
            result["action_name"] = action.name_cn
            results.append(result)

        return results

    def _execute_action(self, action, context: dict) -> dict:
        """安全执行一条动作的 Python 代码"""
        code = action.python_code.strip()

        try:
            local_ns: dict[str, Any] = {}
            exec(code, {"__builtins__": _safe_builtins(), "math": math, "json": json}, local_ns)

            execute_fn = local_ns.get("execute")
            if not callable(execute_fn):
                return {"status": "skipped", "error": "动作代码中未定义 execute(context) 函数"}

            result = execute_fn(context)
            if not isinstance(result, dict):
                return {"status": "done", "raw_result": str(result)}
            if "status" not in result:
                result["status"] = "done"

            # 动作返回 links_to_create 作为提议，不自动写入，等用户确认
            return result

        except Exception as e:
            return {"status": "failed", "error": f"动作执行异常: {str(e)}"}

    def _create_links(self, links: list[dict]) -> int:
        """根据动作返回的 links_to_create 列表，写入 Link 表"""
        from app.models.v2.object_type import Link
        from app.models.v2.object_type import LinkType
        import uuid

        count = 0
        for item in links:
            lt_name = item.get("link_type", "")
            # 按名称查找 LinkType ID
            lt = (
                self.db.query(LinkType)
                .filter(LinkType.ontology_id == self.ontology_id, LinkType.name_en == lt_name)
                .first()
            )
            if not lt:
                continue

            src_id = item.get("source_instance_id", "")
            tgt_id = item.get("target_instance_id", "")
            props = item.get("properties", {})

            # 避免重复创建
            existing = (
                self.db.query(Link)
                .filter(
                    Link.ontology_id == self.ontology_id,
                    Link.link_type_id == lt.id,
                    Link.source_instance_id == src_id,
                    Link.target_instance_id == tgt_id,
                )
                .first()
            )
            if existing:
                continue

            self.db.add(Link(
                id=str(uuid.uuid4()),
                ontology_id=self.ontology_id,
                link_type_id=lt.id,
                source_instance_id=src_id,
                target_instance_id=tgt_id,
                properties=props,
            ))
            count += 1

        if count > 0:
            self.db.commit()
        return count


def _safe_builtins() -> dict:
    import builtins
    return {
        "True": True, "False": False, "None": None,
        "abs": builtins.abs, "all": builtins.all, "any": builtins.any,
        "bool": builtins.bool, "dict": builtins.dict, "enumerate": builtins.enumerate,
        "filter": builtins.filter, "float": builtins.float, "int": builtins.int,
        "len": builtins.len, "list": builtins.list, "map": builtins.map,
        "max": builtins.max, "min": builtins.min, "pow": builtins.pow,
        "print": builtins.print, "range": builtins.range, "round": builtins.round,
        "set": builtins.set, "sorted": builtins.sorted, "str": builtins.str,
        "sum": builtins.sum, "tuple": builtins.tuple, "type": builtins.type,
        "zip": builtins.zip, "Exception": Exception, "ValueError": ValueError,
        "__import__": builtins.__import__,
    }
