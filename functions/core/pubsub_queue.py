import json
import os


TELEGRAM_TOOL_TOPIC = "hermes-telegram-tool-dispatch"


def _get_project_id() -> str:
    for key in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        value = os.environ.get(key)
        if value:
            return value
    raise RuntimeError("Project ID nao encontrado nas variaveis de ambiente.")


def publish_telegram_tool(payload: dict) -> str:
    from google.cloud import pubsub_v1

    project_id = _get_project_id()
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, TELEGRAM_TOOL_TOPIC)
    future = publisher.publish(topic_path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return future.result(timeout=15)
