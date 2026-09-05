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


    def test_load_settings_direct_read_when_use_cache_false(self):
        from unittest.mock import MagicMock, patch
        from email_action_linker import _load_settings

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "email_action_linker": {
                "enabled": True,
                "ignored_senders": ["fresh@domain.com"],
            }
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("main._cached_doc_get") as mock_cached_get, \
             patch("inbox_pendentes._noise_config", return_value=(set(), set())):
            settings = _load_settings(mock_db, use_cache=False)
            mock_cached_get.assert_not_called()
            mock_db.collection.assert_called_with("system")
            self.assertIn("fresh@domain.com", settings["ignored_senders"])

    def test_dismiss_matching_pending_emails_filters_canal_email_only(self):
        from unittest.mock import MagicMock
        from email_action_linker import dismiss_matching_pending_emails

        mock_db = MagicMock()
        # Mocking db.transaction() context
        mock_tx = MagicMock()
        mock_db.transaction.return_value = mock_tx

        # Doc 1: canal email, matching sender -> should be dismissed
        doc_email = MagicMock()
        doc_email.to_dict.return_value = {
            "canal": "email",
            "status": "pending",
            "sender": "ignore_me@domain.com",
        }
        snap_email = MagicMock()
        snap_email.exists = True
        snap_email.to_dict.return_value = {
            "canal": "email",
            "status": "pending",
            "sender": "ignore_me@domain.com",
        }
        doc_email.reference.get.return_value = snap_email

        # Doc 2: canal whatsapp, matching sender -> should NOT be dismissed
        doc_wa = MagicMock()
        doc_wa.to_dict.return_value = {
            "canal": "whatsapp",
            "status": "pending",
            "sender": "ignore_me@domain.com",
        }
        snap_wa = MagicMock()
        snap_wa.exists = True
        snap_wa.to_dict.return_value = {
            "canal": "whatsapp",
            "status": "pending",
            "sender": "ignore_me@domain.com",
        }
        doc_wa.reference.get.return_value = snap_wa

        query_mock = MagicMock()
        query_mock.stream.return_value = [doc_email, doc_wa]
        mock_db.collection.return_value.where.return_value = query_mock

        count = dismiss_matching_pending_emails(mock_db, ["@domain.com"])
        self.assertEqual(count, 1)

    def test_dismiss_matching_pending_emails_race_condition_skips_applied(self):
        from unittest.mock import MagicMock
        from email_action_linker import dismiss_matching_pending_emails

        mock_db = MagicMock()
        # Initial stream had pending
        doc_applied = MagicMock()
        doc_applied.to_dict.return_value = {
            "canal": "email",
            "status": "pending",
            "sender": "ignore_me@domain.com",
        }
        # But inside transaction, status is already applied
        snap_applied = MagicMock()
        snap_applied.exists = True
        snap_applied.to_dict.return_value = {
            "canal": "email",
            "status": "applied",
            "sender": "ignore_me@domain.com",
        }
        doc_applied.reference.get.return_value = snap_applied

        query_mock = MagicMock()
        query_mock.stream.return_value = [doc_applied]
        mock_db.collection.return_value.where.return_value = query_mock

        count = dismiss_matching_pending_emails(mock_db, ["@domain.com"])
        self.assertEqual(count, 0)
        doc_applied.reference.update.assert_not_called()


if __name__ == '__main__':
    unittest.main()

