"""HTTP transport for channel APIs. Tests inject a memory transport and never open sockets."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HttpResult:
    """One HTTP response. Callers parse `body`; it is not an instruction."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> object:
        import json

        return json.loads(self.body)


@dataclass
class RecordedCall:
    """A request the memory transport observed."""

    method: str
    url: str
    headers: Mapping[str, str]
    content: bytes | None
    json_body: object
    data: Mapping[str, str] | None
    files: Mapping[str, tuple[str, bytes, str]] | None


class MemoryTransport:
    """Scripted responses keyed by method and a URL substring."""

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self._routes: list[tuple[str, str, HttpResult]] = []
        self._default: HttpResult | None = None

    def when(self, method: str, url_contains: str, result: HttpResult) -> None:
        self._routes.append((method.upper(), url_contains, result))

    def default(self, result: HttpResult) -> None:
        self._default = result

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        json_body: object = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
    ) -> HttpResult:
        self.calls.append(
            RecordedCall(
                method=method.upper(),
                url=url,
                headers=dict(headers or {}),
                content=content,
                json_body=json_body,
                data=dict(data) if data is not None else None,
                files=dict(files) if files is not None else None,
            )
        )
        for route_method, needle, result in self._routes:
            if route_method == method.upper() and needle in url:
                return result
        if self._default is not None:
            return self._default
        raise AssertionError(f"No scripted response for {method} {url}")


class HttpxTransport:
    """Live HTTP. Tests must not construct this; the suite blocks sockets."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        json_body: object = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
    ) -> HttpResult:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=dict(headers or {}),
                content=content,
                json=json_body,
                data=dict(data) if data is not None else None,
                files=dict(files) if files is not None else None,
            )
        return HttpResult(status=response.status_code, body=response.content)
