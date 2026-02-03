#!/usr/bin/env python3
"""Quick probe tool for Intelbras AMT endpoint.

It can try TLS and/or plain TCP, optionally send a payload, and print any response bytes.
"""

import argparse
import socket
import ssl
import sys
from typing import Optional, Tuple


def _connect_plain(host: str, port: int, timeout: float) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    return s


def _connect_tls(host: str, port: int, timeout: float, sni: Optional[str]) -> ssl.SSLSocket:
    ctx = ssl.create_default_context()
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    raw.connect((host, port))
    tls = ctx.wrap_socket(raw, server_hostname=sni or host)
    return tls


def _recv_some(sock: socket.socket, recv_bytes: int) -> bytes:
    try:
        return sock.recv(recv_bytes)
    except socket.timeout:
        return b""


def _send_and_recv(sock: socket.socket, payload: Optional[bytes], recv_bytes: int) -> bytes:
    if payload:
        sock.sendall(payload)
    return _recv_some(sock, recv_bytes)


def _probe(host: str, port: int, timeout: float, recv_bytes: int, payload: Optional[bytes], mode: str, sni: Optional[str]) -> Tuple[str, bytes, Optional[str]]:
    """Returns (mode_used, response, extra_info)."""
    if mode == "plain":
        s = _connect_plain(host, port, timeout)
        try:
            return "plain", _send_and_recv(s, payload, recv_bytes), None
        finally:
            s.close()

    if mode == "tls":
        s = _connect_tls(host, port, timeout, sni)
        try:
            cert = s.getpeercert()
            subject = None
            if cert and "subject" in cert:
                subject = ", ".join("=".join(x) for part in cert["subject"] for x in part)
            return "tls", _send_and_recv(s, payload, recv_bytes), subject
        finally:
            s.close()

    # auto
    try:
        s = _connect_tls(host, port, timeout, sni)
        try:
            cert = s.getpeercert()
            subject = None
            if cert and "subject" in cert:
                subject = ", ".join("=".join(x) for part in cert["subject"] for x in part)
            return "tls", _send_and_recv(s, payload, recv_bytes), subject
        finally:
            s.close()
    except Exception:
        s = _connect_plain(host, port, timeout)
        try:
            return "plain", _send_and_recv(s, payload, recv_bytes), None
        finally:
            s.close()


def _hex_to_bytes(value: str) -> bytes:
    v = value.strip().replace(" ", "")
    if v.startswith("0x"):
        v = v[2:]
    if len(v) % 2 != 0:
        raise ValueError("hex string must have even length")
    return bytes.fromhex(v)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Intelbras AMT endpoint over TCP/TLS.")
    parser.add_argument("--host", required=True, help="Host to connect")
    parser.add_argument("--port", type=int, default=9009, help="Port to connect")
    parser.add_argument("--mode", choices=["auto", "plain", "tls"], default="auto", help="Connection mode")
    parser.add_argument("--timeout", type=float, default=5.0, help="Socket timeout in seconds")
    parser.add_argument("--recv-bytes", type=int, default=1024, help="Max bytes to read")
    parser.add_argument("--send-hex", default="", help="Hex payload to send (e.g. 'f0f0...')")
    parser.add_argument("--sni", default="", help="Override SNI hostname for TLS")

    args = parser.parse_args()

    payload = None
    if args.send_hex:
        try:
            payload = _hex_to_bytes(args.send_hex)
        except ValueError as exc:
            print(f"Invalid --send-hex: {exc}", file=sys.stderr)
            return 2

    try:
        mode_used, response, subject = _probe(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            recv_bytes=args.recv_bytes,
            payload=payload,
            mode=args.mode,
            sni=args.sni or None,
        )
    except Exception as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        return 1

    print(f"mode={mode_used}")
    if subject:
        print(f"tls_subject={subject}")
    if response:
        print(f"response_len={len(response)}")
        print(f"response_hex={response.hex()}")
    else:
        print("response_len=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
