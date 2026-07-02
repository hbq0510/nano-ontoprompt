"""
通用 Webhook 异步推送任务 — 全局可复用，任意业务接口均可调用。

使用方式:
    from app.tasks.webhook import send_webhook
    send_webhook.delay(target_url="https://example.com/hook", payload={"key": "value"})

设计原则:
    - 与情报抽取业务完全解耦，不依赖任何特定数据模型
    - 失败自动重试，完整的异常捕获和可观测日志
    - 预留多地址、自定义请求头、数据库日志等扩展点
"""
import logging
import httpx
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def send_webhook(
    self,
    target_url: str,
    payload: dict,
    timeout: int = 10,
    retry_times: int = 2,
    headers: dict | None = None,
):
    """
    通用 Webhook 异步推送任务。

    Args:
        target_url:   目标 webhook 地址（兼容任意第三方接收地址）
        payload:      任意业务结构化数据，不限制格式
        timeout:      HTTP 请求超时秒数，默认 10 秒
        retry_times:  失败自动重试次数，默认 2 次
        headers:      自定义请求头，默认 {"Content-Type": "application/json"}
                      【扩展点】对接带鉴权的第三方系统时传入 Token/签名头

    Returns:
        dict: {"status": "ok", "status_code": 200, "url": target_url}
              或 {"status": "failed", "error": "...", "url": target_url}

    异常处理:
        - 网络超时、连接失败、4xx/5xx、域名解析失败全部捕获
        - 按 retry_times 自动重试，重试耗尽后输出 FATAL 日志
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}

    # 载荷摘要（截断过长内容，保护日志可读性）
    payload_preview = str(payload)
    if len(payload_preview) > 500:
        payload_preview = payload_preview[:500] + "..."

    logger.info(
        "[webhook] dispatching POST to %s | payload preview: %s",
        target_url, payload_preview,
    )

    try:
        resp = httpx.post(
            target_url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        # 4xx/5xx 也视为失败，触发重试
        resp.raise_for_status()

        logger.info(
            "[webhook] success | target=%s | status=%s | payload_size=%d",
            target_url, resp.status_code, len(str(payload)),
        )
        return {"status": "ok", "status_code": resp.status_code, "url": target_url}

    except httpx.TimeoutException as e:
        logger.warning(
            "[webhook] timeout | target=%s | timeout=%ds | err=%s",
            target_url, timeout, str(e),
        )
        if self.request.retries < retry_times:
            raise self.retry(exc=e)
        logger.error("[webhook] FATAL after %d retries (timeout) | target=%s", retry_times, target_url)
        return {"status": "failed", "error": f"timeout after {retry_times} retries", "url": target_url}

    except httpx.ConnectError as e:
        logger.warning(
            "[webhook] connection error | target=%s | err=%s", target_url, str(e),
        )
        if self.request.retries < retry_times:
            raise self.retry(exc=e)
        logger.error("[webhook] FATAL after %d retries (connection) | target=%s", retry_times, target_url)
        return {"status": "failed", "error": f"connection failed after {retry_times} retries", "url": target_url}

    except httpx.HTTPStatusError as e:
        logger.warning(
            "[webhook] HTTP error | target=%s | status=%s | err=%s",
            target_url, e.response.status_code, str(e),
        )
        if self.request.retries < retry_times:
            raise self.retry(exc=e)
        logger.error("[webhook] FATAL after %d retries (http) | target=%s", retry_times, target_url)
        return {"status": "failed", "error": str(e), "url": target_url}

    except httpx.RequestError as e:
        logger.warning(
            "[webhook] request error | target=%s | err=%s", target_url, str(e),
        )
        if self.request.retries < retry_times:
            raise self.retry(exc=e)
        logger.error("[webhook] FATAL after %d retries (request) | target=%s", retry_times, target_url)
        return {"status": "failed", "error": str(e), "url": target_url}

    except Exception as e:
        logger.error(
            "[webhook] unexpected error | target=%s | err=%s | traceback=%s",
            target_url, str(e), getattr(e, "__traceback__", ""),
        )
        return {"status": "failed", "error": str(e), "url": target_url}


# ══════════════════════════════════════════════════════════════════════
# 扩展预留（后续需求无需重写代码，在此处扩展即可）
# ══════════════════════════════════════════════════════════════════════

def _parse_multi_urls(url_string: str) -> list[str]:
    """
    【扩展点】单本体多 webhook 地址解析。
    支持逗号 / 分号 / 换行分隔，后续前端多填地址即可批量推送。
    当前仅预留，未在业务中启用。
    """
    if not url_string or not url_string.strip():
        return []
    parts = [s.strip() for s in url_string.replace(";", ",").replace("\n", ",").split(",")]
    return [p for p in parts if p]


# 【扩展点】推送日志落地数据库
# 后续可在 send_webhook 任务末尾调用以下函数，将推送结果写入
# webhook_logs 表（需新建对应 ORM 模型），用于业务溯源和运维排查。
#
# def _save_webhook_log(
#     target_url: str, payload: dict, status: str,
#     error: str | None, celery_task_id: str,
# ):
#     from app.database import SessionLocal
#     from app.models.webhook_log import WebhookLog  # 需新建模型
#     db = SessionLocal()
#     try:
#         log = WebhookLog(
#             target_url=target_url,
#             payload=payload,
#             status=status,
#             error=error,
#             celery_task_id=celery_task_id,
#         )
#         db.add(log)
#         db.commit()
#     finally:
#         db.close()
