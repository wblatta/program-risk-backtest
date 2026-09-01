"""Rate-limit discipline for the GitHub client. No network: a fake transport records calls."""
from datetime import datetime, timezone
import pytest
from adapters.k8s.github import GitHubClient, RateLimitError


class FakeTransport:
    """Returns queued (status, headers, body) triples and records requests."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.slept = []

    def __call__(self, url, headers):
        self.requests.append((url, dict(headers)))
        return self.responses.pop(0)


def hdr(remaining, reset=2_000_000_000, **extra):
    h = {"X-RateLimit-Remaining": str(remaining), "X-RateLimit-Reset": str(reset)}
    h.update(extra)
    return h


def test_stops_before_exhausting_the_budget():
    """Client must refuse to issue a request that would take it below its reserve."""
    t = FakeTransport([(200, hdr(1), b'{"n": 1}')])
    c = GitHubClient(transport=t, sleep=lambda s: t.slept.append(s), reserve=5)
    c.get_json("https://api.github.com/a")          # observes remaining=1, under reserve=5
    with pytest.raises(RateLimitError):
        c.get_json("https://api.github.com/b")      # must not be attempted
    assert len(t.requests) == 1, "second request should never have been issued"


def test_conditional_request_reuses_cached_body_on_304():
    """A 304 costs no quota and must return the cached body, not None."""
    t = FakeTransport([(200, hdr(100, ETag='"v1"'), b'{"n": 1}'),
                       (304, hdr(100), b"")])
    c = GitHubClient(transport=t, sleep=lambda s: None)
    first = c.get_json("https://api.github.com/a")
    second = c.get_json("https://api.github.com/a")
    assert first == second == {"n": 1}
    assert t.requests[1][1].get("If-None-Match") == '"v1"', "second request must send the ETag"


def test_waits_for_reset_when_secondary_limit_hits():
    """A 403 carrying Retry-After must sleep for that long, then retry."""
    t = FakeTransport([(403, hdr(50, **{"Retry-After": "7"}), b'{"message":"secondary"}'),
                       (200, hdr(49), b'{"ok": true}')])
    slept = []
    c = GitHubClient(transport=t, sleep=slept.append)
    assert c.get_json("https://api.github.com/a") == {"ok": True}
    assert slept == [7], f"expected a single 7s sleep, got {slept}"
