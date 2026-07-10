import json
import re
import base64
import os
from typing import Any

# Image mime types that can be passed to vision LLMs
IMAGE_MIME_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
    "image/tiff", "image/tif",
}

def _is_image_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".tif", ".bmp"}

def _encode_image(file_path: str) -> str:
    """Read image file and return base64 data-URL string."""
    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    ext = os.path.splitext(file_path)[1].lower()
    mime = mime_map.get(ext, "image/png")
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def extract_ontology(text: str, prompt_content: str, model_config: dict, model_name: str, retry_count: int = 3) -> dict:
    provider = model_config.get("provider", "openai")
    api_key = model_config.get("api_key", "")
    api_base = model_config.get("api_base")

    messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": f"请从以下文档中提取本体信息，以JSON格式返回：\n\n{text}"},
    ]

    for attempt in range(retry_count):
        try:
            raw = _call_llm(provider, api_key, api_base, model_name, messages)
            return _parse_response(raw)
        except Exception as e:
            if attempt == retry_count - 1:
                raise
    return {}


def extract_ontology_multimodal(
    text: str,
    image_paths: list[str],
    prompt_content: str,
    model_config: dict,
    model_name: str,
    retry_count: int = 3,
) -> dict:
    """Extract ontology from text + images using a vision-capable LLM."""
    provider = model_config.get("provider", "openai")
    api_key = model_config.get("api_key", "")
    api_base = model_config.get("api_base")

    # Build multimodal user content
    user_content: list[dict] = []
    if text.strip():
        user_content.append({"type": "text", "text": f"请从以下情报中提取本体信息，以JSON格式返回：\n\n{text}"})
    else:
        user_content.append({"type": "text", "text": "请从以下图像中提取本体信息，以JSON格式返回："})

    for img_path in image_paths:
        try:
            data_url = _encode_image(img_path)
            user_content.append({"type": "image_url", "image_url": {"url": data_url}})
        except Exception:
            pass  # skip unreadable images

    messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": user_content},
    ]

    for attempt in range(retry_count):
        try:
            raw = _call_llm(provider, api_key, api_base, model_name, messages, json_mode=True)
            return _parse_response(raw)
        except Exception as e:
            if attempt == retry_count - 1:
                raise
    return {}


def infer_relations(entities: list, existing_relations: list, text: str,
                    model_config: dict, model_name: str) -> list:
    """Second-pass relation inference: find IS-A / PART-OF / INSTANCE-OF links the first pass missed."""
    if len(entities) < 3:
        return []

    provider  = model_config.get("provider", "openai")
    api_key   = model_config.get("api_key", "")
    api_base  = model_config.get("api_base")

    # Build entity snapshot (limit to 50 to keep prompt manageable)
    entity_lines = "\n".join(
        f"- {e.get('name_cn','?')} ({e.get('type','?')}): {(e.get('description') or '')[:60]}"
        for e in entities[:50]
    )
    existing_set = {
        (r.get("source"), r.get("type"), r.get("target"))
        for r in existing_relations
        if r.get("source") and r.get("target")
    }

    system_prompt = (
        "你是本体关系补全专家。给定已提取实体列表和原始文档，找出实体间遗漏的层级和关联关系。\n\n"
        "关系类型（只能使用以下类型）：IS-A、PART-OF、INSTANCE-OF、supply、stores、processes、treats、causes、关联\n\n"
        "重点寻找：\n"
        "1. IS-A：A 是 B 的一种（如 销售费用 IS-A 费用）\n"
        "2. PART-OF：A 是 B 的组成部分（如 流动资产 PART-OF 资产）\n"
        "3. INSTANCE-OF：A 是 B 的具体实例（如 华为供应链 INSTANCE-OF S级战略客户）\n\n"
        "要求：\n"
        "- 只输出新发现的关系，不要重复已有关系\n"
        "- source 和 target 必须是实体列表中的 name_cn\n"
        "- 每对实体最多一条关系\n"
        "- 至少找 10 条，最多 30 条\n\n"
        '返回 JSON（不要有其他文字）：{"relations": [{"source": "A", "target": "B", "type": "IS-A", "confidence": 0.85}]}'
    )
    user_msg = (
        f"已提取实体：\n{entity_lines}\n\n"
        f"文档节选：\n{text[:2500]}"
    )

    try:
        raw = _call_llm(provider, api_key, api_base, model_name,
                        [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user_msg}])
        parsed = _parse_response(raw)
        candidates = parsed.get("relations", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])

        new_rels = []
        for r in candidates:
            if not isinstance(r, dict):
                continue
            key = (r.get("source"), r.get("type"), r.get("target"))
            if key[0] and key[2] and key not in existing_set:
                new_rels.append(r)
                existing_set.add(key)
        return new_rels
    except Exception:
        return []  # relation inference failure is non-fatal


def _call_llm(provider: str, api_key: str, api_base: str | None, model: str, messages: list, json_mode: bool = True) -> str:
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=32768,
            system=messages[0]["content"],
            messages=[{"role": "user", "content": messages[1]["content"] + ("\n\n```json\n{" if json_mode else "")}],
        )
        return ("{" + resp.content[0].text) if json_mode else resp.content[0].text
    else:
        import openai
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        elif provider == "compatible":
            kwargs["api_key"] = "dummy"
        if api_base:
            kwargs["base_url"] = api_base
        client = openai.OpenAI(**kwargs)
        create_kwargs: dict = {"model": model, "messages": messages, "timeout": 300, "max_tokens": 32768}
        if json_mode:
            create_kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**create_kwargs)
        return resp.choices[0].message.content or ""


def _parse_response(raw: str) -> dict:
    if not raw:
        raise ValueError("Empty LLM response")

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    text = raw.strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?```\s*$', '', text).strip()

    # Remove control characters that are illegal inside JSON strings
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Fast path: well-formed JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try json_repair (handles unescaped quotes, truncated output, etc.)
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        result = json.loads(repaired)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    # Last resort: slice from first { to last } and try again
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse LLM response as JSON: {raw[:300]}")
