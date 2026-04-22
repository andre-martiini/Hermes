import re

with open('functions/main.py', 'r') as f:
    content = f.read()

new_functions = """
# ─────────────────────────────────────────────────────────────────────────────
# DEEP RESEARCH MAX (MVP) - Callables
# ─────────────────────────────────────────────────────────────────────────────

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def startDeepResearch(req: https_fn.CallableRequest):
    \"\"\"
    Inicia uma pesquisa profunda.
    Valida dados, injeta serverTimestamp e cria o doc em deep_research_tasks.
    \"\"\"
    try:
        data = req.data or {}
        topic = data.get('topic')
        requester_email = data.get('requester_email', 'unknown')
        telegram_chat_id = data.get('telegram_chat_id', '')

        if not topic:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Topic is required."
            )

        db = get_db()
        task_ref = db.collection('deep_research_tasks').document()
        task_ref.set({
            'status': 'pending',
            'topic': topic,
            'requester_email': requester_email,
            'telegram_chat_id': telegram_chat_id,
            'created_at': firestore.firestore.SERVER_TIMESTAMP
        })

        return {"taskId": task_ref.id, "status": "pending"}
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )

@https_fn.on_call(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["POST"]),
    memory=options.MemoryOption.MB_256,
    timeout_sec=30
)
def cancelDeepResearch(req: https_fn.CallableRequest):
    \"\"\"
    Cancela uma pesquisa profunda, atualizando o status do doc.
    \"\"\"
    try:
        data = req.data or {}
        task_id = data.get('taskId')

        if not task_id:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Task ID is required."
            )

        db = get_db()
        task_ref = db.collection('deep_research_tasks').document(task_id)

        doc = task_ref.get()
        if not doc.exists:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Task not found."
            )

        task_ref.update({
            'status': 'CANCELLED',
            'cancelled_at': firestore.firestore.SERVER_TIMESTAMP
        })

        return {"taskId": task_id, "status": "CANCELLED"}
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=str(e)
        )
"""

with open('functions/main.py', 'w') as f:
    f.write(content + "\n" + new_functions)
