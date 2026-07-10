import os
from app.config import settings
from app.tasks import celery_app


# ── Confidence calibration (Fix 5) ─────────────────────────────────────────
def _calibrate_confidence(result: dict) -> dict:
    """Adjust LLM-generated confidence scores using objective completeness signals."""
    import ast

    entities    = result.get("entities", [])
    relations   = result.get("relations", [])
    logic_rules = result.get("logic_rules", [])
    actions     = result.get("actions", [])

    entity_names = {e.get("name_cn") for e in entities if e.get("name_cn")}

    # Entities that appear in at least one relation get a small boost
    in_graph: set = set()
    for r in relations:
        in_graph.add(r.get("source")); in_graph.add(r.get("target"))

    for e in entities:
        base = float(e.get("confidence") or 0.85)
        adj  = 0.0
        if not (e.get("properties") and len(e.get("properties", {})) > 0): adj -= 0.10
        if not (e.get("description") or "").strip():                        adj -= 0.05
        if e.get("name_cn") in in_graph:                                    adj += 0.05
        e["confidence"] = round(max(0.30, min(0.98, base + adj)), 3)

    for r in relations:
        base = float(r.get("confidence") or 0.85)
        if r.get("source") not in entity_names or r.get("target") not in entity_names:
            r["confidence"] = 0.30   # broken reference → low confidence
        else:
            r["confidence"] = round(max(0.40, min(0.98, base)), 3)

    logic_names = {r.get("name_cn") for r in logic_rules if r.get("name_cn")}
    for rule in logic_rules:
        base = float(rule.get("confidence") or 0.85)
        adj  = 0.0
        if not rule.get("linked_entities"):                adj -= 0.10
        if not (rule.get("formula") or "").strip():        adj -= 0.05
        # Phase 1 结构化: conditions 为空则额外扣分（提示该规则暂无法被程序触发）
        if not rule.get("conditions") or len(rule.get("conditions", [])) == 0:
            adj -= 0.05
        rule["confidence"] = round(max(0.30, min(0.98, base + adj)), 3)

    for action in actions:
        base = float(action.get("confidence") or 0.85)
        code = (action.get("function_code") or "").strip()
        adj  = 0.0
        if not code or len(code) < 20:
            adj -= 0.20
        else:
            try:
                ast.parse(code)
            except SyntaxError:
                adj -= 0.15
        if not action.get("linked_entities"): adj -= 0.05
        # Phase 1 结构化: submission_criteria 为空则额外扣分
        if not action.get("submission_criteria") or len(action.get("submission_criteria", [])) == 0:
            adj -= 0.05
        action["confidence"] = round(max(0.30, min(0.98, base + adj)), 3)

    return result


def _dedup_existing(db, ontology_id: str, model_cls, name_field: str):
    """Delete duplicate rows with the same (ontology_id, name_field), keeping the richest one."""
    rows = db.query(model_cls).filter(model_cls.ontology_id == ontology_id).all()
    seen: dict = {}
    for row in rows:
        key = getattr(row, name_field, None)
        if not key:
            continue
        if key not in seen:
            seen[key] = row
        else:
            # Keep the one with more data (prefer non-None properties/code/formula)
            incumbent = seen[key]
            challenger_score = _richness(row)
            incumbent_score  = _richness(incumbent)
            if challenger_score > incumbent_score:
                db.delete(incumbent)
                seen[key] = row
            else:
                db.delete(row)


def _richness(obj) -> int:
    """Heuristic score for how data-rich an ORM object is — higher = keep."""
    score = 0
    for attr in ("properties", "function_code", "formula", "description", "linked_entities"):
        val = getattr(obj, attr, None)
        if val:
            score += len(str(val))
    return score


