import hashlib
import hmac
import json
import unittest
from unittest import mock

from main import (
    _obter_github_webhook_secret,
    anotar_evento_github_em_tarefas,
    githubWebhook,
    normalizar_evento_github,
    verificar_assinatura_github,
)


class TestGitHubWebhookAssinatura(unittest.TestCase):
    def setUp(self):
        self.secret = "meu-segredo-super-secreto-123"
        self.corpo = b'{"zen": "Favoring focus over features."}'

    def _gerar_sig(self, corpo: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_assinatura_valida(self):
        sig = self._gerar_sig(self.corpo, self.secret)
        self.assertTrue(verificar_assinatura_github(self.corpo, sig, self.secret))

    def test_assinatura_invalida(self):
        sig = "sha256=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        self.assertFalse(verificar_assinatura_github(self.corpo, sig, self.secret))

    def test_assinatura_com_outro_secret(self):
        sig = self._gerar_sig(self.corpo, "outro-segredo")
        self.assertFalse(verificar_assinatura_github(self.corpo, sig, self.secret))

    def test_header_sem_prefixo_sha256(self):
        digest = hmac.new(self.secret.encode("utf-8"), self.corpo, hashlib.sha256).hexdigest()
        self.assertFalse(verificar_assinatura_github(self.corpo, digest, self.secret))

    def test_header_ausente_ou_vazio(self):
        self.assertFalse(verificar_assinatura_github(self.corpo, None, self.secret))
        self.assertFalse(verificar_assinatura_github(self.corpo, "", self.secret))

    def test_secret_ausente_ou_vazio(self):
        sig = self._gerar_sig(self.corpo, self.secret)
        self.assertFalse(verificar_assinatura_github(self.corpo, sig, None))
        self.assertFalse(verificar_assinatura_github(self.corpo, sig, ""))


class TestGitHubWebhookNormalizacao(unittest.TestCase):
    def setUp(self):
        self.repo = "andre-martiini/Atlas"
        self.repo_payload = {
            "full_name": self.repo,
            "default_branch": "main",
        }

    def test_pr_mergeada_gera_nota(self):
        payload = {
            "action": "closed",
            "repository": self.repo_payload,
            "pull_request": {
                "number": 42,
                "title": "feat: suporte a exportacao de relatorios",
                "merged": True,
                "html_url": "https://github.com/andre-martiini/Atlas/pull/42",
            },
        }
        res = normalizar_evento_github("pull_request", payload)
        self.assertIsNotNone(res)
        self.assertEqual(res["repo"], self.repo)
        self.assertIn("[GitHub] PR #42 mergeada em andre-martiini/Atlas", res["nota"])
        self.assertIn('"feat: suporte a exportacao de relatorios"', res["nota"])
        self.assertIn("https://github.com/andre-martiini/Atlas/pull/42", res["nota"])

    def test_pr_fechada_sem_merge_ignora(self):
        payload = {
            "action": "closed",
            "repository": self.repo_payload,
            "pull_request": {
                "number": 43,
                "title": "teste descartado",
                "merged": False,
                "html_url": "https://github.com/andre-martiini/Atlas/pull/43",
            },
        }
        self.assertIsNone(normalizar_evento_github("pull_request", payload))

    def test_pr_aberta_ignora(self):
        payload = {
            "action": "opened",
            "repository": self.repo_payload,
            "pull_request": {
                "number": 44,
                "title": "em andamento",
                "merged": False,
            },
        }
        self.assertIsNone(normalizar_evento_github("pull_request", payload))

    def test_push_default_branch_com_commits(self):
        payload = {
            "ref": "refs/heads/main",
            "repository": self.repo_payload,
            "commits": [
                {"message": "fix: ajuste no layout", "url": "https://github.com/commit/1"},
                {
                    "message": "docs: atualiza documentacao\n\nDetalhes sobre o novo endpoint.",
                    "url": "https://github.com/commit/2",
                },
            ],
            "head_commit": {
                "message": "docs: atualiza documentacao\n\nDetalhes sobre o novo endpoint.",
                "url": "https://github.com/commit/2",
            },
            "compare": "https://github.com/andre-martiini/Atlas/compare/1...2",
        }
        res = normalizar_evento_github("push", payload)
        self.assertIsNotNone(res)
        self.assertEqual(res["repo"], self.repo)
        self.assertIn("[GitHub] Push em andre-martiini/Atlas (main), 2 commit(s)", res["nota"])
        self.assertIn('último: "docs: atualiza documentacao"', res["nota"])
        self.assertNotIn("Detalhes sobre o novo endpoint.", res["nota"])
        self.assertIn("https://github.com/andre-martiini/Atlas/compare/1...2", res["nota"])

    def test_push_em_branch_diferente_do_default_ignora(self):
        payload = {
            "ref": "refs/heads/feature/novo-card",
            "repository": self.repo_payload,
            "commits": [{"message": "wip"}],
        }
        self.assertIsNone(normalizar_evento_github("push", payload))

    def test_push_sem_commits_ignora(self):
        payload = {
            "ref": "refs/heads/main",
            "repository": self.repo_payload,
            "commits": [],
        }
        self.assertIsNone(normalizar_evento_github("push", payload))

    def test_evento_desconhecido_ignora(self):
        for evt in ["issues", "issue_comment", "release", "workflow_run", "ping"]:
            with self.subTest(evento=evt):
                res = normalizar_evento_github(evt, {"repository": self.repo_payload})
                self.assertIsNone(res)

    def test_payload_invalido_ou_sem_repo_ignora(self):
        self.assertIsNone(normalizar_evento_github("pull_request", {}))
        self.assertIsNone(normalizar_evento_github("push", {}))
        self.assertIsNone(normalizar_evento_github("push", None))


class TestAnotarEventoGitHubEmTarefas(unittest.TestCase):
    def test_anota_em_todas_tarefas_vinculadas(self):
        db = mock.MagicMock()
        t1 = mock.MagicMock()
        t1.id = "tarefa-1"
        t2 = mock.MagicMock()
        t2.id = "tarefa-2"

        db.collection.return_value.where.return_value.stream.return_value = [t1, t2]

        count = anotar_evento_github_em_tarefas(db, "andre-martiini/Atlas", "Nota de teste")
        self.assertEqual(count, 2)
        t1.reference.update.assert_called_once()
        t2.reference.update.assert_called_once()

    def test_zero_tarefas_vinculadas_nao_falha(self):
        db = mock.MagicMock()
        db.collection.return_value.where.return_value.stream.return_value = []
        count = anotar_evento_github_em_tarefas(db, "andre-martiini/Inexistente", "Nota")
        self.assertEqual(count, 0)

    def test_falha_em_uma_tarefa_nao_derruba_as_outras(self):
        db = mock.MagicMock()
        t1 = mock.MagicMock()
        t1.id = "tarefa-1"
        t1.reference.update.side_effect = RuntimeError("Falha de rede Firestore")

        t2 = mock.MagicMock()
        t2.id = "tarefa-2"

        db.collection.return_value.where.return_value.stream.return_value = [t1, t2]

        count = anotar_evento_github_em_tarefas(db, "andre-martiini/Atlas", "Nota")
        self.assertEqual(count, 1)
        t2.reference.update.assert_called_once()


class TestGitHubWebhookHttpFlow(unittest.TestCase):
    def setUp(self):
        self.secret = "segredo-webhook-teste"

    def _criar_req(
        self,
        method="POST",
        event="pull_request",
        delivery="delivery-uuid-123",
        payload=None,
        sig=None,
    ):
        req = mock.MagicMock()
        req.method = method
        corpo = json.dumps(payload or {}).encode("utf-8")
        req.get_data.return_value = corpo

        if sig is None:
            digest = hmac.new(self.secret.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
            sig = f"sha256={digest}"

        req.headers = {
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": sig,
        }
        return req

    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_falha_fechada_secret_nao_configurado_retorna_500(self, mock_get_db, mock_secret):
        mock_secret.return_value = None
        req = self._criar_req()
        resp = githubWebhook(req)
        self.assertEqual(resp.status_code, 500)

    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_assinatura_invalida_retorna_401(self, mock_get_db, mock_secret):
        mock_secret.return_value = self.secret
        req = self._criar_req(sig="sha256=assinaturaerrada123")
        resp = githubWebhook(req)
        self.assertEqual(resp.status_code, 401)

    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_ping_com_assinatura_valida_retorna_200_sem_processar(self, mock_get_db, mock_secret):
        mock_secret.return_value = self.secret
        req = self._criar_req(event="ping", payload={"zen": "Non-blocking is better than blocking."})
        resp = githubWebhook(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "pong")

    @mock.patch("core.idempotency.check_and_register")
    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_delivery_repetido_retorna_200_ja_processado(
        self, mock_get_db, mock_secret, mock_idempotency
    ):
        mock_secret.return_value = self.secret
        mock_idempotency.return_value = False  # Já registrado
        req = self._criar_req()
        resp = githubWebhook(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "Already processed")

    @mock.patch("main.anotar_evento_github_em_tarefas")
    @mock.patch("core.idempotency.check_and_register")
    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_evento_valido_chama_anotar_e_retorna_200(
        self, mock_get_db, mock_secret, mock_idempotency, mock_anotar
    ):
        mock_secret.return_value = self.secret
        mock_idempotency.return_value = True

        payload = {
            "action": "closed",
            "repository": {"full_name": "andre-martiini/Hermes", "default_branch": "main"},
            "pull_request": {
                "number": 159,
                "title": "feat: outbox aprovacao whatsapp",
                "merged": True,
                "html_url": "https://github.com/andre-martiini/Hermes/pull/159",
            },
        }
        req = self._criar_req(event="pull_request", payload=payload)
        resp = githubWebhook(req)

        self.assertEqual(resp.status_code, 200)
        mock_anotar.assert_called_once()
        args, _ = mock_anotar.call_args
        self.assertEqual(args[1], "andre-martiini/Hermes")
        self.assertIn("PR #159 mergeada em andre-martiini/Hermes", args[2])

    @mock.patch("main.anotar_evento_github_em_tarefas")
    @mock.patch("core.idempotency.check_and_register")
    @mock.patch("main._obter_github_webhook_secret")
    @mock.patch("main.get_db")
    def test_evento_irrelevante_nao_anota_e_retorna_200(
        self, mock_get_db, mock_secret, mock_idempotency, mock_anotar
    ):
        mock_secret.return_value = self.secret
        mock_idempotency.return_value = True

        payload = {
            "action": "opened",
            "repository": {"full_name": "andre-martiini/Hermes", "default_branch": "main"},
            "pull_request": {"number": 160, "title": "wip", "merged": False},
        }
        req = self._criar_req(event="pull_request", payload=payload)
        resp = githubWebhook(req)

        self.assertEqual(resp.status_code, 200)
        mock_anotar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
