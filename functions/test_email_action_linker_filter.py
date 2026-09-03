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


if __name__ == '__main__':
    unittest.main()