def _build_schema_instructions(ontology_id: str, db) -> str:
    """读取本体的 ObjectType 和 LinkType，翻译为 LLM Schema 约束指令。

    参考 LlamaIndex_server 的 _schema_instructions()：
    - 把实体类型清单、属性定义、关系类型（含源→目标约束）逐条写成自然语言
    - 返回的文本直接拼接到 Prompt 末尾
    """
    from app.models.v2.object_type import ObjectType, LinkType

    object_types = db.query(ObjectType).filter(
        ObjectType.ontology_id == ontology_id
    ).all()
    link_types = db.query(LinkType).filter(
        LinkType.ontology_id == ontology_id
    ).all()

    if not object_types and not link_types:
        # 本体尚未定义任何 Schema，提示 LLM 自由提取但保持类型粒度合理
        return (
            "\n\n"
            "# Schema 约束\n\n"
            "本本体空间尚未定义实体类型和关系类型。请从文本中**自动发现**合适的类型。\n\n"
            "## 类型粒度要求\n"
            "- 同类装备合并为一个类型（如所有型号的导弹都归为「导弹」，不要拆成弹道导弹/巡航导弹等子类）\n"
            "- 型号和实例不拆成两个类型（如「战斗机」就是一个类型，不要同时建「战斗机型号」和「战斗机实例」）\n"
            "- 部队单位、设施、地点等各为一个类型\n"
            "- 预计总共 5-10 个实体类型即可\n\n"
            "## 实例粒度\n"
            "- 每个具体型号/单位只建一条 ObjectInstance，不追踪个体状态\n"
        )

    # 构建 name_en → name_cn 的查找表，用于解析 LinkType 的源/目标引用
    ot_map: dict[str, str] = {}
    for ot in object_types:
        ot_map[ot.id] = ot.name_cn
        if ot.name_en:
            ot_map[ot.name_en] = ot.name_cn

    lines: list[str] = [
        "",
        "# Schema 约束（必须遵守）",
        "",
        "本本体空间已定义以下实体类型和关系类型。这些类型定义已经存在，请勿重复创建。",
        "你的任务是：从文本中提取属于这些类型的**具体实例**，以及它们之间的**关系**、**规则**和**动作**。",
        "",
        "## ⚠️ 关键规则",
        "- object_types 字段请设为空数组 []，不要重新定义已存在的类型",
        "- 把精力集中在 object_instances：每个实例的 object_type_id 必须使用上述实体类型的 name_cn",
        "- link_types 使用上述关系类型的 name_cn，links 连接具体的 object_instances",
        "- 如果文本中出现了 Schema 未覆盖的实体类型或关系类型，可以在 object_types / link_types 中补充",
        "",
        "## ⚠️ 实例提取粒度（重要）",
        "- 装备类实体（导弹、坦克、战机、车辆等）：**每个型号只建一条 ObjectInstance**。属性填该型号的技术参数（射程、口径、速度等），不填个体状态（状态、位置、损毁等）",
        "- 部队单位、指挥所、基地、设施：每个具体单位建一条实例。属性填编制/规模数据",
        "- 不要为同一型号装备的每一枚/每一辆/每一架单独建实例",
        "- 不要给实例填个体状态字段（如状态=正常/损毁、位置=xxx），这些是参考数据，不追踪个体生命周期",
        "",
    ]

    # ── 实体类型 ──
    if object_types:
        lines.append("## 实体类型（source_type / target_type 只能从以下取值）")
        lines.append("")
        for ot in object_types:
            name = ot.name_cn
            desc = (ot.description or "").strip()
            schema = ot.property_schema or {}
            required_fields = [
                k for k, v in schema.items()
                if isinstance(v, dict) and v.get("required") is True
            ]
            optional_fields = [
                k for k, v in schema.items()
                if not isinstance(v, dict) or v.get("required") is not True
            ]
            parts: list[str] = []
            if required_fields:
                parts.append(f"必填属性: {', '.join(required_fields)}")
            if optional_fields:
                parts.append(f"可选属性: {', '.join(optional_fields)}")
            field_hint = f"  [{'; '.join(parts)}]" if parts else ""
            if desc:
                lines.append(f"- **{name}**: {desc}{field_hint}")
            else:
                lines.append(f"- **{name}**{field_hint}")
        lines.append("")

    # ── 关系类型 ──
    if link_types:
        lines.append("## 关系类型（relation 字段只能从以下取值，且必须匹配源→目标方向）")
        lines.append("")
        for lt in link_types:
            name = lt.name_cn
            desc = (lt.description or "").strip()
            src_name = ot_map.get(lt.source_object_type_id or "", "") if lt.source_object_type_id else "?"
            tgt_name = ot_map.get(lt.target_object_type_id or "", "") if lt.target_object_type_id else "?"
            direction = f"**{src_name} → {tgt_name}**" if src_name and tgt_name else "任意实体"
            if desc:
                lines.append(f"- **{name}**  ({direction}): {desc}")
            else:
                lines.append(f"- **{name}**  ({direction})")
        lines.append("")

    # ── 规则类型 ──
    lines.extend([
        "## 逻辑规则类型（logic_rules 的 logic_type 字段）",
        "",
        "- **validation**: 数据校验规则（字段非空、值域检查）",
        "- **inference**: 推理规则（IF-THEN 推导）",
        "- **state**: 状态机规则（状态流转条件）",
        "- **automation**: 自动化触发规则",
        "",
        "## 动作类型（actions 的 action_category 字段）",
        "",
        "- **crud**: 创建/更新/删除实体",
        "- **state_transition**: 状态流转操作",
        "- **link**: 关系维护操作",
        "- **review**: 人工审核确认",
        "- **repair**: 数据质量修复",
        "",
        "## 重要提示",
        "",
        "1. 实体类型字段（type / source_type / target_type）必须使用上述实体类型的 name_cn",
        "2. 关系类型字段（relations.type）必须使用上述关系类型的 name_cn",
        "3. 关系的源→目标方向必须与 Schema 中定义的方向一致",
        "4. 如果文本中出现了 Schema 未覆盖的实体/关系，可以适当补充，但请优先使用 Schema 定义的类型",
        "5. **必填属性（required）必须从文本中提取**。如果文本中没有明确信息，从上下文合理推断，标注 confidence 低于 0.7",
        "",
    ])

    return "\n".join(lines)


def _validate_required_properties(result: dict, ontology_id: str, db) -> list[str]:
    """校验提取结果中每个实体的必填属性是否都有值。

    Returns:
        警告信息列表（为空表示全部通过）
    """
    from app.models.v2.object_type import ObjectType

    object_types = db.query(ObjectType).filter(
        ObjectType.ontology_id == ontology_id
    ).all()
    if not object_types:
        return []

    # 构建 type_name → required_fields 的索引
    type_requirements: dict[str, list[str]] = {}
    for ot in object_types:
        schema = ot.property_schema or {}
        required = [
            k for k, v in schema.items()
            if isinstance(v, dict) and v.get("required") is True
        ]
        if required:
            type_requirements[ot.name_cn] = required

    if not type_requirements:
        return []  # 没有定义任何必填属性，跳过

    warnings: list[str] = []
    for entity in result.get("entities", []):
        etype = (entity.get("type") or "").strip()
        name = (entity.get("name_cn") or entity.get("name") or "?").strip()
        required = type_requirements.get(etype)
        if not required:
            continue

        props = entity.get("properties") or entity.get("attributes") or {}
        if not isinstance(props, dict):
            props = {}

        missing = [f for f in required if props.get(f) in (None, "", 0)]
        if missing:
            warnings.append(
                f"[{etype}] {name} 缺失必填属性: {', '.join(missing)}"
            )
            # 自动降低缺失必填属性的实体置信度
            current_conf = entity.get("confidence", 0.85)
            if isinstance(current_conf, (int, float)) and current_conf > 0.5:
                entity["confidence"] = round(max(0.3, current_conf - 0.15), 2)

    return warnings


