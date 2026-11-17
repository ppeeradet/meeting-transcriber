from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit


PLATFORM_HOSTS = {
    "youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com",
    "tiktok.com", "x.com", "twitter.com", "vimeo.com", "dailymotion.com",
    "dai.ly", "soundcloud.com",
}


class UnsafeMediaURL(ValueError):
    pass


class UnsafeRequest(ValueError):
    pass


def validate_request_context(mode: str, client_host: str, host: str, origin: str | None, public_origin: str) -> None:
    normalized_host = host.split(":", 1)[0].lower()
    allowed_hosts = {"127.0.0.1", "localhost", "dell-pc.tail187694.ts.net", "testserver"}
    if normalized_host not in allowed_hosts:
        raise UnsafeRequest("Host ไม่ได้รับอนุญาต")
    if origin and origin.rstrip("/") != public_origin.rstrip("/"):
        raise UnsafeRequest("Origin ไม่ได้รับอนุญาต")
    if mode == "tailnet":
        try:
            address = ipaddress.ip_address(client_host)
        except ValueError as exc:
            raise UnsafeRequest("Client address ไม่ถูกต้อง") from exc
        if not address.is_loopback:
            raise UnsafeRequest("Tailnet proxy ต้องเชื่อมต่อผ่าน loopback")


def _matches_host(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith(f".{allowed}")


def _resolved_ips(host: str, resolver: Callable[..., Iterable[tuple]] | None = None) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    lookup = resolver or socket.getaddrinfo
    try:
        records = lookup(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeMediaURL("ไม่สามารถตรวจสอบ DNS ของ URL ได้") from exc
    addresses = {ipaddress.ip_address(record[4][0]) for record in records}
    if not addresses:
        raise UnsafeMediaURL("URL ไม่มี DNS address")
    return addresses


def validate_media_url(raw_url: str, direct_hosts: set[str] | None = None, resolver: Callable[..., Iterable[tuple]] | None = None) -> str:
    url = raw_url.strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeMediaURL("รูปแบบ URL ไม่ถูกต้อง") from exc
    if parsed.scheme.lower() != "https":
        raise UnsafeMediaURL("รองรับเฉพาะ HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeMediaURL("URL ต้องไม่มี credentials และต้องมี hostname")
    if port not in (None, 443):
        raise UnsafeMediaURL("ไม่อนุญาตพอร์ตที่กำหนดเอง")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeMediaURL("ไม่อนุญาต localhost")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeMediaURL("ไม่อนุญาต private, loopback, link-local หรือ metadata address")
    allowed = PLATFORM_HOSTS | {item.lower().strip(".") for item in (direct_hosts or set()) if item}
    if not any(_matches_host(host, item) for item in allowed):
        raise UnsafeMediaURL("Platform หรือโดเมนนี้ยังไม่ได้รับอนุญาต")
    for address in _resolved_ips(host, resolver):
        if not address.is_global:
            raise UnsafeMediaURL("DNS ชี้ไปยัง private, loopback, link-local หรือ metadata address")
    return url


def validate_batch(urls: list[str], direct_hosts: set[str] | None = None, resolver: Callable[..., Iterable[tuple]] | None = None) -> list[str]:
    validated: list[str] = []
    seen: set[str] = set()
    for index, raw_url in enumerate(urls, 1):
        try:
            url = validate_media_url(raw_url, direct_hosts=direct_hosts, resolver=resolver)
        except UnsafeMediaURL as exc:
            raise UnsafeMediaURL(f"URL ลำดับที่ {index}: {exc}") from exc
        if url not in seen:
            validated.append(url)
            seen.add(url)
    return validated
