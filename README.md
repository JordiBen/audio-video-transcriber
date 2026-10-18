# Audio & Video Transcriber: Speech to Text, SRT & VTT Subtitles (Whisper)

[![Run on Apify](https://img.shields.io/badge/Run%20on-Apify-1f6feb?logo=apify)](https://apify.com/manageable_gully/audio-video-transcriber) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Run it in the cloud with no setup:** [Audio & Video Transcriber: Speech to Text & SRT Subtitles on the Apify Store](https://apify.com/manageable_gully/audio-video-transcriber).  
> Pay only per result, export to JSON/CSV/Excel, schedule runs and call it from the API.
<!-- Note: the Apify Store page goes live once the Actor is published. -->
<!-- AFFILIATE_LINK_PLACEHOLDER: replace the Apify links above with the affiliate link when available -->

Turn **audio and video files into text** with OpenAI's open-source **Whisper** speech recognition model. Paste links to MP3, MP4, WAV, M4A, WebM, OGG, FLAC or MOV files (or upload one), and get a clean transcript, **timestamped segments**, **SRT and WebVTT subtitle files**, optional **word-level timestamps** and **translation to English**. 99 languages with automatic language detection. No API key, no OpenAI account, no setup. You pay per minute of audio, from **$0.005 per minute**.

## What you can use it for
- **Podcast and interview transcripts:** searchable text and show notes from episodes and recorded calls.
- **Subtitles and captions:** SRT/VTT files for videos, courses, webinars and social clips, ready to upload to any video player or editor.
- **Meeting and lecture notes:** transcribe recordings, then summarize them with ChatGPT, Claude or your own LLM.
- **AI and RAG pipelines:** feed transcripts with timestamps into vector databases, agents and n8n/Make/Zapier workflows.
- **Translate speech to English:** Spanish, Hebrew, Arabic, French, German, Hindi and 90+ other languages to English text in one step.
- **Content repurposing:** turn videos into blog posts, quotes and newsletter material.

## How to use it
1. Paste one or more **direct file links** (or upload a file). Google Drive files shared as *Anyone with the link* and Dropbox links are converted automatically.
2. Pick **Fast** or **Accurate** quality and, optionally, the spoken language.
3. Click **Start**. Each file becomes one result row with the full text, plus links to the SRT, VTT and TXT files.

## Fast or Accurate?
| | Fast | Accurate |
|---|---|---|
| Model | Whisper base (int8) | Whisper small (int8, beam search 5) |
| Best for | Clear speech, English and major languages | Accents, noisy audio, names, non-English speech |
| Price | **$0.005 / audio minute** | **$0.010 / audio minute** |

## Pricing example
Billing is per started minute of audio in each file (a 30-minute podcast = 30 minutes), plus a tiny start fee. Files that fail to download or contain no speech are **not charged**.
| Job | Fast | Accurate |
|---|---|---|
| One 10-minute interview | $0.05 | $0.10 |
| Ten 30-minute podcast episodes (300 min) | $1.50 | $3.00 |
| 100 hours of lectures (6,000 min) | $30 | $60 |

## Features
- **Every common format:** anything FFmpeg can read, including video files (the audio track is extracted automatically).
- **99 languages** with auto-detect, or force a language for better accuracy.
- **Translate to English** (Whisper's built-in translation task).
- **SRT, WebVTT, TXT and JSON** files saved to the run's key-value store, with direct links in each result.
- **Word-level timestamps** with confidence scores (for karaoke-style captions, editing tools and search).
- **Silence skipping (VAD):** detects speech first, which avoids the "phantom text" Whisper can produce on silence or music.
- **Vocabulary hint:** give it names, brands or jargon to improve spelling.
- **Budget safe:** before transcribing, it checks your run's max cost and skips files that would exceed it.
- **Private by design:** files are processed inside your run and not stored anywhere else.

## Input example
```json
{
  "fileUrls": [{"url": "https://www.archive.org/download/count_monte_cristo_0711_librivox/count_of_monte_cristo_001_dumas.mp3"}],
  "quality": "fast",
  "language": "auto",
  "task": "transcribe",
  "outputFormats": ["srt", "vtt", "txt"],
  "wordTimestamps": false,
  "maxMinutesPerFile": 180
}
```

## Output example (one item per file)
```json
{
  "url": "https://www.archive.org/download/count_monte_cristo_0711_librivox/count_of_monte_cristo_001_dumas.mp3",
  "fileSizeMB": 18,
  "durationSeconds": 1179.5,
  "language": "en",
  "languageProbability": 0.962,
  "quality": "fast",
  "model": "whisper-base",
  "task": "transcribe",
  "transcribedSeconds": 300,
  "truncated": true,
  "billedMinutes": 5,
  "processingSeconds": 34.9,
  "segmentCount": 62,
  "text": "This is a Librevox recording. All Librevox recordings are in the public domain and for more information or to volunteer visit Librevox.org\n\nRecording by Christian Luoma, greenkri.com of the Count of Monte Cristo by Alexander Dumas ...",
  "wordCount": 728,
  "srtUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/001-count_of_monte_cristo_001_dumas.srt",
  "vttUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/001-count_of_monte_cristo_001_dumas.vtt",
  "txtUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/001-count_of_monte_cristo_001_dumas.txt",
  "segments": [
    {
      "start": 0.66,
      "end": 10.86,
      "text": "This is a Librevox recording. All Librevox recordings are in the public domain and for more information or to volunteer visit Librevox.org"
    },
    {
      "start": 12.86,
      "end": 22.3,
      "text": "Recording by Christian Luoma, greenkri.com of the Count of Monte Cristo by Alexander Dumas"
    }
  ]
}
```
This example was run with **Max minutes per file** = 5 on a 19.7-minute file, so only 5 minutes were transcribed and billed (`truncated: true`). With **Word-level timestamps** on, every segment also has a `words` array with `start`, `end`, `word` and `probability`.

Failed files produce a row with `url` and `error` (for example *File has no audio track* or *The link returned a web page, not a media file*) and are not charged.

## Use it from code, n8n or AI agents
Call it through the Apify API (`POST https://api.apify.com/v2/acts/manageable_gully~audio-video-transcriber/run-sync-get-dataset-items`), the Apify Python/JavaScript clients, the Apify n8n/Make/Zapier integrations, or as a tool for AI agents through the Apify MCP server.

## FAQ
**Which links work?** Direct links to media files (they should download the file, not open a web page), Apify key-value store records, S3/GCS signed URLs, Google Drive (shared publicly) and Dropbox share links.

**Can I transcribe YouTube, TikTok or Instagram links?** No. Those are web pages, and downloading from them breaks their terms. Download your own video file and pass its link instead.

**How long can a file be?** Up to 240 minutes and 1 GB per file. Use **Max minutes per file** to cap cost on long recordings.

**How accurate is it?** It's Whisper, the same open-source model family used by many paid services. Accuracy depends on audio quality; use **Accurate** for difficult audio and set the language when you know it.

**Speaker labels (diarization)?** Not yet. Segments are timestamped but not split by speaker.

**Is my audio used for training?** No. Transcription runs locally inside the Actor; nothing is sent to third-party AI APIs.

## More tools from WebIntel Tools
- [PDF & Image OCR to Text/Markdown](https://apify.com/manageable_gully/pdf-ocr-extractor)
- [Web Page to Markdown for LLMs](https://apify.com/manageable_gully/page-to-markdown)
- [URL to PDF & Screenshot](https://apify.com/manageable_gully/url-to-pdf-screenshot)
- [Website Health Audit](https://apify.com/manageable_gully/website-health-audit)

## Run from source
This repository is the full source of the [Audio & Video Transcriber: Speech to Text & SRT Subtitles](https://apify.com/manageable_gully/audio-video-transcriber) Actor.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest
# run locally with the Apify CLI (https://docs.apify.com/cli):
apify run --input '{...}'
```

Deploy your own copy with `apify push`. The easiest way to use it is the hosted version on the [Apify Store](https://apify.com/manageable_gully/audio-video-transcriber).

<!-- AFFILIATE_LINK_PLACEHOLDER: "New to Apify? Sign up here" link goes here -->

## License
MIT, see [LICENSE](LICENSE).