def _fuzzy_resolve_entity(name: str, name_to_id: dict) -> str | None:
    """Resolve entity name to ID, falling back to substring-containment match.

    Handles cases where the LLM writes a slightly different name in relations
    than what was extracted in entities (e.g. '供应商' vs '供应商A').
    """
    if not name:
        return None
    if name in name_to_id:
        return name_to_id[name]
    # Substring containment: search name is contained in a known name, or vice versa
    candidates = [
        (kn, eid) for kn, eid in name_to_id.items()
        if kn and (name in kn or kn in name)
    ]
    if not candidates:
        return None
    # When multiple candidates, prefer the one sharing the most unique characters
    candidates.sort(key=lambda x: len(set(x[0]) & set(name)), reverse=True)
    return candidates[0][1]


@celery_app.task(bind=True)
def run_extraction(self, task_id: str):
    from app.database import SessionLocal
    from app.models import user as _user_model  # noqa: F401
    from app.models.extraction_task import ExtractionTask
    from app.models.file import UploadedFile
    from app.models.model_config import ModelConfig
    from app.models.prompt import Prompt
    from app.models.entity import Entity
    from app.models.logic import LogicRule
    from app.models.action import Action
    from app.models.relation import Relation
    from app.models.ontology import OntologyProject
    from app.services.llm_service import extract_ontology, infer_relations
    from app.services.encryption_service import decrypt
    import uuid

    db = SessionLocal()
    try:
        task = db.query(ExtractionTask).filter(ExtractionTask.id == task_id).first()
        if not task:
            return

        task.status = "running"
        task.progress = {"stage": "loading files", "pct": 10}
        db.commit()

        files = db.query(UploadedFile).filter(UploadedFile.ontology_id == task.ontology_id).all()
        if not files:
            task.status = "failed"; task.error = "No files uploaded"; db.commit(); return

        import re as _re
        from app.services.llm_service import _is_image_file

        combined_text = "\n\n---\n\n".join(f.converted_md or "" for f in files if f.converted_md)
        # Strip control characters
        combined_text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', combined_text)

        # Detect image files & resolve them to local temp paths
        image_paths: list[str] = []
        import tempfile as _tempfile
        _temp_images_to_clean: list[str] = []  # track temp files for cleanup

        for f in files:
            path = (f.file_path or "").strip()
            if not path:
                continue
            # Download from MinIO if needed
            if path.startswith("minio://"):
                try:
                    from minio import Minio
                    bucket, obj = path[8:].split("/", 1)
                    client = Minio(
                        settings.minio_endpoint,
                        access_key=settings.minio_access_key,
                        secret_key=settings.minio_secret_key,
                        secure=settings.minio_use_ssl,
                    )
                    tmp = _tempfile.NamedTemporaryFile(suffix=os.path.splitext(obj)[1], delete=False)
                    client.fget_object(bucket, obj, tmp.name)
                    tmp.close()
                    path = tmp.name
                    _temp_images_to_clean.append(path)
                except Exception:
                    path = ""
            # Fallback to local uploads dir
            if (not path or not os.path.exists(path)) and f.filename:
                path = os.path.join(settings.uploads_dir, f.filename)
            if path and os.path.exists(path) and _is_image_file(path):
                image_paths.append(path)
            # Read raw text files that don't have converted_md yet (e.g. from skill triggers)
            elif path and os.path.exists(path) and not f.converted_md:
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as rf:
                        raw_text = rf.read()
                    combined_text += "\n\n---\n\n" + _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_text)
                except Exception:
                    pass

        has_images = len(image_paths) > 0
        has_text = bool(combined_text.strip())

        if not has_text and not has_images:
            task.status = "failed"; task.error = "No text or image content found in files"; db.commit(); return

        # Resolve model config — fallback to first available
        model_cfg = db.query(ModelConfig).filter(ModelConfig.id == task.model_id).first() if task.model_id else None
        if not model_cfg:
            model_cfg = db.query(ModelConfig).order_by(ModelConfig.created_at.asc()).first()
        if not model_cfg:
            task.status = "failed"; task.error = "No model configured"; db.commit(); return

        # Resolve prompt — fallback to first available
        prompt = db.query(Prompt).filter(Prompt.id == task.prompt_id).first() if task.prompt_id else None
        if not prompt:
            prompt = db.query(Prompt).order_by(Prompt.created_at.asc()).first()
        if not prompt:
            task.status = "failed"; task.error = "No prompt configured"; db.commit(); return

        task.progress = {"stage": "calling LLM", "pct": 40}
        db.commit()

        model_name = task.parameters.get("model_name", "")
        if not model_name and model_cfg.models:
            model_name = model_cfg.models[0] if isinstance(model_cfg.models, list) else ""
        config_dict = {
            "provider": model_cfg.provider,
            "api_key":  decrypt(model_cfg.api_key_encrypted or ""),
            "api_base": model_cfg.api_base,
        }

        prompt_content = prompt.content
        # 只要求 LLM 输出实体和关系，不要编造规则和动作
        # 不再强制禁止规则/动作输出，由提示词自行控制
        # Inject prebuilt entities as constraints if provided by skill
        prebuilt = task.parameters.get("prebuilt_entities", [])
        if prebuilt:
            prebuilt_hint = "\n\n# 预定义实体（务必包含）\n请确保提取结果中包含以下实体类型：\n" + "\n".join(f"- {e}" for e in prebuilt)
            prompt_content += prebuilt_hint
        constraints = task.parameters.get("constraints", [])
        if constraints:
            prompt_content += "\n\n" + "\n".join(constraints)

        # ── Schema 注入：读取该本体的 ObjectType + LinkType，转为 LLM 约束 ─────
        schema_text = _build_schema_instructions(task.ontology_id, db)
        if schema_text:
            prompt_content += "\n\n" + schema_text
            task.progress = {"stage": "calling LLM (schema-injected)", "pct": 42}
            db.commit()

        # ── Pass 1: main extraction ──────────────────────────────────────────
        if has_images:
            from app.services.llm_service import extract_ontology_multimodal
            result = extract_ontology_multimodal(combined_text, image_paths, prompt_content, config_dict, model_name)
        else:
            result = extract_ontology(combined_text, prompt_content, config_dict, model_name)

        # ── Fix 5: calibrate confidence before validation ────────────────────
        result = _calibrate_confidence(result)

        # Save raw LLM output for debugging
        task.raw_output = result
        db.commit()

        # ── P0 validation ────────────────────────────────────────────────────
        task.progress = {"stage": "validating output", "pct": 65}
        db.commit()

        from app.engine.post_harness.validator import PostHarnessValidator
        validator = PostHarnessValidator()
        v_report  = validator.validate(result)
        task.validation_report = v_report.to_dict()
        db.commit()

        if v_report.has_fatal():
            task.status = "failed"; task.error = v_report.to_summary(); db.commit(); return

        # ── Schema 必填属性校验 ──────────────────────────────────────────────
        prop_warnings = _validate_required_properties(result, task.ontology_id, db)
        if prop_warnings:
            v_report_dict = dict(task.validation_report or {})
            existing_warnings = list(v_report_dict.get("by_severity", {}).get("warning", []))
            for msg in prop_warnings:
                existing_warnings.append({"message": msg, "type": "missing_required_property"})
            v_report_dict.setdefault("by_severity", {})["warning"] = existing_warnings
            v_report_dict["total_issues"] = v_report_dict.get("total_issues", 0) + len(prop_warnings)
            task.validation_report = v_report_dict
            db.commit()

        # ── Fix 1: second-pass relation inference ─────────────────────────────
        entities_extracted  = result.get("entities", [])
        relations_extracted = result.get("relations", [])
        entity_count    = len(entities_extracted)
        relation_count  = len(relations_extracted)

        # Count how many entities appear in at least one relation (exact or fuzzy)
        entity_names_set = {e.get("name_cn") for e in entities_extracted if e.get("name_cn")}
        in_relation: set = set()
        for r in relations_extracted:
            in_relation.add(r.get("source") or r.get("source_entity", ""))
            in_relation.add(r.get("target") or r.get("target_entity", ""))
        isolated_count = sum(
            1 for n in entity_names_set
            if n and not any(n in rn or rn in n for rn in in_relation if rn)
        )

        # Trigger when globally sparse OR >30% of entities are isolated
        sparse = relation_count < max(5, entity_count * 0.4)
        many_isolated = isolated_count > max(2, entity_count * 0.3)
        if entity_count >= 5 and (sparse or many_isolated):
            task.progress = {"stage": "inferring relations", "pct": 75}
            db.commit()
            extra_rels = infer_relations(
                entities_extracted, relations_extracted,
                combined_text, config_dict, model_name
            )
            if extra_rels:
                # Accept relations where both endpoints fuzzy-match a known entity name
                for r in extra_rels:
                    src, tgt = r.get("source", ""), r.get("target", "")
                    src_ok = src in entity_names_set or any(
                        src in n or n in src for n in entity_names_set if n)
                    tgt_ok = tgt in entity_names_set or any(
                        tgt in n or n in tgt for n in entity_names_set if n)
                    if src_ok and tgt_ok:
                        result["relations"].append(r)
                result = _calibrate_confidence(result)

        task.progress = {"stage": "saving results", "pct": 85}
        db.commit()

        # ── Cleanup pre-existing duplicates (keep best, delete extras) ────────
        _dedup_existing(db, task.ontology_id, Entity, "name_cn")
        _dedup_existing(db, task.ontology_id, LogicRule, "name_cn")
        _dedup_existing(db, task.ontology_id, Action, "name_cn")
        db.flush()

        # ── Fix 2+4: upsert entities (by name_cn) ────────────────────────────
        existing_entities = db.query(Entity).filter(Entity.ontology_id == task.ontology_id).all()
        existing_ent_map  = {e.name_cn: e for e in existing_entities}

        entity_name_to_id: dict = {e.name_cn: e.id for e in existing_entities}
        for e in existing_entities:
            if e.name_en:
                entity_name_to_id[e.name_en] = e.id

        for e_data in result.get("entities", []):
            name_cn = e_data.get("name_cn") or e_data.get("name", "")
            if not name_cn:
                continue
            props = e_data.get("properties") or e_data.get("attributes") or e_data.get("attrs") or {}
            if not isinstance(props, dict):
                props = {}

            if name_cn in existing_ent_map:
                # Upsert: update fields that improved
                ent = existing_ent_map[name_cn]
                if e_data.get("type"):        ent.type        = e_data["type"]
                if e_data.get("description"): ent.description = e_data["description"]
                if props:                     ent.properties  = props
                if e_data.get("name_en"):     ent.name_en     = e_data["name_en"]
                # Phase 1 结构化: property_schema（值非空时才覆盖）
                property_schema = e_data.get("property_schema")
                if property_schema and isinstance(property_schema, dict) and len(property_schema) > 0:
                    ent.property_schema = property_schema
                ent.confidence = e_data.get("confidence", ent.confidence)
                eid = ent.id
            else:
                eid = str(uuid.uuid4())
                pschema = e_data.get("property_schema")
                if not isinstance(pschema, dict):
                    pschema = {}
                ent = Entity(
                    id=eid, ontology_id=task.ontology_id,
                    name_cn=name_cn, name_en=e_data.get("name_en"),
                    type=e_data.get("type"), description=e_data.get("description"),
                    properties=props, property_schema=pschema,
                    confidence=e_data.get("confidence", 0.85),
                )
                db.add(ent)
                existing_ent_map[name_cn] = ent

            entity_name_to_id[name_cn] = eid
            if e_data.get("name_en"):
                entity_name_to_id[e_data["name_en"]] = eid

        # ── Fix 2+4: upsert relations (by source_id, target_id, type) ────────
        existing_rels    = db.query(Relation).filter(Relation.ontology_id == task.ontology_id).all()
        existing_rel_set = {(r.source_entity, r.target_entity, r.type) for r in existing_rels}

        for rel in result.get("relations", []):
            src_name = rel.get("source") or rel.get("source_entity", "")
            tgt_name = rel.get("target") or rel.get("target_entity", "")
            src_id   = _fuzzy_resolve_entity(src_name, entity_name_to_id)
            tgt_id   = _fuzzy_resolve_entity(tgt_name, entity_name_to_id)
            rel_type = rel.get("type", "关联")
            if src_id and tgt_id and (src_id, tgt_id, rel_type) not in existing_rel_set:
                db.add(Relation(
                    id=str(uuid.uuid4()), ontology_id=task.ontology_id,
                    source_entity=src_id, target_entity=tgt_id,
                    type=rel_type, confidence=rel.get("confidence", 0.85),
                ))
                existing_rel_set.add((src_id, tgt_id, rel_type))

        # ── 桥接：如果 LLM 返回的是 Phase 2 object_instances 而非 v1 entities，自动转换 ──
        v1_entities = result.get("entities", [])
        if not v1_entities and result.get("object_instances"):
            converted_entities: list[dict] = []
            for oi in result.get("object_instances", []):
                if not isinstance(oi, dict):
                    continue
                converted_entities.append({
                    "name_cn": oi.get("name_cn", ""),
                    "name_en": oi.get("name_en", ""),
                    "type": oi.get("object_type_id", "Entity"),
                    "description": oi.get("description", ""),
                    "properties": oi.get("properties", {}),
                    "confidence": oi.get("confidence", 0.85),
                })
            # 把这些转换来的实体也写入 v1 entities 表
            for e_data in converted_entities:
                name_cn = e_data.get("name_cn", "")
                if not name_cn:
                    continue
                if name_cn in existing_ent_map:
                    ent = existing_ent_map[name_cn]
                    if e_data.get("type"):
                        ent.type = e_data["type"]
                    if e_data.get("properties"):
                        ent.properties = e_data["properties"]
                    ent.confidence = e_data.get("confidence", ent.confidence)
                else:
                    eid = str(uuid.uuid4())
                    ent = Entity(
                        id=eid, ontology_id=task.ontology_id,
                        name_cn=name_cn, name_en=e_data.get("name_en"),
                        type=e_data.get("type"), description=e_data.get("description"),
                        properties=e_data.get("properties", {}),
                        confidence=e_data.get("confidence", 0.85),
                    )
                    db.add(ent)
                    existing_ent_map[name_cn] = ent
                entity_name_to_id[name_cn] = ent.id
                if e_data.get("name_en"):
                    entity_name_to_id[e_data["name_en"]] = ent.id
            # 刷新 entity_name_to_id 以便后续 v1 关系匹配
            for e in existing_ent_map.values():
                entity_name_to_id[e.name_cn] = e.id
                if e.name_en:
                    entity_name_to_id[e.name_en] = e.id

        v1_relations = result.get("relations", [])
        if not v1_relations and result.get("links"):
            # 构建 instance temp_id → name_cn 的查找表
            inst_id_to_name: dict[str, str] = {}
            for oi in result.get("object_instances", []):
                if not isinstance(oi, dict):
                    continue
                name = oi.get("name_cn", "")
                tid = oi.get("temp_id") or oi.get("id", "")
                if name:
                    inst_id_to_name[tid] = name
                    inst_id_to_name[name] = name
            for link in result.get("links", []):
                if not isinstance(link, dict):
                    continue
                src_name = inst_id_to_name.get(
                    link.get("source_instance_temp_id") or link.get("source_instance_id", ""),
                    link.get("source_instance_temp_id", "")
                )
                tgt_name = inst_id_to_name.get(
                    link.get("target_instance_temp_id") or link.get("target_instance_id", ""),
                    link.get("target_instance_temp_id", "")
                )
                rel_type = link.get("type") or link.get("relation") or "关联"
                src_id = entity_name_to_id.get(src_name)
                tgt_id = entity_name_to_id.get(tgt_name)
                if src_id and tgt_id and (src_id, tgt_id, rel_type) not in existing_rel_set:
                    db.add(Relation(
                        id=str(uuid.uuid4()), ontology_id=task.ontology_id,
                        source_entity=src_id, target_entity=tgt_id,
                        type=rel_type, confidence=link.get("confidence", 0.85),
                    ))
                    existing_rel_set.add((src_id, tgt_id, rel_type))

        # ── Keyword matching helpers (unchanged) ─────────────────────────────
        all_entity_names = [
            e.get("name_cn") or e.get("name", "")
            for e in result.get("entities", [])
            if e.get("name_cn") or e.get("name")
        ]
        type_to_entities: dict = {}
        for e in result.get("entities", []):
            etype = (e.get("type") or "").lower()
            ename = e.get("name_cn") or e.get("name", "")
            if ename:
                type_to_entities.setdefault(etype, []).append(ename)

        TYPE_KEYWORDS: dict = {
            "supplier": ["供应商","供货商","厂商","卖方"],
            "material": ["物料","原材料","辅料","零部件","库存"],
            "warehouse": ["仓库","库存","存储","盘点","入库","出库"],
            "product":  ["产品","成品","半成品","货物","质量","合格"],
            "document": ["订单","采购单","合同","审批","单据"],
            "process":  ["流程","工艺","步骤","采购","质检","物流"],
        }
        STOP_CHARS = set("的和在是了或且，。、（）[]【】")

        def _match_entities(text: str, entity_names: list) -> list:
            if not text: return []
            exact = [n for n in entity_names if n and n in text]
            if exact: return exact
            matched: list = []
            for etype, keywords in TYPE_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    matched.extend(type_to_entities.get(etype, []))
            return list(dict.fromkeys(matched))[:6]

        def _match_logic_rules(text: str, logic_name_to_id: dict) -> list:
            if not text: return []
            text_chars = set(text) - STOP_CHARS
            return [lid for lname, lid in logic_name_to_id.items()
                    if len(text_chars & (set(lname) - STOP_CHARS)) >= 2]

        # ── Phase 1 结构化: 构建 name_en → property_schema 查找表 ──────────
        # 重新查询所有实体（含本次新增），用于校验 conditions/submission_criteria 的 field
        all_ent_for_validation = db.query(Entity).filter(Entity.ontology_id == task.ontology_id).all()
        name_en_to_property_schema: dict = {}
        for e in all_ent_for_validation:
            if e.name_en and e.property_schema and isinstance(e.property_schema, dict):
                name_en_to_property_schema[e.name_en] = e.property_schema

        def _validate_field_against_schema(field: str, target_name_en: str, linked_names: list) -> tuple:
            """校验 field 是否存在于目标实体的 property_schema 中。
            返回 (valid: bool, found_in: str|None)"""
            if not field:
                return False, None
            # 优先检查 target_entity_type 对应实体的 property_schema
            if target_name_en:
                schema = name_en_to_property_schema.get(target_name_en)
                if schema and field in schema:
                    return True, target_name_en
            # 回退：检查 linked_entities 中每个实体的 property_schema
            for name in (linked_names or []):
                schema = name_en_to_property_schema.get(name)
                if schema and field in schema:
                    return True, name
            return False, None

        # ── Fix 2+4: upsert logic rules (by name_cn) ─────────────────────────
        existing_rules    = db.query(LogicRule).filter(LogicRule.ontology_id == task.ontology_id).all()
        existing_rule_map = {r.name_cn: r for r in existing_rules}
        logic_name_to_id: dict = {r.name_cn: r.id for r in existing_rules}

        for r_data in result.get("logic_rules", []):
            name_cn = r_data.get("name_cn") or r_data.get("name", "")
            if not name_cn:
                continue

            llm_linked = r_data.get("linked_entities", [])
            if not llm_linked:
                combined = " ".join(filter(None, [name_cn, r_data.get("formula",""), r_data.get("description","")]))
                llm_linked = _match_entities(combined, all_entity_names)

            if name_cn in existing_rule_map:
                rule = existing_rule_map[name_cn]
                if r_data.get("formula"):     rule.formula     = r_data["formula"]
                if r_data.get("description"): rule.description = r_data["description"]
                if llm_linked:                rule.linked_entities = llm_linked
                if r_data.get("name_en"):     rule.name_en     = r_data["name_en"]
                rule.confidence = r_data.get("confidence", rule.confidence)
                # Phase 1 结构化: conditions
                conditions = r_data.get("conditions")
                if conditions and isinstance(conditions, list):
                    rule.conditions = conditions
                    # 校验每个 condition 的 field
                    for c in conditions:
                        if isinstance(c, dict) and c.get("field"):
                            valid, _ = _validate_field_against_schema(
                                c["field"], None, llm_linked or rule.linked_entities or []
                            )
                            if not valid:
                                rule.needs_review = True
                                break
                rid = rule.id
            else:
                rid  = str(uuid.uuid4())
                conditions = r_data.get("conditions")
                if not isinstance(conditions, list):
                    conditions = []
                # 校验 conditions
                needs_review = False
                for c in conditions:
                    if isinstance(c, dict) and c.get("field"):
                        valid, _ = _validate_field_against_schema(
                            c["field"], None, llm_linked or []
                        )
                        if not valid:
                            needs_review = True
                            break
                rule = LogicRule(
                    id=rid, ontology_id=task.ontology_id,
                    name_cn=name_cn, name_en=r_data.get("name_en"),
                    description=r_data.get("description"), formula=r_data.get("formula"),
                    conditions=conditions, needs_review=needs_review,
                    confidence=r_data.get("confidence", 0.85),
                )
                rule.linked_entities = llm_linked
                db.add(rule)
                existing_rule_map[name_cn] = rule

            logic_name_to_id[name_cn] = rid

        # ── Fix 2+4: upsert actions (by name_cn) ─────────────────────────────
        existing_actions    = db.query(Action).filter(Action.ontology_id == task.ontology_id).all()
        existing_action_map = {a.name_cn: a for a in existing_actions}

        for a_data in result.get("actions", []):
            name_cn = a_data.get("name_cn") or a_data.get("name", "")
            if not name_cn:
                continue

            linked_ents = a_data.get("linked_entities", [])
            if not linked_ents:
                combined = " ".join(filter(None, [name_cn, a_data.get("execution_rule",""), a_data.get("description","")]))
                linked_ents = _match_entities(combined, all_entity_names)

            linked_logic_names = a_data.get("linked_logic_names", [])
            linked_ids = [logic_name_to_id[n] for n in linked_logic_names if n in logic_name_to_id]
            linked_ids += [i for i in a_data.get("linked_logic_ids", []) if i not in linked_ids]
            if not linked_ids:
                action_text = " ".join(filter(None, [name_cn, a_data.get("execution_rule",""), a_data.get("description","")]))
                linked_ids = _match_logic_rules(action_text, logic_name_to_id)

            if name_cn in existing_action_map:
                act = existing_action_map[name_cn]
                if a_data.get("description"):    act.description    = a_data["description"]
                if a_data.get("execution_rule"): act.execution_rule = a_data["execution_rule"]
                if a_data.get("function_code"):  act.function_code  = a_data["function_code"]
                if a_data.get("name_en"):        act.name_en        = a_data["name_en"]
                if linked_ents:  act.linked_entities  = linked_ents
                if linked_ids:   act.linked_logic_ids = linked_ids
                act.confidence = a_data.get("confidence", act.confidence)
                # Phase 1 结构化: submission_criteria + target_entity_type
                target_type = a_data.get("target_entity_type")
                criteria = a_data.get("submission_criteria")
                act_needs_review = False
                if target_type:
                    act.target_entity_type = target_type
                    # 校验 target_entity_type 是否存在于任何实体的 name_en
                    if target_type not in name_en_to_property_schema:
                        act_needs_review = True
                if criteria and isinstance(criteria, list):
                    act.submission_criteria = criteria
                    for c in criteria:
                        if isinstance(c, dict) and c.get("field"):
                            valid, _ = _validate_field_against_schema(
                                c["field"], target_type, linked_ents or []
                            )
                            if not valid:
                                act_needs_review = True
                                break
                if act_needs_review:
                    act.needs_review = True
            else:
                # Phase 1 结构化: 校验 submission_criteria + target_entity_type
                target_type = a_data.get("target_entity_type")
                criteria = a_data.get("submission_criteria")
                if not isinstance(criteria, list):
                    criteria = []
                act_needs_review = False
                if target_type:
                    if target_type not in name_en_to_property_schema:
                        act_needs_review = True
                for c in criteria:
                    if isinstance(c, dict) and c.get("field"):
                        valid, _ = _validate_field_against_schema(
                            c["field"], target_type, linked_ents or []
                        )
                        if not valid:
                            act_needs_review = True
                            break
                act = Action(
                    id=str(uuid.uuid4()), ontology_id=task.ontology_id,
                    name_cn=name_cn, name_en=a_data.get("name_en"),
                    description=a_data.get("description"), execution_rule=a_data.get("execution_rule"),
                    function_code=a_data.get("function_code"),
                    linked_entities=linked_ents, linked_logic_ids=linked_ids,
                    submission_criteria=criteria, target_entity_type=target_type,
                    needs_review=act_needs_review,
                    confidence=a_data.get("confidence", 0.85),
                )
                db.add(act)
                existing_action_map[name_cn] = act

        # ── Phase 2: 如果 LLM 返回了 object_types/object_instances，写入新表 ──
        if result.get("object_types") or result.get("object_instances"):
            try:
                task.progress = {"stage": "saving Phase 2", "pct": 88}
                db.commit()

                from app.models.v2.object_type import ObjectType as OT, ObjectInstance as OI
                from app.models.v2.object_type import Interface as IF, LinkType as LT, Link

                # 临时ID → 真实UUID 映射
                temp_ot_map: dict = {}
                temp_inst_map: dict = {}
                temp_lt_map: dict = {}
                _llm_oi_map: dict = {}

                # 1. 写 Interfaces
                for i_data in result.get("interfaces", []):
                    iid = str(uuid.uuid4())
                    db.add(IF(id=iid, ontology_id=task.ontology_id,
                              name_cn=i_data.get("name_cn",""), name_en=i_data.get("name_en"),
                              description=i_data.get("description"),
                              shared_properties=i_data.get("shared_properties", [])))

                # 2. 写 ObjectTypes
                for idx, ot_data in enumerate(result.get("object_types", [])):
                    ot_id = str(uuid.uuid4())
                    temp_id = ot_data.get("temp_id") or ot_data.get("id") or f"ot-{idx+1}"
                    temp_ot_map[temp_id] = ot_id
                    db.add(OT(id=ot_id, ontology_id=task.ontology_id,
                              name_cn=ot_data.get("name_cn",""), name_en=ot_data.get("name_en"),
                              description=ot_data.get("description"),
                              property_schema=ot_data.get("property_schema", {}),
                              interface_ids=ot_data.get("interface_ids", [])))

                # 3a. 先写非批量实例，收集批量实例待展开
                _bulk_instances: list = []  # (oi_data, oi_id)
                for idx, oi_data in enumerate(result.get("object_instances", [])):
                    oi_id = str(uuid.uuid4())
                    bulk_count = oi_data.get("bulk_count")
                    name_cn = oi_data.get("name_cn", "")
                    name_en = oi_data.get("name_en", "")

                    # 收集 LLM 所有可能的 ID 格式
                    llm_keys = [str(v) for v in [oi_data.get("temp_id"), oi_data.get("id")] if v]
                    if name_cn: llm_keys.append(name_cn)
                    if name_en: llm_keys.append(name_en)
                    if not llm_keys: llm_keys.append(f"inst-{idx+1}")

                    ot_temp = oi_data.get("object_type_id") or oi_data.get("object_type_temp_id", "")
                    real_ot_id = temp_ot_map.get(ot_temp, ot_temp)
                    props = oi_data.get("properties", {})

                    if isinstance(bulk_count, int) and bulk_count > 1:
                        # 批量实例：记录待展开，先存模板信息
                        damaged = oi_data.get("bulk_damaged", 0)
                        pattern = oi_data.get("bulk_pattern") or f"{name_en}_{{i:03d}}"
                        props_tpl = oi_data.get("properties_template") or props
                        # 生成所有个体实例
                        for i in range(1, bulk_count + 1):
                            bi_id = str(uuid.uuid4())
                            bi_name = f"{name_cn}#{i:03d}" if name_cn else pattern.format(i=i)
                            status = "损毁" if i <= damaged else "正常"
                            bi_props = {}
                            for k, v in props_tpl.items():
                                if isinstance(v, str):
                                    bi_props[k] = v.replace("{i:04d}", f"{i:04d}").replace("{i:03d}", f"{i:03d}").replace("{i}", str(i)).replace("{status}", status)
                                else:
                                    bi_props[k] = v
                            bi_props["状态"] = status
                            bi_props["批量序号"] = i
                            db.add(OI(id=bi_id, ontology_id=task.ontology_id,
                                      object_type_id=real_ot_id,
                                      name_cn=bi_name,
                                      name_en=pattern.format(i=i) if "{" in pattern else f"{name_en}_{i:03d}",
                                      description=oi_data.get("description", ""),
                                      properties=bi_props))
                            # 把展开后的实例也加入 ID 映射（Link 需要引用）
                            for k in llm_keys:
                                _llm_oi_map[f"{k}#{i:03d}"] = bi_id
                                _llm_oi_map[f"{k}-{i}"] = bi_id
                            _llm_oi_map[bi_name] = bi_id
                        # 模板实例不用真实写入（只是占位），但保留 ID 映射让 Link 引用
                        _bulk_instances.append((oi_data, oi_id, bulk_count, damaged, ot_temp, real_ot_id))
                    else:
                        db.add(OI(id=oi_id, ontology_id=task.ontology_id,
                                  object_type_id=real_ot_id,
                                  name_cn=name_cn, name_en=name_en,
                                  description=oi_data.get("description", ""),
                                  properties=props))
                        for k in llm_keys:
                            _llm_oi_map[k] = oi_id
                        temp_inst_map[f"inst-{idx+1}"] = oi_id

                db.flush()

                # 4. 写 LinkTypes
                for idx, lt_data in enumerate(result.get("link_types", [])):
                    lt_id = str(uuid.uuid4())
                    temp_id = lt_data.get("temp_id") or lt_data.get("id") or f"lt-{idx+1}"
                    temp_lt_map[temp_id] = lt_id
                    # 尝试解析 source/target object_type ID（LLM 可能用各种方式引用）
                    src_raw = lt_data.get("source_object_type_temp_id") or lt_data.get("source_object_type_id", "")
                    tgt_raw = lt_data.get("target_object_type_temp_id") or lt_data.get("target_object_type_id", "")
                    src_ot_id = temp_ot_map.get(str(src_raw)) if src_raw else None
                    tgt_ot_id = temp_ot_map.get(str(tgt_raw)) if tgt_raw else None
                    # 回退：尝试在已写入的 object_types 中按 name_en 查找
                    if not src_ot_id and src_raw:
                        for tid, tname in [(ot_id, ot_name) for ot_id, ot_name in [(t.id, t.name_en) for t in db.query(OT).filter(OT.ontology_id == task.ontology_id).all()]]:
                            if tname and str(src_raw).lower() == tname.lower():
                                src_ot_id = tid; break
                    if not tgt_ot_id and tgt_raw:
                        for tid, tname in [(ot_id, ot_name) for ot_id, ot_name in [(t.id, t.name_en) for t in db.query(OT).filter(OT.ontology_id == task.ontology_id).all()]]:
                            if tname and str(tgt_raw).lower() == tname.lower():
                                tgt_ot_id = tid; break
                    db.add(LT(id=lt_id, ontology_id=task.ontology_id,
                              name_cn=lt_data.get("name_cn",""), name_en=lt_data.get("name_en"),
                              description=lt_data.get("description"),
                              source_object_type_id=src_ot_id,
                              target_object_type_id=tgt_ot_id))

                # 先 flush instances，然后按名称映射 ID
                db.flush()
                # 构建 name_cn → id 和 name_en → id 的实例查找表
                inst_name_to_id: dict = {}
                for oi in db.query(OI).filter(OI.ontology_id == task.ontology_id).all():
                    if oi.name_cn: inst_name_to_id[oi.name_cn] = oi.id
                    if oi.name_en: inst_name_to_id[oi.name_en] = oi.id
                    # 也按 properties 中的序列号/编号匹配
                    for v in (oi.properties or {}).values():
                        if isinstance(v, str) and len(v) > 2:
                            inst_name_to_id[str(v)] = oi.id

                # 同样给 link_types 按名称建映射（因为 LLM 输出可能用 link type name）
                lt_name_to_id: dict = {}
                for lt in db.query(LT).filter(LT.ontology_id == task.ontology_id).all():
                    if lt.name_cn: lt_name_to_id[lt.name_cn] = lt.id
                    if lt.name_en: lt_name_to_id[lt.name_en] = lt.id

                # 5. 写 Links
                for l_data in result.get("links", []):
                    # 解析 link_type
                    lt_raw = l_data.get("link_type_temp_id") or l_data.get("link_type_id", "")
                    real_lt = temp_lt_map.get(str(lt_raw)) or lt_name_to_id.get(str(lt_raw), lt_raw)

                    # 解析 source/target instance：_llm_oi_map 优先（LLM 的原始引用）
                    src_raw = l_data.get("source_instance_temp_id") or l_data.get("source_instance_id", "")
                    tgt_raw = l_data.get("target_instance_temp_id") or l_data.get("target_instance_id", "")
                    real_src = _llm_oi_map.get(str(src_raw)) or inst_name_to_id.get(str(src_raw), src_raw)
                    real_tgt = _llm_oi_map.get(str(tgt_raw)) or inst_name_to_id.get(str(tgt_raw), tgt_raw)

                    if real_src and real_tgt and real_lt:
                        db.add(Link(id=str(uuid.uuid4()), ontology_id=task.ontology_id,
                                    link_type_id=str(real_lt),
                                    source_instance_id=str(real_src),
                                    target_instance_id=str(real_tgt)))

                db.flush()
            except Exception as e:
                task.progress = {"stage": "Phase 2 save failed (non-fatal)", "pct": 88, "error": str(e)[:200]}

        project = db.query(OntologyProject).filter(OntologyProject.id == task.ontology_id).first()
        if project:
            project.status = "created"

        task.status   = "completed"
        task.progress = {"stage": "done", "pct": 100}
        db.commit()

        try:
            from app.services.v2.graph.neo4j_service import Neo4jService
            neo = Neo4jService()
            if neo.available:
                synced_entities = neo.batch_upsert_entities("OntologyEntity", [
                    {
                        "id": e.id,
                        "source_id": e.id,
                        "ontology_id": task.ontology_id,
                        "name_cn": e.name_cn or "",
                        "name_en": e.name_en or "",
                        "name": e.name_cn or "",
                        "type": e.type or "",
                        "description": e.description or "",
                        "confidence": e.confidence or 1.0,
                        "version": e.version or "v0.1",
                        **(e.properties or {}),
                    }
                    for e in db.query(Entity).filter(Entity.ontology_id == task.ontology_id).all()
                ], key_field="id")
                synced_relations = 0
                for r in db.query(Relation).filter(Relation.ontology_id == task.ontology_id).all():
                    if neo.upsert_relation(
                        "OntologyEntity", r.source_entity,
                        "OntologyEntity", r.target_entity,
                        (r.type or "RELATED").upper().replace(" ", "_").replace("-", "_"),
                        props={"ontology_id": task.ontology_id, "confidence": r.confidence or 1.0},
                    ):
                        synced_relations += 1
                task.progress = {"stage": "done", "pct": 100, "neo4j_synced": synced_entities + synced_relations}
                db.commit()
                neo.close()
        except Exception:
            pass  # Neo4j sync is best-effort, don't fail the extraction

    except Exception as e:
        db.rollback()
        task = db.query(ExtractionTask).filter(ExtractionTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error  = str(e)
            db.commit()
    finally:
        db.close()
