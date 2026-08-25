"""Contexto de execucao de tools fora do closure de `askCopilotoHermes`.

O copiloto web mantem suas ~45 tools como closures presas ao escopo da
requisicao (`db`, `user_uid`, `session_id`, `task_id`, `client`, `gemini_key`).
A analise de variaveis livres dessas closures mostrou que o acoplamento real e
raso: 35 delas capturam apenas `db`, 13 capturam `user_uid`, e o restante se
resolve com `session_id`, `task_id` e o cliente Gemini.

`ToolContext` reune exatamente esse conjunto, com construcao preguicosa do que
e caro (cliente Gemini, chave de API), para que qualquer canal — servidor MCP,
voz, Telegram — execute a mesma tool sem depender de um request HTTP do web app.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolContext:
    """Estado que as tools do Hermes precisam para rodar fora do copiloto web.

    `user_uid` vem do ID token verificado pelo canal (no MCP, do `Authorization:
    Bearer`). `session_id` e `task_id` sao opcionais: existem para dar
    continuidade a uma sessao/acao do Hermes quando o canal souber informa-los,
    e as tools que dependem deles degradam com mensagem explicita quando ausentes.
    """

    user_uid: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    canal: str = "mcp"

    _db: object | None = field(default=None, repr=False)
    _gemini_key: str | None = field(default=None, repr=False)
    _genai_client: object | None = field(default=None, repr=False)

    @property
    def db(self):
        if self._db is None:
            from firebase_admin import firestore

            self._db = firestore.client()
        return self._db

    @property
    def gemini_key(self) -> str | None:
        """Chave Gemini de `system/api_keys`, lida sob demanda e memoizada.

        Só as tools que geram conteudo (relatorio, imagem, leitura integral de
        documento) precisam dela — resolver preguicosamente evita uma leitura de
        Firestore em toda chamada de tool somente-leitura.
        """
        if self._gemini_key is None:
            snap = self.db.collection("system").document("api_keys").get()
            data = snap.to_dict() or {} if snap.exists else {}
            self._gemini_key = data.get("gemini_api_key") or ""
        return self._gemini_key or None

    @property
    def genai_client(self):
        if self._genai_client is None:
            key = self.gemini_key
            if not key:
                raise RuntimeError(
                    "Chave Gemini nao configurada em system/api_keys.gemini_api_key"
                )
            from google import genai

            self._genai_client = genai.Client(api_key=key)
        return self._genai_client

    def require_task_id(self, explicito: str | None = None) -> str:
        """Resolve o task_id do argumento, caindo para o do contexto."""
        resolved = (explicito or self.task_id or "").strip()
        if not resolved:
            raise ValueError(
                "Nenhuma acao em contexto: informe task_id explicitamente nesta chamada."
            )
        return resolved
