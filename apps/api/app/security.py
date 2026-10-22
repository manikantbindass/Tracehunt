import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx

from app.config import get_settings

SENSITIVE_KEY = re.compile(r"(password|passwd|secret|token|authorization|api.?key|cookie|credential)", re.I)
SECRET_TEXT = re.compile(
    r"""(?i)\b(authorization|password|passwd|secret|access_token|refresh_token|api[_-]?key|token)\b(\s*["']?\s*[:=]\s*["']?)(?:Bearer\s+)?[^\s"',;}]+"""
)
BEARER = re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9._~+/-]+=*")


def redact(value, depth=0):
    if depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if SENSITIVE_KEY.search(str(k)) else redact(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value]
    if isinstance(value, str):
        return BEARER.sub("Bearer [REDACTED]", SECRET_TEXT.sub(r"\1\2[REDACTED]", value))
    return value


def validate_target(url: str, allow_private: bool | None = None, resolve=True) -> tuple[str, int, str]:
    """Resolve once and pin the outbound connection to a validated address."""
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Monitor URLs must use http or https")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("URLs must not contain credentials or fragments")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Invalid port") from exc
    if port not in (80, 443, 8000, 8080, 8443):
        raise ValueError("Allowed ports: 80, 443, 8000, 8080, 8443")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid hostname") from exc
    if not hostname or any(character.isspace() for character in hostname):
        raise ValueError("Invalid hostname")
    if "%" in hostname:
        raise ValueError("Scoped addresses are not supported")
    private = get_settings().monitor_allow_private_networks if allow_private is None else allow_private
    if not resolve:
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            if hostname.lower() in ("localhost", "metadata.google.internal") or hostname.endswith(
                ".localhost"
            ):
                if not private:
                    raise ValueError("Private destinations are blocked") from None
            return hostname, port, hostname
        if not private and not literal.is_global:
            raise ValueError("Private destinations are blocked")
        return hostname, port, hostname
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("Hostname has no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not private and not ip.is_global:
            raise ValueError("Private, loopback, reserved, and link-local destinations are blocked")
    return hostname, port, addresses[0][4][0]


def safe_request(url: str, method="GET", timeout=10, json_body=None) -> tuple[int, float]:
    """No redirects, proxies, cookies, auth, or body downloads. Prevent DNS rebinding."""
    import time

    hostname, port, address = validate_target(url)
    original = httpx.URL(url)
    pinned = original.copy_with(host=address)
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port != (443 if original.scheme == "https" else 80):
        host = f"{host}:{port}"
    started = time.monotonic()
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=timeout) as client:
        with client.stream(
            method,
            pinned,
            headers={"Host": host, "User-Agent": "TraceHunt/1.0"},
            extensions={"sni_hostname": hostname.encode("ascii")},
            json=json_body,
        ) as response:
            return response.status_code, round((time.monotonic() - started) * 1000, 2)
