"""Public firmware releases from the project's fixed GitHub repository."""
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'pidiman/stitky'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100'
MAX_IMAGE = 0x1D0000
LAYOUT = 'dual1856-v1'
VERSION = re.compile(r'^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})$')
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


class SourceError(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise SourceError('Vydanie nemá podporované označenie verzie.')
    return tuple(int(v) for v in value.split('.'))


def allowed_url(url):
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port
    except ValueError:
        raise SourceError('GitHub vrátil nepovolený odkaz na firmvér.') from None
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or port not in (None, 443):
        raise SourceError('GitHub vrátil nepovolený odkaz na firmvér.')


class GitHubRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, request, fp, code, message, headers, url):
        allowed_url(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def download(url, limit):
    allowed_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'FajnyPrintStudio-Firmware', 'Accept': 'application/vnd.github+json' if url.startswith('https://api.github.com/') else 'application/octet-stream'})
    opener = urllib.request.build_opener(GitHubRedirects())
    try:
        with opener.open(request, timeout=12) as response:
            allowed_url(response.geturl())
            length = response.headers.get('Content-Length')
            if length and int(length) > limit:
                raise SourceError('Súbor z GitHubu prekročil povolenú veľkosť.')
            result = bytearray(); deadline = time.monotonic() + 45
            while True:
                if time.monotonic() > deadline:
                    raise SourceError('Sťahovanie z GitHubu trvalo príliš dlho.')
                part = response.read(min(65536, limit + 1 - len(result)))
                if not part:
                    return bytes(result)
                result.extend(part)
                if len(result) > limit:
                    raise SourceError('Súbor z GitHubu prekročil povolenú veľkosť.')
    except SourceError:
        raise
    except (OSError, ValueError, urllib.error.URLError):
        raise SourceError('GitHub je dočasne nedostupný alebo obmedzil počet požiadaviek. Skús kontrolu neskôr.') from None


def asset_url(version, extension):
    version_tuple(version)
    return f'https://github.com/{REPOSITORY}/releases/download/firmware-v{version}/esp32-firmware-{version}.{extension}'


def read_latest(fetch):
    try:
        releases = json.loads(fetch(API_URL, 1024 * 1024))
        if not isinstance(releases, list):
            raise SourceError('GitHub vrátil neplatný zoznam vydaní.')
        candidates = []
        for r in releases:
            if not isinstance(r, dict) or r.get('draft') or r.get('prerelease'):
                continue
            tag = r.get('tag_name', '')
            if isinstance(tag, str) and tag.startswith('firmware-v') and VERSION.fullmatch(tag[10:]):
                candidates.append((version_tuple(tag[10:]), tag[10:], r))
        if not candidates:
            return None
        _, version, release = max(candidates, key=lambda r: r[0])
        assets = release.get('assets', [])
        if not isinstance(assets, list):
            raise SourceError('Vydanie nemá podporované súbory firmvéru.')
        names = {r.get('name'): r for r in assets if isinstance(r, dict) and r.get('state') == 'uploaded'}
        binary = names.get(f'esp32-firmware-{version}.bin')
        manifest = names.get(f'esp32-firmware-{version}.json')
        if not binary or not manifest:
            raise SourceError('Najnovšie vydanie nemá kompletný firmvér a kontrolné údaje pre ESP32.')
        data = json.loads(fetch(asset_url(version, 'json'), 16384))
        if not isinstance(data, dict) or type(data.get('schema')) is not int or data.get('schema') != 1 or data.get('product') != 'fajny-print-studio' or data.get('board') != 'esp32dev' or data.get('layout') != LAYOUT or data.get('version') != version or data.get('file') != f'esp32-firmware-{version}.bin':
            raise SourceError('Vydanie nie je kompatibilné s týmto ESP32 mostom.')
        size = data.get('size'); sha = data.get('sha256')
        if type(size) is not int or not 1024 <= size <= MAX_IMAGE or type(binary.get('size')) is not int or binary['size'] != size or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise SourceError('Vydanie má neplatnú veľkosť alebo kontrolný súčet.')
        if binary.get('digest') not in (None, 'sha256:' + sha):
            raise SourceError('Kontrolné údaje vydania a GitHubu sa nezhodujú.')
        return {'version': version, 'tag': 'firmware-v' + version, 'sha256': sha, 'size': size,
                'url': f'https://github.com/{REPOSITORY}/releases/tag/firmware-v{version}',
                'published_at': release.get('published_at')}
    except SourceError:
        raise
    except (ValueError, TypeError, KeyError):
        raise SourceError('GitHub vrátil neplatné údaje o firmvéri.') from None


class GitHubFirmwareSource:
    def __init__(self, transaction, fetch=None):
        self.transaction = transaction
        self.fetch = fetch or download
        self.lock = threading.Lock()

    def latest(self, force=False):
        # One shared cache avoids consuming the public GitHub API limit on each browser poll.
        with self.lock:
            now = time.time()
            with self.transaction() as c:
                row = c.execute('SELECT * FROM firmware_source_cache WHERE id=1').fetchone()
            if row and now - row['last_attempt'] < (60 if force or row['error'] else 300):
                return {'release': json.loads(row['payload']), 'checked_at': row['checked_at'], 'error': row['error'] or None}
            try:
                release = read_latest(self.fetch); error = ''; checked = now
            except SourceError as e:
                release = json.loads(row['payload']) if row else None
                checked = row['checked_at'] if row else None; error = str(e)
            with self.transaction() as c:
                c.execute('INSERT OR REPLACE INTO firmware_source_cache VALUES(1,?,?,?,?)', (checked, now, json.dumps(release), error))
            return {'release': release, 'checked_at': checked, 'error': error or None}

    def image(self, release):
        image = self.fetch(asset_url(release['version'], 'bin'), MAX_IMAGE)
        if len(image) != release['size'] or hashlib.sha256(image).hexdigest() != release['sha256']:
            raise SourceError('Stiahnutý firmvér nesúhlasí s kontrolnými údajmi vydania.')
        return image
