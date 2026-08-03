from __future__ import annotations

import logging
import socket

import httpx

logger = logging.getLogger(__name__)

_orig_getaddrinfo = socket.getaddrinfo
_patched = False


def force_ipv4_dns() -> None:
    global _patched
    if _patched:
        return

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_ipv4  # type: ignore[assignment]
    _patched = True
    logger.info("socket.getaddrinfo patched to AF_INET only")


def restore_dns() -> None:
    """Undo process-wide IPv4 DNS patch (e.g. after probe, before TG traffic)."""
    global _patched
    if not _patched:
        return
    socket.getaddrinfo = _orig_getaddrinfo  # type: ignore[assignment]
    _patched = False
    logger.info("socket.getaddrinfo restored to system default")


async def probe_ipv4_or_raise(skip: bool = False) -> str:
    if skip:
        logger.warning("IPv4 probe skipped via LUMIBOT_SKIP_IPV4_CHECK")
        return "skipped"
    force_ipv4_dns()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.ipify.org")
            resp.raise_for_status()
            ip = resp.text.strip()
    except Exception as exc:  # noqa: BLE001
        restore_dns()
        raise RuntimeError(
            "IPv4 outbound probe failed. GMGN requires IPv4. "
            "Disable IPv6 on the host or run on an IPv4 VPS. "
            f"Detail: {exc}"
        ) from exc
    if ":" in ip:
        restore_dns()
        raise RuntimeError(
            f"Outbound address looks like IPv6 ({ip}). GMGN requires IPv4. "
            "Disable IPv6 or use an IPv4 network."
        )
    restore_dns()
    logger.info("IPv4 probe ok: %s (system DNS restored; GMGN client binds IPv4)", ip)
    return ip
