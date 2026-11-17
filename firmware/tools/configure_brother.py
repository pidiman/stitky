#!/usr/bin/env python3
"""Add a Brother network destination to an existing configured ESP32 over USB."""
import argparse
import getpass
import ipaddress
from pathlib import Path

from provision import send_configuration


def configuration(host, token):
    address = ipaddress.ip_address(host)
    if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError("Use the Brother printer's reachable IPv4 address.")
    token = token.strip()
    if not 24 <= len(token) <= 200:
        raise ValueError("Brother device token must contain 24–200 characters.")
    return {"brother_host": str(address), "brother_token": token}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--host", required=True, help="IPv4 address of the Brother, not the server")
    parser.add_argument("--token-file", help="Private local file; otherwise asked using hidden input")
    args = parser.parse_args()
    token = Path(args.token_file).read_text() if args.token_file else getpass.getpass("Brother device token (hidden): ")
    send_configuration(configuration(args.host, token), args.port)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(str(exc)) from None
