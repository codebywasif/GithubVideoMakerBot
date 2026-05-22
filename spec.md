# GitHub Video Maker Bot — Product Specification

## 1. Overview

**GitHub Video Maker Bot** is an automated tool that discovers trending repositories on GitHub,
generates engaging narrated short-form videos (YouTube Shorts / TikTok format, 9:16 aspect ratio)
about each repository, and maintains a persistent history so it never creates duplicate videos.

It is built by repurposing the existing *Reddit Video Maker Bot* codebase — replacing the Reddit
data source with GitHub, the Reddit screenshot pipeline with GitHub repository screenshots, and
the Reddit-oriented script generation with an LLM-powered scriptwriter.

---

## 2. Goals

| # | Goal | Success Criteria |
|---|------|-----------------|
| G1 | Automatically discover trending GitHub repos | Fetches daily trending repos from GitHub (any language, configurable) |
| G2 | Generate a narrated video script from repo data | LLM (OpenAI / local) produces a 30-60s script from repo name, description, README, topics, and stars |
| G3 | Capture visual assets for the video | Screenshots of the repo page (main page, README, code snippets) via Playwright |
| G4 | Assemble a complete short-form video | Combines background gameplay, TTS narration, repo screenshots, and text overlays into a final MP4 |
| G5 | Track completed repos | Persistent JSON ledger prevents re-processing |
| G6 | Run on a daily schedule | Processes 1 repo per run; can be scheduled via cron / Task Scheduler |

---

## 3. Core Concepts

### 3.1 Data Source: GitHub Trending

- **Primary source**: GitHub Trending page (`https://github.com/trending`) scraped via HTTP or the
  unofficial `github-trending-api`.
- **Fallback**: GitHub REST/GraphQL API search sorted by stars with `created:>YYYY-MM-DD`.
- **Filtering**: Language filter (optional), minimum stars, exclude already-processed repos.

### 3.2 Script Generation

For each repo the bot collects:

| Field | Source |
|-------|--------|
| `repo_full_name` | e.g. `vercel/next.js` |
| `description` | One-line description from GitHub |
| `stars` | Star count |
| `language` | Primary language |
| `topics` | Topic tags |
| `readme_excerpt` | First ~500 chars of README.md (fetched via API) |

These fields are fed into an **LLM prompt** that outputs a narration script of ~100-200 words
(targeting 30-60 seconds of TTS audio). The prompt instructs the LLM to write in an engaging,
informative, short-form video style.

### 3.3 Visual Assets

Using **Playwright** (already a dependency), the bot:

1. Navigates to `https://github.com/{owner}/{repo}`.
2. Takes a full-page screenshot of the repo header (name, description, stars, language badge).
3. Takes a screenshot of the README section.
4. Optionally takes a screenshot of a highlighted code file.

Screenshots are cropped/resized to fit within the 1080×1920 video frame.

### 3.4 Video Assembly Pipeline

The existing pipeline is reused with modifications:

1. **TTS** — The generated script is split into segments and converted to MP3 via the existing
   TTS engine (TikTok, OpenAI, ElevenLabs, gTTS, etc.).
2. **Background** — A background gameplay video (Minecraft, GTA, etc.) is chopped to match the
   audio length (existing logic).
3. **Overlay** — Repo screenshots are overlaid on the background, timed to the audio segments.
4. **Title card** — A branded title card showing the repo name and star count.
5. **Final render** — ffmpeg composites everything into a 1080×1920 MP4.

### 3.5 History / Deduplication

A JSON file (`video_creation/data/videos.json`) stores every repo that has been processed:

```json
{
  "repo_full_name": "vercel/next.js",
  "id": "vercel-nextjs",
  "time": "1716321600",
  "background_credit": "Minecraft",
  "video_title": "Next.js - The React Framework",
  "filename": "Next-js-The-React-Framework.mp4"
}
```

Before processing, the bot checks this list and skips any repo already present.

### 3.6 Scheduling

The bot is designed to be invoked once per execution (processing **1 repo**). Scheduling is
handled externally:

- **Windows**: Task Scheduler runs `python main.py` daily.
- **Linux/macOS**: cron job.
- **Docker**: cron inside the container.

---

## 4. Configuration

A new TOML config replaces the Reddit-centric one:

```toml
[github]
trending_language = ""           # e.g. "python", "" for all
trending_since = "daily"         # "daily", "weekly", "monthly"
min_stars = 100                  # minimum star count filter
repos_per_run = 1                # how many repos to process per invocation

[github.api]
token = ""                       # optional GitHub PAT for higher rate limits

[script]
provider = "openai"              # "openai" or "local"
openai_api_key = ""
openai_model = "gpt-4o-mini"
max_script_words = 150           # target word count for the narration
custom_prompt = ""               # optional override for the system prompt

[settings]
# ... (existing settings: resolution, theme, background, TTS, etc.)
```

---

## 5. Output

| Artifact | Path |
|----------|------|
| Final video | `results/github/{RepoName}.mp4` |
| Thumbnail | `assets/temp/{repo_id}/thumbnail.png` |
| History | `video_creation/data/videos.json` |
| Temp assets | `assets/temp/{repo_id}/` (cleaned up after render) |

---

## 6. Non-Goals (v1)

- Automatic upload to YouTube/TikTok (future enhancement).
- Web GUI for managing the queue (CLI only for now).
- Multi-language narration.
- Live GitHub webhook triggers.

---

## 7. Dependencies

### Retained from existing project
- `moviepy`, `ffmpeg-python`, `Pillow` — video/image processing
- `playwright` — browser automation for screenshots
- TTS engines (TikTok, OpenAI, ElevenLabs, gTTS, AWS Polly, pyttsx, Streamlabs)
- `rich` — console output
- `toml` / `tomlkit` — config management
- `yt-dlp` — background video download

### New
- `requests` (already present) — GitHub API / trending page scraping
- `openai` — LLM script generation (or use existing `openai` TTS dep)
- `beautifulsoup4` — HTML parsing for GitHub trending page

### Removed
- `praw` / `prawcore` — Reddit API (no longer needed)
- `translators` — translation support (removed for simplicity)
- `spacy`, `torch`, `transformers` — AI similarity sorting (replaced by LLM script generation)
