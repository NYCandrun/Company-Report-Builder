from __future__ import annotations

import unittest
from unittest.mock import patch

from research_control.capture import USER_AGENT, _robots_allowed


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class _Opener:
    def __init__(self, body: bytes, seen_agents: list[str | None]) -> None:
        self.body = body
        self.seen_agents = seen_agents

    def open(self, request, *, timeout: int):  # type: ignore[no-untyped-def]
        self.seen_agents.append(request.get_header("User-agent"))
        if timeout != 30:
            raise AssertionError(f"unexpected timeout: {timeout}")
        return _Response(self.body)


class RobotsPolicyTests(unittest.TestCase):
    def test_robots_request_uses_research_user_agent_and_parses_rules(self) -> None:
        seen_agents: list[str | None] = []
        body = b"User-agent: *\nDisallow: /private\nAllow: /public\n"
        opener = _Opener(body, seen_agents)
        with (
            patch("research_control.capture._require_public_host"),
            patch("research_control.capture.build_opener", return_value=opener),
        ):
            self.assertTrue(_robots_allowed("https://docs.example.com/public"))
            self.assertFalse(_robots_allowed("https://docs.example.com/private"))
        self.assertEqual([USER_AGENT, USER_AGENT], seen_agents)


if __name__ == "__main__":
    unittest.main()
