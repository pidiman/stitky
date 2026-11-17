#!/usr/bin/env python3
"""Local USB provisioning. Never prints or saves network passwords/device tokens."""
import argparse
import getpass
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


def configuration(args):
    url = args.api_url.rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('API URL must be an HTTPS origin without credentials/query/fragment')
    cert = Path(args.ca).read_text(encoding='ascii')
    if '-----BEGIN CERTIFICATE-----' not in cert or len(cert) > 6000:
        raise ValueError('CA file must contain a PEM root certificate, maximum 6000 characters')
    token = Path(args.token_file).read_text().strip() if args.token_file else getpass.getpass('Device API token (hidden): ').strip()
    if not 24 <= len(token) <= 200:
        raise ValueError('Device token must contain 24–200 characters')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', args.printer_mac):
        raise ValueError('Invalid printer MAC')
    result = dict(api_url=url, agent_token=token, server_ca_pem=cert, printer_mac=args.printer_mac.lower())
    if args.wifi:
        result['ssid'] = input('2.4 GHz Wi-Fi SSID [MyWiFi]: ').strip() or 'MyWiFi'
        result['password'] = getpass.getpass('Wi-Fi password (hidden): ')
        if len(result['ssid'].encode()) > 32 or len(result['password'].encode()) > 63:
            raise ValueError('Wi-Fi SSID/password too long')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/cu.SLAB_USBtoUART')
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--ca', required=True, help='PEM root CA, e.g. certs/isrgrootx1.pem')
    parser.add_argument('--token-file', help='Optional private local token file; otherwise entered hidden')
    parser.add_argument('--printer-mac', default='02:00:00:00:00:01')
    parser.add_argument('--wifi', action='store_true', help='Optional masked USB Wi-Fi setup instead of captive portal')
    args = parser.parse_args()
    data = configuration(args)
    send_configuration(data, args.port)


def send_configuration(data, port):
    command = b'CONFIG ' + json.dumps(data, ensure_ascii=True, separators=(',', ':')).encode() + b'\n'
    if len(command) > 8192:
        raise ValueError('Configuration exceeds firmware serial limit')
    import serial
    with serial.Serial(port, 115200, timeout=1, dsrdtr=False, rtscts=False) as device:
        device.dtr = False
        device.rts = True
        time.sleep(.15)
        device.rts = False
        # Setup may scan Wi-Fi on first boot. Do not transmit while bootloader is active.
        time.sleep(3)
        device.reset_input_buffer()
        for offset in range(0, len(command), 64):
            device.write(command[offset:offset+64])
            device.flush()
            time.sleep(.01)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            line = device.readline().decode(errors='replace').strip()
            if line == 'CONFIG SAVED; RESTARTING':
                print('Configuration saved in ESP32. Settings omitted from this update were preserved.')
                return
            if line.startswith('CONFIG REJECTED:'):
                raise RuntimeError(line)
        raise TimeoutError('No configuration acknowledgement; inspect serial STATUS without resending print jobs')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(str(exc)) from None
