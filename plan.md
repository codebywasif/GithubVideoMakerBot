# GitHub Video Maker Bot — Implementation Plan

## 1. High-Level Architecture

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐    ┌──────────────┐
│   GitHub     │───▶│  Script Gen  │───▶│  Screenshot    │───▶│  TTS Engine  │───▶│ Video Render │
│  Trending    │    │  (LLM)       │    │  (Playwright)  │    │  (existing)  │    │  (ffmpeg)    │
└─────────────┘    └──────────────┘    └────────────────┘    └──────────────┘    └──────────────┘
       │                                                                                │
       ▼                                                                                ▼
 ┌───────────┐                                                                  ┌──────────────┐
 │ History   │◀─────────────────────────────────────────────────────────────────│  results/    │
 │ (JSON)    │                                                                  │  github/     │
 └───────────┘                                                                  └──────────────┘
```

---

## 2. Module Breakdown

### Phase 1: GitHub Data Source (`github/`)

#### [NEW] `github/__init__.py`
Empty init file.

#### [NEW] `github/trending.py`
Replaces `reddit/subreddit.py`. Responsible for fetching trending repos.

**Key functions:**
- `fetch_trending_repos(language, since, min_stars) -> List[dict]`
  - Scrapes `https://github.com/trending?since={since}&spoken_language_code=` using `requests` + `BeautifulSoup`.
  - Parses each repo card: full name, description, stars, language, URL.
  - Falls back to GitHub REST API search if scraping fails.
- `get_repo_details(repo_full_name) -> dict`
  - Calls GitHub API `GET /repos/{owner}/{repo}` for full metadata.
  - Fetches README via `GET /repos/{owner}/{repo}/readme` (base64 decoded).
  - Returns enriched dict with: `full_name`, `description`, `stars`, `forks`, `language`, `topics`, `readme_excerpt`, `url`, `owner_avatar_url`.
- `get_undone_repo(repos, done_list) -> dict | None`
  - Filters out repos already in `videos.json`.
  - Returns the first undone repo, or `None` if all are done.

---

### Phase 2: Script Generation (`github/script_generator.py`)

#### [NEW] `github/script_generator.py`
Generates a TTS-ready narration script from repo metadata using an LLM.

**Key functions:**
- `generate_script(repo_data: dict, config: dict) -> str`
  - Builds a prompt from repo metadata (name, description, stars, language, readme excerpt).
  - Calls OpenAI Chat Completions API (`gpt-4o-mini` by default).
  - Returns a clean narration script (100-200 words).
- `split_script_into_segments(script: str) -> List[str]`
  - Splits the script into sentence-level segments for per-segment TTS + screenshot timing.

**Prompt template:**
```
You are a tech content creator making a 30-60 second video about a trending GitHub repository.
Write an engaging, informative narration script.

Repository: {full_name}
Stars: {stars} | Language: {language}
Description: {description}
README excerpt: {readme_excerpt}

Rules:
- Start with a hook that grabs attention
- Mention the repo name, what it does, and why it's trending
- Keep it under {max_words} words
- Write in a conversational, enthusiastic tone
- End with a call-to-action (check it out, star it, etc.)
```

---

### Phase 3: Screenshot Pipeline (`video_creation/screenshot_downloader.py`)

#### [MODIFY] `video_creation/screenshot_downloader.py`
Replace Reddit screenshot logic with GitHub repo screenshot logic.

**New function:** `get_screenshots_of_github_repo(repo_data: dict, num_segments: int)`
- Launches Playwright headless browser.
- Navigates to `https://github.com/{full_name}`.
- Takes screenshots:
  1. **Title screenshot**: Repo header area (name, description, stars, language badge).
  2. **README screenshot**: The rendered README section.
  3. **Code screenshot** (optional): A file from the repo's root directory.
- Saves to `assets/temp/{repo_id}/png/`.
- Segments are mapped to screenshots: title screenshot for the intro, README for the middle, code for details.

---

### Phase 4: Config & Settings

