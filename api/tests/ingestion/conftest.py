from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@dataclass
class FakeSession:
    """Duck-types the subset of curl_cffi.requests.Session that fetch() uses.

    Avoids depending on curl_cffi's real transport in tests - handler can
    return a FakeResponse or raise, exactly like a real session's .get().
    """

    handler: Callable[[str, dict | None], FakeResponse]
    calls: list[tuple[str, dict | None]] = field(default_factory=list)

    def get(self, path: str, params: dict | None = None) -> FakeResponse:
        self.calls.append((path, params))
        return self.handler(path, params)
