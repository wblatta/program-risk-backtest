"""Rate-limit-disciplined GitHub REST client.

The corpus is ~650 tracking issues plus their timelines, so a full pass is on the
order of 1,500-2,000 requests against a 5,000/hour authenticated budget. Three
mechanisms keep a run inside it:

1. **Reserve.** The client reads `X-RateLimit-Remaining` from every response and
   refuses to issue a request once the budget is at or below `reserve`, raising
   rather than spending the last of it. A caller that wants to wait instead can
   catch `RateLimitError` and check `reset_at`.
2. **Conditional requests.** ETags are cached per URL and replayed as
   `If-None-Match`. GitHub does not charge quota for a 304, so a re-run over an
   unchanged corpus is nearly free.
3. **Retry-After.** Secondary rate limits arrive as 403 (or 429) with a
   `Retry-After` header; the client sleeps exactly that long and retries once per
   response rather than backing off blindly.

Unauthenticated requests get 60/hour, which is not enough for a full pass -- pass a
token. `urllib` only: the project's dependency list is pyyaml, pandas, numpy, pytest.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "program-risk-backtest/0.0.1"
API = "https://api.github.com"


class RateLimitError(RuntimeError):
    """Raised rather than spending the budget below the configured reserve."""

    def __init__(self, message: str, reset_at: datetime | None = None):
        super().__init__(message)
        self.reset_at = reset_at


def _urllib_transport(url: str, headers: dict[str, str]):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class GitHubClient:
    def __init__(self, token: str | None = None, transport=None, sleep=time.sleep,
                 reserve: int = 50, max_retries: int = 3):
        self._token = token
        self._transport = transport or _urllib_transport
        self._sleep = sleep
        self._reserve = reserve
        self._max_retries = max_retries
        self._etags: dict[str, str] = {}
        self._bodies: dict[str, object] = {}
        self.remaining: int | None = None
        self.reset_at: datetime | None = None
        self.requests_made = 0
        self.not_modified = 0
        self._last_headers: dict[str, str] | None = None

    def _headers(self, url: str) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
             "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if url in self._etags:
            h["If-None-Match"] = self._etags[url]
        return h

    def _note_limits(self, headers: dict[str, str]) -> None:
        rem = headers.get("X-RateLimit-Remaining")
        if rem is not None:
            try:
                self.remaining = int(rem)
            except ValueError:
                pass
        rst = headers.get("X-RateLimit-Reset")
        if rst is not None:
            try:
                self.reset_at = datetime.fromtimestamp(int(rst), tz=timezone.utc)
            except (ValueError, OSError):
                pass

    def _get_one(self, url: str):
        """GET a single URL. Raises RateLimitError rather than spending the budget
        below the reserve. A 304 returns the cached body."""
        if self.remaining is not None and self.remaining <= self._reserve:
            raise RateLimitError(
                f"budget at {self.remaining}, reserve is {self._reserve}; "
                f"resets at {self.reset_at.isoformat() if self.reset_at else 'unknown'}",
                self.reset_at)

        for attempt in range(self._max_retries):
            status, headers, body = self._transport(url, self._headers(url))
            self.requests_made += 1
            self._last_headers = headers
            self._note_limits(headers)

            if status == 304:
                self.not_modified += 1
                return self._bodies[url]

            if status in (403, 429):
                wait = headers.get("Retry-After")
                if wait is not None:
                    self._sleep(int(wait))
                    continue
                raise RateLimitError(
                    f"{status} from {url} with no Retry-After: {body[:200]!r}", self.reset_at)

            if status >= 500:
                self._sleep(2 ** attempt)
                continue

            if status >= 400:
                raise RuntimeError(f"{status} from {url}: {body[:200]!r}")

            if "ETag" in headers:
                self._etags[url] = headers["ETag"]
            parsed = json.loads(body)
            self._bodies[url] = parsed
            return parsed

        raise RuntimeError(f"gave up on {url} after {self._max_retries} attempts")

    def get_json(self, url: str):
        """GET `url`, following `Link: rel="next"` when the response is a JSON list.

        GitHub paginates list endpoints at 100 items. The timeline endpoint in
        particular runs oldest-first, so stopping at page 1 silently discards the
        MOST RECENT history -- and long-lived KEPs are the worst affected. Measured
        before this was fixed: 475 of 644 cached timelines held exactly 100 entries,
        and page 1 covered a median of 36% of an issue's lifetime, as little as 1.8%
        for the longest-lived. Everything after the cutoff was invisible to the
        evidence rule, which then reported those rows as having no paper trail.

        Only list responses are followed; a single object (an issue) has no next page.
        """
        first = self._get_one(url)
        if not isinstance(first, list):
            return first
        out = list(first)
        while (nxt := self._next_link(self._last_headers)):
            page = self._get_one(nxt)
            if not isinstance(page, list):
                break
            out.extend(page)
        return out

    @staticmethod
    def _next_link(headers: dict[str, str] | None) -> str | None:
        """Parse `Link: <url>; rel="next"` -- the pagination cursor GitHub returns."""
        link = (headers or {}).get("Link") or (headers or {}).get("link")
        if not link:
            return None
        for part in link.split(","):
            bits = part.split(";")
            if len(bits) < 2:
                continue
            if 'rel="next"' in "".join(bits[1:]).replace(" ", "").replace("'", '"'):
                return bits[0].strip().strip("<>")
        return None
