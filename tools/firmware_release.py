#!/usr/bin/env python3
"""Package a built, public ESP32 app and its versioned OTA manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def package(image, version_file, output, source_commit):
    source = version_file.read_text()
    match = re.search(r'^#define FPS_VERSION "((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"$', source, re.M)
    if not match:
        raise ValueError('FPS_VERSION must be a stable major.minor.patch version')
    version = match[1]
    data = image.read_bytes()
    marker = ('FPS_OTA:esp32dev:dual1856-v1:' + version + ':END').encode()
    if not 1024 <= len(data) <= 0x1D0000 or data[0] != 0xe9 or marker not in data:
        raise ValueError('Image is not a compatible ESP32 OTA app for this version')
    if not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('A full source commit is required')
    output.mkdir(parents=True, exist_ok=True)
    name = f'esp32-firmware-{version}.bin'
    shutil.copyfile(image, output / name)
    manifest = {'schema': 1, 'product': 'fajny-print-studio', 'version': version,
                'board': 'esp32dev', 'layout': 'dual1856-v1', 'file': name,
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'source_commit': source_commit}
    (output / f'esp32-firmware-{version}.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=Path('firmware/.pio/build/esp32dev/firmware.bin'))
    parser.add_argument('--version-file', type=Path, default=Path('firmware/src/firmware_version.h'))
    parser.add_argument('--output', type=Path, default=Path('release'))
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    result = package(args.image, args.version_file, args.output, args.source_commit)
    print(result['version'])
