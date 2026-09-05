import sys
import unittest

sys.path.insert(0, '.')

from email_action_linker import is_sender_ignored


class TestEmailActionLinkerFilter(unittest.TestCase):
    def test_empty_or_none(self):
        self.assertFalse(is_sender_ignored("", ["github.com"]))
        self.assertFalse(is_sender_ignored("user@example.com", []))
        self.assertFalse(is_sender_ignored(None, ["github.com"]))

    def test_exact_email_match(self):
        patterns = ["notifications@github.com"]
        self.assertTrue(is_sender_ignored("notifications@github.com", patterns))
        self.assertTrue(is_sender_ignored("NOTIFICATIONS@GITHUB.COM", patterns))
        self.assertTrue(is_sender_ignored('"GitHub" <notifications@github.com>', patterns))

    def test_domain_match(self):
        patterns = ["@github.com"]
        self.assertTrue(is_sender_ignored("notifications@github.com", patterns))
        self.assertTrue(is_sender_ignored("support@github.com", patterns))
        self.assertTrue(is_sender_ignored('"chatgpt-codex-connector[bot]" <notifications@github.com>', patterns))
        self.assertFalse(is_sender_ignored("user@gitlab.com", patterns))

    def test_partial_domain_match(self):
        patterns = ["github.com"]
        self.assertTrue(is_sender_ignored("notifications@github.com", patterns))
        self.assertTrue(is_sender_ignored("<noreply@github.com>", patterns))
        self.assertFalse(is_sender_ignored("user@example.com", patterns))

    def test_name_or_keyword_match(self):
        patterns = ["chatgpt-codex-connector"]
        self.assertTrue(is_sender_ignored('"chatgpt-codex-connector[bot]" <bot@external.org>', patterns))
        self.assertFalse(is_sender_ignored('"André Martini" <andre@example.com>', patterns))

    def test_multiple_patterns(self):
        patterns = ["notifications@github.com", "noreply@", "@jira.com"]
        self.assertTrue(is_sender_ignored("noreply@service.com", patterns))
        self.assertTrue(is_sender_ignored("alert@jira.com", patterns))
        self.assertTrue(is_sender_ignored("notifications@github.com", patterns))
        self.assertFalse(is_sender_ignored("valid.person@empresa.com.br", patterns))

    def test_load_settings_unifies_inbox_pendentes_noise(self):
        from unittest.mock import MagicMock, patch
        from email_action_linker import _load_settings

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "email_action_linker": {
                "enabled": True,
                "ignored_senders": ["custom@empresa.com"],
            }
        }
        with patch("main._cached_doc_get", return_value=mock_doc), \
             patch("inbox_pendentes._noise_config", return_value=({"eventos.ifnmg.edu.br", "picpay.com"}, set())):
            settings = _load_settings(mock_db)
            self.assertIn("custom@empresa.com", settings["ignored_senders"])
            self.assertIn("eventos.ifnmg.edu.br", settings["ignored_senders"])
            self.assertIn("picpay.com", settings["ignored_senders"])

    def test_load_settings_default_unifies_noise_domains(self):
        from unittest.mock import MagicMock, patch
        from email_action_linker import _load_settings

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        with patch("main._cached_doc_get", return_value=mock_doc), \
             patch("inbox_pendentes._noise_config", return_value=({"eventos.ifnmg.edu.br"}, set())):
            settings = _load_settings(mock_db)
            self.assertIn("notifications@github.com", settings["ignored_senders"])
            self.assertIn("@github.com", settings["ignored_senders"])
            self.assertIn("eventos.ifnmg.edu.br", settings["ignored_senders"])


if __name__ == '__main__':
    unittest.main()
