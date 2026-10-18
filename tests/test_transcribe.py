import os
import pathlib

import pytest

from src.transcribe import (MediaError, billed_minutes, blocked_platform, file_slug, normalize_url, parse_input,
                            probe_duration, to_srt, to_text, to_vtt)

FIX = pathlib.Path(__file__).parent / 'fixtures'
SEGS = [{'start': 0.0, 'end': 2.5, 'text': ' Hello there.'}, {'start': 2.6, 'end': 4.0, 'text': 'Second line'},
        {'start': 7.0, 'end': 3725.123, 'text': 'After a pause'}]


def test_parse_defaults():
    urls, o = parse_input({'fileUrls': [{'url': 'https://a.com/x.mp3'}, 'https://a.com/x.mp3']})
    assert urls == ['https://a.com/x.mp3']
    assert o.quality == 'fast' and o.model == 'base' and o.event == 'audio-minute' and o.language is None
    assert o.formats == ('srt', 'vtt', 'txt') and o.vad


def test_parse_options_and_errors():
    urls, o = parse_input({'uploadedFile': 'https://kv/u', 'quality': 'accurate', 'language': 'HE', 'task': 'translate',
                           'outputFormats': ['json'], 'maxMinutesPerFile': 9999})
    assert urls == ['https://kv/u'] and o.model == 'small' and o.event == 'audio-minute-accurate'
    assert o.language == 'he' and o.task == 'translate' and o.max_minutes == 240
    for bad in ({}, {'fileUrls': ['u'], 'quality': 'x'}, {'fileUrls': ['u'], 'language': 'english'},
                {'fileUrls': ['u'], 'outputFormats': ['doc']}, {'fileUrls': ['u'], 'task': 'sum'}):
        with pytest.raises(ValueError):
            parse_input(bad)


def test_blocked_and_normalize():
    assert blocked_platform('https://www.youtube.com/watch?v=1') == 'youtube.com'
    assert blocked_platform('https://m.tiktok.com/@a/video/1') == 'tiktok.com'
    assert blocked_platform('https://cdn.example.com/a.mp3') is None
    assert normalize_url('https://drive.google.com/file/d/AbC_12-x/view?usp=sharing') == 'https://drive.google.com/uc?export=download&id=AbC_12-x'
    assert normalize_url('https://www.dropbox.com/s/abc/f.mp3?dl=0') == 'https://www.dropbox.com/s/abc/f.mp3?dl=1'
    assert normalize_url(' https://x.com/a.mp3 ') == 'https://x.com/a.mp3'


def test_formats():
    srt = to_srt(SEGS)
    assert srt.startswith('1\n00:00:00,000 --> 00:00:02,500\nHello there.\n')
    assert '01:02:05,123' in srt
    vtt = to_vtt(SEGS)
    assert vtt.startswith('WEBVTT\n') and '00:00:02.600 --> 00:00:04.000' in vtt
    assert to_text(SEGS) == 'Hello there. Second line\n\nAfter a pause'


def test_billing_and_slug():
    assert billed_minutes(0.5) == 1 and billed_minutes(60.0) == 1 and billed_minutes(60.4) == 2 and billed_minutes(600) == 10
    assert file_slug('https://a.com/path/My File (1).mp3?x=1', 3) == '003-My-File-1'
    assert file_slug('https://a.com/', 1) == '001-file'


def test_probe():
    assert abs(probe_duration(str(FIX / 'speech25.mp3')) - 25) < 0.5
    with pytest.raises(MediaError):
        probe_duration(str(FIX / '__init__.py' if (FIX / '__init__.py').exists() else __file__))


@pytest.mark.skipif(os.environ.get('SKIP_MODEL_TESTS') == '1', reason='model test disabled')
def test_whisper_end_to_end():
    from src.main import run_whisper
    from src.transcribe import Options
    segs, info = run_whisper(str(FIX / 'speech25.mp3'), Options(), None)
    text = ' '.join(s['text'] for s in segs).lower()
    assert info.language == 'en' and 'public domain' in text
    segs, _ = run_whisper(str(FIX / 'silence5.wav'), Options(), None)
    assert segs == []
