import unittest

from gway import gw


class DummyResponse:
    def __init__(self, *, status_code=200, json_data=None, text="", reason=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.reason = reason

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON payload")
        return self._json_data


class DummySession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": headers,
            "timeout": timeout,
        })
        return self.response


class MonitorGithubIssueTests(unittest.TestCase):
    def setUp(self):
        gw.monitor.get_state("github_issue").clear()

    def test_monitor_updates_state_for_open_issue(self):
        payload = {
            "number": 42,
            "state": "open",
            "title": "Add docs",
            "html_url": "https://github.com/example/repo/issues/42",
            "updated_at": "2023-08-01T12:00:00Z",
            "user": {"login": "alice"},
        }
        session = DummySession(DummyResponse(json_data=payload))

        result = gw.monitor.github_issue.monitor_github_issue(
            issue=42,
            repo="example/repo",
            session=session,
            token="abc123",
            timeout=1,
        )

        self.assertFalse(result["closed"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["issue"], 42)

        state = gw.monitor.get_state("github_issue")
        self.assertIn("last_monitor_check", state)
        self.assertEqual(state["last_issue_checked"], "42")
        issue_state = state["issues"]["42"]
        self.assertEqual(issue_state["title"], "Add docs")
        self.assertEqual(issue_state["state"], "open")
        self.assertFalse(issue_state["closed"])
        self.assertEqual(issue_state["url"], payload["html_url"])

        call = session.calls[0]
        self.assertEqual(
            call["url"],
            "https://api.github.com/repos/example/repo/issues/42",
        )
        self.assertEqual(call["headers"].get("Authorization"), "token abc123")

    def test_monitor_marks_issue_closed(self):
        payload = {
            "number": 55,
            "state": "closed",
            "title": "Fix bug",
            "html_url": "https://github.com/example/repo/issues/55",
            "closed_at": "2023-08-01T12:10:00Z",
            "closed_by": {"login": "bob"},
        }
        session = DummySession(DummyResponse(json_data=payload))

        result = gw.monitor.github_issue.monitor_github_issue(
            issue="#55",
            repo="example/repo",
            session=session,
        )

        self.assertTrue(result["closed"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["issue"], 55)

        state = gw.monitor.get_state("github_issue")
        self.assertEqual(state["last_closed_issue"], "55")
        self.assertEqual(state["last_closed_at"], payload["closed_at"])
        issue_state = state["issues"]["55"]
        self.assertTrue(issue_state["closed"])
        self.assertEqual(issue_state["closed_by"], "bob")

    def test_monitor_records_error_for_missing_issue(self):
        session = DummySession(
            DummyResponse(status_code=404, json_data={}, text="Not Found", reason="Not Found")
        )

        result = gw.monitor.github_issue.monitor_github_issue(
            issue=7,
            repo="example/repo",
            session=session,
        )

        self.assertIsNone(result["closed"])
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"].lower())

        state = gw.monitor.get_state("github_issue")
        self.assertEqual(state["last_error"], result["error"])
        self.assertIsNone(state["last_closed_issue"])
        issue_state = state["issues"]["7"]
        self.assertEqual(issue_state["error"], result["error"])
        self.assertIsNone(issue_state["closed"])


if __name__ == "__main__":
    unittest.main()