#### [NEW] `utils/.config.template.toml` (replace existing)
New TOML template with GitHub-specific and script-generation sections. Retains all existing `[settings]` sections for TTS, background, resolution, etc.

**New sections:**
```toml
[github]
trending_language = ""
trending_since = "daily"
min_stars = 100
repos_per_run = 1

[github.api]
token = ""

[script]
provider = "openai"
openai_api_key = ""
openai_model = "gpt-4o-mini"
max_script_words = 150
custom_prompt = ""
```

**Removed sections:** `[reddit.creds]`, `[reddit.thread]`, `[ai]`

#### [MODIFY] `utils/settings.py`
Update config references from `reddit.*` to `github.*` and `script.*`.

---

### Phase 5: TTS Integration

#### [MODIFY] `video_creation/voices.py`
Rename `save_text_to_mp3(reddit_obj)` → `save_text_to_mp3(content_obj)`.
The `content_obj` now has this shape:

```python
{
    "thread_id": "vercel-nextjs",        # used as folder name
    "thread_title": "Next.js - ...",     # for title TTS
    "thread_post": ["segment1", "segment2", ...],  # script segments
}
```

Since the existing TTS engine already supports `storymode` with method 1 (list of text segments),
we can reuse it almost directly by always running in "storymode method 1" internally.

#### [MODIFY] `TTS/engine_wrapper.py`
- Remove Reddit-specific text processing (link removal, AI/AGI expansion).
- Remove `translators` dependency.
- Adapt `add_periods()` for general script text.
- Change `self.reddit_object` → `self.content_object` (or keep for compatibility).

---

### Phase 6: Video Assembly

#### [MODIFY] `video_creation/final_video.py`
- Replace Reddit-specific title card logic with GitHub repo title card.
- `create_fancy_thumbnail()` → show repo name, stars, and language instead of Reddit thread title.
- Update overlay timing to match script segments to screenshots.
- Change output path from `results/{subreddit}/` to `results/github/`.
- Remove Reddit-specific name normalization and translation.

#### [MODIFY] `video_creation/background.py`
Minimal changes — the background download and chopping logic is content-agnostic.
- Remove `reddit_object["thread_id"]` references; use `content_object["thread_id"]` instead.

---

### Phase 7: Main Entry Point

#### [MODIFY] `main.py`
Complete rewrite of the main flow:

```python
def main():
    # 1. Load config
    # 2. Fetch trending repos
    repos = fetch_trending_repos(...)
    
    # 3. Find undone repo
    repo = get_undone_repo(repos)
    if not repo:
        print("All trending repos already processed!")
        return
    
    # 4. Get full repo details
    repo_data = get_repo_details(repo)
    
    # 5. Generate script
    script = generate_script(repo_data)
    segments = split_script_into_segments(script)
    
    # 6. Build content object (compatible with existing pipeline)
    content_obj = {
        "thread_id": sanitize_id(repo_data["full_name"]),
        "thread_title": f"{repo_data['full_name']} — {repo_data['description']}",
        "thread_post": segments,
    }
    
    # 7. Generate TTS audio
    length, num_segments = save_text_to_mp3(content_obj)
    
    # 8. Take screenshots
    get_screenshots_of_github_repo(repo_data, num_segments)
    
    # 9. Prepare background
    bg_config = ...
    download_background_video(bg_config["video"])
    download_background_audio(bg_config["audio"])
    chop_background(bg_config, length, content_obj)
    
    # 10. Render final video
    make_final_video(num_segments, length, content_obj, bg_config)
```

---

### Phase 8: History & Deduplication

#### [MODIFY] `utils/videos.py`
- Update `check_done()` to work with repo full names instead of Reddit submission IDs.
- Update `save_data()` to store GitHub-specific metadata.

