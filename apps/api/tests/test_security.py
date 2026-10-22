import socket

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.security import redact, safe_request, validate_target


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254",
        "http://10.0.0.1",
        "http://localhost",
        "http://localhost.",
        "http://x.localhost",
        "https://user:password@example.com",
        "https://example.com/#fragment",
        "http://example.com:22",
        "http://[invalid",
        "http://[fe80::1%eth0]",
        "http://example.com:invalid",
    ],
)
def test_rejects_unsafe_urls_without_network(url):
    with pytest.raises(ValueError):
        validate_target(url, allow_private=False, resolve=False)


def test_dns_mixed_public_private_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(ValueError, match="Private"):
        validate_target("https://example.com")
    assert validate_target("https://example.com", allow_private=True)[2] == "93.184.216.34"


def test_safe_request_pins_address_and_keeps_tls_hostname(monkeypatch):
    from app import security

    monkeypatch.setattr(security, "validate_target", lambda *a, **k: ("example.com", 8443, "93.184.216.34"))
    captured = {}

    class Response:
        status_code = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Client(Response):
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def stream(self, method, url, **kwargs):
            captured.update(method=method, url=url, request=kwargs)
            return Response()

    monkeypatch.setattr(security.httpx, "Client", Client)
    status, latency = safe_request("https://example.com:8443/health", method="HEAD")
    assert status == 204 and latency >= 0
    assert captured["url"].host == "93.184.216.34"
    assert captured["request"]["headers"]["Host"] == "example.com:8443"
    assert captured["request"]["extensions"]["sni_hostname"] == b"example.com"
    assert captured["client"]["follow_redirects"] is False
    assert captured["client"]["trust_env"] is False


def test_redaction_preserves_evidence_and_removes_common_secrets():
    value = redact(
        {
            "message": "timeout Authorization: Bearer abc.def password=hunter2 api_key=secret-key",
            "nested": {"refresh_token": "opaque", "status_code": 503},
            "items": ["Bearer xyz", {"cookie": "session"}],
        }
    )
    assert value["nested"] == {"refresh_token": "[REDACTED]", "status_code": 503}
    assert value["items"] == ["Bearer [REDACTED]", {"cookie": "[REDACTED]"}]
    assert "timeout" in value["message"]
    assert all(secret not in str(value) for secret in ["abc.def", "hunter2", "secret-key", "opaque"])


def test_production_settings_require_key_and_normalize_postgres_url():
    with pytest.raises(ValidationError):
        Settings(demo_mode=False, api_key="short", _env_file=None)
    settings = Settings(
        demo_mode=False, api_key="a" * 32, database_url="postgres://user:pass@host/db", _env_file=None
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@host/db"
