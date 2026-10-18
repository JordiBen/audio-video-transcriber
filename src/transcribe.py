"""Pure helpers for the transcriber: input parsing, URL normalisation, download, probe/decode, subtitle formatting."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from .netguard import assert_public_url

MODELS = {'fast': 'base', 'accurate': 'small'}
EVENTS = {'fast': 'audio-minute', 'accurate': 'audio-minute-accurate'}
OUTPUT_FORMATS = ('srt', 'vtt', 'txt', 'json')
# Pages on these platforms are not files: downloading from them breaks their terms. We only take direct file links.
BLOCKED_HOSTS = ('youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'facebook.com', 'fb.watch', 'x.com',
                 'twitter.com', 'vimeo.com', 'spotify.com', 'soundcloud.com', 'twitch.tv', 'dailymotion.com',
                 'linkedin.com', 'reddit.com', 'netflix.com')
LANG_RE = re.compile(r'^[a-z]{2,3}$')


class MediaError(ValueError):
    pass


@dataclass
class Options:
    quality: str = 'fast'
    language: str | None = None
    task: str = 'transcribe'
    word_timestamps: bool = False
    vad: bool = True
    max_minutes: int = 180
    max_bytes: int = 1024 * 1024 * 1024
    formats: tuple[str, ...] = ('srt', 'vtt', 'txt')
    include_segments: bool = True
    initial_prompt: str | None = None
    allow_private: bool = False

    @property
    def model(self) -> str:
        return MODELS[self.quality]

    @property
    def event(self) -> str:
        return EVENTS[self.quality]


def blocked_platform(url: str) -> str | None:
    host = (urlsplit(url).hostname or '').lower()
    for b in BLOCKED_HOSTS:
        if host == b or host.endswith('.' + b):
            return b
    return None


def normalize_url(url: str) -> str:
    """Turn common share links into direct-download links (Google Drive, Dropbox, OneDrive is left as is)."""
    url = url.strip()
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    if host == 'drive.google.com':
        m = re.search(r'/file/d/([\w-]+)', p.path)
        fid = m.group(1) if m else (parse_qs(p.query).get('id') or [None])[0]
        if fid:
            return f'https://drive.google.com/uc?export=download&id={fid}'
    if host in ('www.dropbox.com', 'dropbox.com'):
        q = parse_qs(p.query)
        q['dl'] = ['1']
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode({k: v[0] for k, v in q.items()}), ''))
    return url


def parse_input(inp: dict) -> tuple[list[str], Options]:
    urls: list[str] = []
    for s in (inp.get('fileUrls') or []):
        u = (s.get('url') if isinstance(s, dict) else s) or ''
        u = u.strip()
        if u and u not in urls:
            urls.append(u)
    up = (inp.get('uploadedFile') or '').strip()
    if up and up not in urls:
        urls.insert(0, up)
    if not urls:
        raise ValueError('Provide at least one audio or video file link in "fileUrls" (or upload a file).')
    quality = inp.get('quality', 'fast')
    if quality not in MODELS:
        raise ValueError('quality must be "fast" or "accurate"')
    lang = (inp.get('language') or 'auto').strip().lower()
    if lang in ('', 'auto'):
        lang = None
    elif not LANG_RE.match(lang):
        raise ValueError('language must be "auto" or an ISO 639-1 code such as "en", "he", "es"')
    task = inp.get('task', 'transcribe')
    if task not in ('transcribe', 'translate'):
        raise ValueError('task must be "transcribe" or "translate" (translate = output in English)')
    fmts = tuple(dict.fromkeys(inp.get('outputFormats') or ['srt', 'vtt', 'txt']))
    bad = [f for f in fmts if f not in OUTPUT_FORMATS]
    if bad:
        raise ValueError(f'Unsupported output format(s): {bad}. Use {list(OUTPUT_FORMATS)}')
    prompt = (inp.get('vocabularyHint') or '').strip()[:600] or None
    opts = Options(quality=quality, language=lang, task=task, word_timestamps=bool(inp.get('wordTimestamps', False)),
                   vad=bool(inp.get('skipSilence', True)),
                   max_minutes=int(min(max(int(inp.get('maxMinutesPerFile', 180)), 1), 240)),
                   formats=fmts, include_segments=bool(inp.get('includeSegments', True)), initial_prompt=prompt)
    return urls, opts


async def download(client: httpx.AsyncClient, url: str, dest: str, opts: Options) -> tuple[int, str]:
    """Stream url to dest. Returns (bytes, final_url)."""
    await assert_public_url(url, allow_private=opts.allow_private)
    async with client.stream('GET', url, follow_redirects=True) as r:
        if r.status_code >= 400:
            raise MediaError(f'Download failed: HTTP {r.status_code}')
        final = str(r.url)
        await assert_public_url(final, allow_private=opts.allow_private)
        ctype = (r.headers.get('content-type') or '').lower()
        if ctype.startswith('text/html'):
            raise MediaError('The link returned a web page, not a media file. Use a direct download link '
                             '(for Google Drive, the file must be shared as "Anyone with the link").')
        declared = int(r.headers.get('content-length') or 0)
        if declared > opts.max_bytes:
            raise MediaError(f'File too large ({declared // 1048576} MB > {opts.max_bytes // 1048576} MB)')
        n = 0
        with open(dest, 'wb') as f:
            async for chunk in r.aiter_bytes(1 << 20):
                n += len(chunk)
                if n > opts.max_bytes:
                    raise MediaError(f'File too large (> {opts.max_bytes // 1048576} MB)')
                f.write(chunk)
    if n == 0:
        raise MediaError('Downloaded file is empty')
    return n, final


def probe_duration(path: str) -> float:
    """Duration in seconds of the first audio stream (ffprobe). Raises MediaError if there is no audio."""
    if not shutil.which('ffprobe'):
        raise RuntimeError('ffprobe not installed')
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=duration:format=duration',
                        '-of', 'json', path], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise MediaError('Not a readable audio/video file')
    d = json.loads(r.stdout or '{}')
    if not d.get('streams'):
        raise MediaError('File has no audio track')
    for v in (d['streams'][0].get('duration'), (d.get('format') or {}).get('duration')):
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except ValueError:
            pass
    # Some containers (e.g. streamed webm) lack a duration header: decode to measure.
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-f', 'null', '-'], capture_output=True, text=True, timeout=1800)
    m = re.findall(r'time=(\d+):(\d+):([\d.]+)', r.stderr)
    if m:
        h, mi, s = m[-1]
        return int(h) * 3600 + int(mi) * 60 + float(s)
    raise MediaError('Could not determine audio duration')


def decode_audio(path: str, max_seconds: float | None = None):
    """Decode to 16 kHz mono float32 numpy array via ffmpeg."""
    import numpy as np
    cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '16000']
    if max_seconds:
        cmd += ['-t', str(max_seconds)]
    cmd += ['-f', 'f32le', '-']
    r = subprocess.run(cmd, capture_output=True, timeout=3600)
    if r.returncode != 0 or not r.stdout:
        raise MediaError('Could not decode audio: ' + r.stderr.decode('utf-8', 'replace')[-200:])
    return np.frombuffer(r.stdout, dtype=np.float32)


def billed_minutes(duration_s: float) -> int:
    return max(1, math.ceil(round(duration_s, 2) / 60))


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}'


def to_srt(segments: list[dict]) -> str:
    out = []
    for i, s in enumerate(segments, 1):
        out.append(f"{i}\n{_ts(s['start'], ',')} --> {_ts(s['end'], ',')}\n{s['text'].strip()}\n")
    return '\n'.join(out)


def to_vtt(segments: list[dict]) -> str:
    out = ['WEBVTT\n']
    for s in segments:
        out.append(f"{_ts(s['start'], '.')} --> {_ts(s['end'], '.')}\n{s['text'].strip()}\n")
    return '\n'.join(out)


def to_text(segments: list[dict]) -> str:
    """Plain text with paragraph breaks at pauses > 1.5 s."""
    paras, cur, prev_end = [], [], None
    for s in segments:
        t = s['text'].strip()
        if not t:
            continue
        if prev_end is not None and s['start'] - prev_end > 1.5 and cur:
            paras.append(' '.join(cur))
            cur = []
        cur.append(t)
        prev_end = s['end']
    if cur:
        paras.append(' '.join(cur))
    return '\n\n'.join(paras)


def file_slug(url: str, n: int) -> str:
    name = urlsplit(url).path.rsplit('/', 1)[-1] or 'file'
    name = re.sub(r'\.[A-Za-z0-9]{1,5}$', '', name)
    name = re.sub(r'[^A-Za-z0-9_-]+', '-', name).strip('-')[:60] or 'file'
    return f'{n:03d}-{name}'