#### [MODIFY] `video_creation/data/videos.json`
Keep the existing JSON array format but with GitHub fields:
```json
[
  {
    "source": "github",
    "id": "vercel-nextjs",
    "repo_full_name": "vercel/next.js",
    "time": "1716321600",
    "background_credit": "Minecraft",
    "video_title": "Next.js - The React Framework",
    "filename": "Nextjs-The-React-Framework.mp4"
  }
]
```

---

### Phase 9: Cleanup

#### [DELETE] `reddit/` directory
Remove the entire Reddit module.

#### [MODIFY] `requirements.txt`
```diff
- praw==7.8.1
- translators==5.9.9
- spacy==3.8.7
- torch==2.7.0
- transformers==4.52.4
+ openai>=1.30.0
+ beautifulsoup4>=4.12.0
```

#### [DELETE] Old Reddit-specific utilities
- Remove `utils/subreddit.py`
- Remove `utils/posttextparser.py`
- Clean up `utils/ai_methods.py` (no longer needed)

#### [MODIFY] `utils/id.py`
Generalize `extract_id()` to work with the new content object format.

#### [MODIFY] `utils/cleanup.py`
No changes needed — already generic.

---

## 3. File Change Summary

| Action | File | Description |
|--------|------|-------------|
| **NEW** | `github/__init__.py` | Package init |
| **NEW** | `github/trending.py` | GitHub trending repo fetcher |
| **NEW** | `github/script_generator.py` | LLM-powered script generation |
| **MODIFY** | `main.py` | New orchestration flow |
| **MODIFY** | `video_creation/screenshot_downloader.py` | GitHub repo screenshots |
| **MODIFY** | `video_creation/voices.py` | Generalized TTS entry point |
| **MODIFY** | `video_creation/final_video.py` | GitHub-themed video assembly |
| **MODIFY** | `video_creation/background.py` | Minor: generalize object references |
| **MODIFY** | `TTS/engine_wrapper.py` | Remove Reddit-specific text processing |
| **MODIFY** | `utils/.config.template.toml` | New config schema |
| **MODIFY** | `utils/settings.py` | Config path updates |
| **MODIFY** | `utils/videos.py` | GitHub-oriented history tracking |
| **MODIFY** | `utils/id.py` | Generalize ID extraction |
| **MODIFY** | `requirements.txt` | Swap Reddit deps for GitHub/OpenAI deps |
| **DELETE** | `reddit/subreddit.py` | No longer needed |
| **DELETE** | `utils/subreddit.py` | No longer needed |
| **DELETE** | `utils/posttextparser.py` | No longer needed |
| **DELETE** | `utils/ai_methods.py` | No longer needed |

---

## 4. Execution Order

1. **Phase 1** — Create `github/trending.py` (data source)
2. **Phase 2** — Create `github/script_generator.py` (script generation)
3. **Phase 4** — Update config template and settings
4. **Phase 5** — Adapt TTS pipeline (`voices.py`, `engine_wrapper.py`)
5. **Phase 3** — Rewrite screenshot pipeline
6. **Phase 6** — Update video assembly (`final_video.py`, `background.py`)
7. **Phase 7** — Rewrite `main.py`
8. **Phase 8** — Update history tracking
9. **Phase 9** — Delete old files, update requirements

---

## 5. Scheduling (External)

The bot processes **1 repo per run**. To schedule daily execution:

### Windows Task Scheduler
```
Action: Start a program
Program: python
Arguments: main.py
Start in: C:\Users\Hp\source\repos\GithubVideoMakerBot
Trigger: Daily at desired time
```

### Linux/macOS Cron
```cron
0 9 * * * cd /path/to/GithubVideoMakerBot && python main.py >> /var/log/github-video-bot.log 2>&1
```

---

## 6. Testing Strategy

1. **Unit test `github/trending.py`** — Mock HTTP responses, verify parsing.
2. **Unit test `github/script_generator.py`** — Mock OpenAI API, verify script format.
3. **Integration test** — Run full pipeline on a single repo with `repos_per_run = 1`.
4. **Manual verification** — Watch the generated video to check quality.
5. **History test** — Run twice, verify the second run skips the first repo.
