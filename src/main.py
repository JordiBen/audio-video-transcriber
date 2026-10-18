"""Apify entrypoint: audio & video to text with Whisper (faster-whisper, CPU). Subtitles (SRT/VTT), plain text, segments."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time

import httpx
from apify import Actor

from .transcribe import (MediaError, Options, billed_minutes, blocked_platform, decode_audio, download, file_slug,
                         normalize_url, parse_input, probe_duration, to_srt, to_text, to_vtt)

MODEL_DIR = os.environ.get('WHISPER_MODEL_DIR', '/models')
_models: dict = {}


def cpu_threads() -> int:
    if Actor.is_at_home():
        mem = int(os.environ.get('ACTOR_MEMORY_MBYTES') or os.environ.get('APIFY_MEMORY_MBYTES') or 4096)
        return max(1, mem // 4096)  # Apify gives 1 CPU core per 4 GB of memory
    return min(4, os.cpu_count() or 1)


def get_model(name: str):
    if name not in _models:
        from faster_whisper import WhisperModel
        local = os.path.join(MODEL_DIR, name)
        src = local if os.path.isdir(local) else name
        _models[name] = WhisperModel(src, device='cpu', compute_type='int8', cpu_threads=cpu_threads())
    return _models[name]


def run_whisper(path: str, opts: Options, max_seconds: float) -> tuple[list[dict], object]:
    audio = decode_audio(path, max_seconds)
    model = get_model(opts.model)
    segs, info = model.transcribe(audio, language=opts.language, task=opts.task, beam_size=1 if opts.quality == 'fast' else 5,
                                  vad_filter=opts.vad, word_timestamps=opts.word_timestamps,
                                  initial_prompt=opts.initial_prompt, condition_on_previous_text=False)
    out = []
    for s in segs:
        d = {'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()}
        if opts.word_timestamps and s.words:
            d['words'] = [{'start': round(w.start, 2), 'end': round(w.end, 2), 'word': w.word.strip(),
                           'probability': round(w.probability, 3)} for w in s.words]
        out.append(d)
    return out, info


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        try:
            urls, opts = parse_input(inp)
        except ValueError as e:
            await Actor.fail(status_message=str(e))
            return
        if os.environ.get('ALLOW_PRIVATE_NETWORK_FOR_LOCAL_DEV') == '1' and not Actor.is_at_home():
            opts.allow_private = True
        kvs = await Actor.open_key_value_store()
        cm = Actor.get_charging_manager()
        done = budget_hit = 0
        minutes_total = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, read=300), headers={'User-Agent': 'Mozilla/5.0 (compatible; AudioVideoTranscriber/1.0)'}) as client:
            for n, raw in enumerate(urls, 1):
                rec: dict = {'url': raw}
                with tempfile.TemporaryDirectory() as td:
                    try:
                        plat = blocked_platform(raw)
                        if plat:
                            raise MediaError(f'{plat} pages are not supported. Provide a direct link to an audio/video file you have the rights to.')
                        url = normalize_url(raw)
                        await Actor.set_status_message(f'File {n}/{len(urls)}: downloading')
                        path = os.path.join(td, 'media')
                        size, _ = await download(client, url, path, opts)
                        rec['fileSizeMB'] = round(size / 1048576, 2)
                        duration = await asyncio.to_thread(probe_duration, path)
                        rec['durationSeconds'] = round(duration, 2)
                        limit_s = opts.max_minutes * 60
                        truncated = duration > limit_s
                        use_s = min(duration, limit_s)
                        minutes = billed_minutes(use_s)
                        allowed = cm.calculate_max_event_charge_count_within_limit(opts.event)
                        if allowed is not None and allowed < minutes:
                            budget_hit = True
                            raise MediaError(f'Skipped: needs {minutes} audio minute(s) but your max charge per run allows {allowed}. Raise the run\'s max cost limit.')
                        await Actor.set_status_message(f'File {n}/{len(urls)}: transcribing {use_s / 60:.1f} min ({opts.quality})')
                        t0 = time.time()
                        segments, info = await asyncio.to_thread(run_whisper, path, opts, limit_s if truncated else None)
                        rec.update({
                            'language': info.language, 'languageProbability': round(info.language_probability, 3),
                            'quality': opts.quality, 'model': f'whisper-{opts.model}', 'task': opts.task,
                            'transcribedSeconds': round(use_s, 2), 'truncated': truncated,
                            'billedMinutes': minutes, 'processingSeconds': round(time.time() - t0, 1),
                            'segmentCount': len(segments), 'text': to_text(segments),
                        })
                        rec['wordCount'] = len(rec['text'].split())
                        slug = file_slug(url, n)
                        files = {'srt': (to_srt, 'application/x-subrip; charset=utf-8'),
                                 'vtt': (to_vtt, 'text/vtt; charset=utf-8'),
                                 'txt': (lambda s: rec['text'], 'text/plain; charset=utf-8'),
                                 'json': (lambda s: json.dumps(s, ensure_ascii=False), 'application/json; charset=utf-8')}
                        for fmt in opts.formats:
                            fn, ctype = files[fmt]
                            key = f'{slug}.{fmt}'
                            await kvs.set_value(key, fn(segments), content_type=ctype)
                            rec[f'{fmt}Url'] = await kvs.get_public_url(key)
                        if opts.include_segments:
                            rec['segments'] = segments
                        if segments:
                            res = await Actor.charge(opts.event, count=minutes)
                            rec['billedMinutes'] = res.charged_count
                            minutes_total += res.charged_count
                        else:
                            rec['billedMinutes'] = 0
                            rec['note'] = 'No speech detected (not charged).'
                        done += 1
                    except MediaError as e:
                        rec['error'] = str(e)[:300]
                    except httpx.HTTPError as e:
                        rec['error'] = f'Download failed: {type(e).__name__}'
                    except Exception as e:  # noqa: BLE001 - one bad file must not kill the batch
                        Actor.log.exception('File failed')
                        rec['error'] = f'Processing failed: {str(e)[:200]}'
                await Actor.push_data(rec)
        msg = f'Done: {done}/{len(urls)} file(s), {minutes_total} audio minute(s)'
        if budget_hit:
            msg += ' (some files skipped: max charge reached)'
        await Actor.set_status_message(msg, is_terminal=True)
