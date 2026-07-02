"""
Celery 全局实例 — 所有任务模块（extraction、webhook 等）共用此实例。
启动 worker: celery -A app.tasks worker --loglevel=info
"""
from celery import Celery
from app.config import settings

celery_app = Celery("ontoprompt", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_publish_retry = False
celery_app.conf.broker_connection_timeout = 3

# 显式导入所有任务模块，确保 Celery worker 能发现注册
from app.tasks import extraction   # noqa: E402, F401 — 抽取任务
from app.tasks import webhook     # noqa: E402, F401 — Webhook 推送任务
