"""
规则触发服务 — 在实例更新/创建时，自动检查规则并执行动作。

用法：
    trigger = TriggerService(db_session)
    report = trigger.on_instance_updated(instance)
"""

from app.engine.rule_engine import RuleEngine
from app.engine.action_executor import ActionExecutor


class TriggerService:
    """实例数据变更后，检查规则 → 执行动作"""

    def __init__(self, db):
        self.db = db

    def on_instance_updated(self, instance) -> dict:
        """
        当 ObjectInstance 被更新后调用。
        1. 找到所有适用规则（本体层 + 实体层）
        2. 逐条执行规则
        3. 命中的规则 → 执行关联动作
        返回检查报告
        """
        ontology_id = instance.ontology_id
        engine = RuleEngine(self.db, ontology_id)
        executor = ActionExecutor(self.db, ontology_id)

        # 运行所有规则
        rule_results = engine.check_all(instance)

        triggered: list[dict] = []
        for rr in rule_results:
            if rr.get("passed") and not rr.get("error"):
                # 规则通过 → 执行关联动作
                context = {
                    "instance_id": instance.id,
                    "instance_name": instance.name_cn,
                    "rule_name": rr.get("rule_name"),
                    "rule_result": rr,
                }
                # 合并实例属性到上下文
                context.update(instance.properties or {})

                action_results = executor.run_for_rule(rr["rule_id"], context)
                triggered.append({
                    "rule_id": rr["rule_id"],
                    "rule_name": rr.get("rule_name"),
                    "rule_message": rr.get("message", ""),
                    "actions": action_results,
                })

        return {
            "instance_id": instance.id,
            "instance_name": instance.name_cn,
            "total_rules_checked": len(rule_results),
            "triggered": triggered,
        }
