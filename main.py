#!/usr/bin/env python
import json
import math
import sys
from os.path import exists
from pathlib import Path
from typing import NoReturn

from github.trending import (
    fetch_trending_repos,
    get_repo_details,
    get_undone_repo,
    sanitize_repo_id,
)
from github.script_generator import generate_script, split_script_into_segments
from utils import settings
from utils.cleanup import cleanup
from utils.console import print_markdown, print_step, print_substep
from utils.ffmpeg_install import ffmpeg_install
from video_creation.background import (
    chop_background,
    download_background_audio,
    get_background_config,
)
from video_creation.final_video import make_final_video
from video_creation.screenshot_downloader import get_screenshots_of_github_repo
from video_creation.voices import save_text_to_mp3

__VERSION__ = "4.0.0"

print(
    """
 ██████╗ ██╗████████╗██╗  ██╗██╗   ██╗██████╗     ██╗   ██╗██╗██████╗ ███████╗ ██████╗
██╔════╝ ██║╚══██╔══╝██║  ██║██║   ██║██╔══██╗    ██║   ██║██║██╔══██╗██╔════╝██╔═══██╗
██║  ███╗██║   ██║   ███████║██║   ██║██████╔╝    ██║   ██║██║██║  ██║█████╗  ██║   ██║
██║   ██║██║   ██║   ██╔══██║██║   ██║██╔══██╗    ╚██╗ ██╔╝██║██║  ██║██╔══╝  ██║   ██║
╚██████╔╝██║   ██║   ██║  ██║╚██████╔╝██████╔╝     ╚████╔╝ ██║██████╔╝███████╗╚██████╔╝
 ╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝       ╚═══╝  ╚═╝╚═════╝ ╚══════╝ ╚═════╝

███╗   ███╗ █████╗ ██╗  ██╗███████╗██████╗     ██████╗  ██████╗ ████████╗
████╗ ████║██╔══██╗██║ ██╔╝██╔════╝██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
██╔████╔██║███████║█████╔╝ █████╗  ██████╔╝    ██████╔╝██║   ██║   ██║
██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  ██╔══██╗    ██╔══██╗██║   ██║   ██║
██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗██║  ██║    ██████╔╝╚██████╔╝   ██║
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝    ╚═════╝  ╚═════╝    ╚═╝
"""
)
print_markdown(
    "### GitHub Video Maker Bot v4.0 — Automatically create short-form videos about trending GitHub repos! 🚀"
)

content_id: str


def _load_done_ids() -> list:
    """Load the list of already-processed repo IDs from videos.json."""
    videos_json_path = "./video_creation/data/videos.json"
    if not exists(videos_json_path):
        return []
    try:
        with open(videos_json_path, "r", encoding="utf-8") as f:
            done_videos = json.load(f)
        return [video["id"] for video in done_videos]
    except (json.JSONDecodeError, KeyError):
        return []


def main() -> None:
    global content_id

    config = settings.config

    # --- Step 1: Fetch trending repos ---
    github_config = config.get("github", {})
    language = github_config.get("trending_language", "")
    since = github_config.get("trending_since", "daily")
    min_stars = github_config.get("min_stars", 100)
    token = github_config.get("api", {}).get("token", "")

    repos = fetch_trending_repos(
        language=language,
        since=since,
        min_stars=min_stars,
    )

    if not repos:
        print_markdown("## No trending repos found! Try adjusting your filters.")
        return

    # --- Step 2: Find an undone repo ---
    done_ids = _load_done_ids()
    repo = get_undone_repo(repos, done_ids)

    if repo is None:
        print_markdown(
            "## All trending repos have already been processed! Try again tomorrow. 🎉"
        )
        return

    print_step(f"Selected repo: {repo['full_name']} ⭐ {repo['stars']:,}")

    # --- Step 3: Get full repo details ---
    repo_data = get_repo_details(repo["full_name"], token=token)

    # --- Step 4: Generate narration script ---
    script = generate_script(repo_data, config)
    segments = split_script_into_segments(script)

    print_substep(f"Script has {len(segments)} segments.", style="bold blue")
    for i, seg in enumerate(segments):
        print_substep(f"  [{i+1}] {seg[:80]}{'...' if len(seg) > 80 else ''}")

    # --- Step 5: Build content object (compatible with existing pipeline) ---
    content_id = sanitize_repo_id(repo_data["full_name"])
    content_obj = {
        "thread_id": content_id,
        "thread_title": f"{repo_data['full_name']} — {repo_data['description'][:100]}"
        if repo_data["description"]
        else repo_data["full_name"],
        "thread_post": segments,  # List of script segments for storymode
        "is_nsfw": False,
    }

    # --- Step 6: Generate TTS audio ---
    length, number_of_segments = save_text_to_mp3(content_obj)
    length = math.ceil(length)
    print_substep(f"Total audio length: {length}s", style="bold blue")

    # --- Step 7: Take screenshots and record scrolling background ---
    get_screenshots_of_github_repo(repo_data, number_of_segments, length)

    # --- Step 8: Prepare background ---
    bg_config = {
        "audio": get_background_config("audio"),
        "video": ["", "", "GitHub Scroll", lambda t: ("center", t)] # mock structure for final_video.py
    }
    download_background_audio(bg_config["audio"])
    chop_background(bg_config, length, content_obj)

    # --- Step 9: Render final video ---
    make_final_video(number_of_segments, length, content_obj, bg_config)


def shutdown() -> NoReturn:
    if "content_id" in globals():
        print_markdown("## Clearing temp files")
        cleanup(content_id)

    print("Exiting...")
    sys.exit()


if __name__ == "__main__":
    if sys.version_info.major != 3 or sys.version_info.minor not in [10, 11, 12, 13]:
        print(
            "This program requires Python 3.10+. Please install a supported version and try again."
        )
        sys.exit()

    ffmpeg_install()

    directory = Path().absolute()
    config = settings.check_toml(
        f"{directory}/utils/.config.template.toml", f"{directory}/config.toml"
    )
    config is False and sys.exit()

    # Force storymode for GitHub content (always uses script segments)
    if "storymode" not in settings.config.get("settings", {}):
        settings.config["settings"]["storymode"] = True
    if "storymodemethod" not in settings.config.get("settings", {}):
        settings.config["settings"]["storymodemethod"] = 1

    repos_per_run = settings.config.get("github", {}).get("repos_per_run", 1)

    try:
        for run_idx in range(repos_per_run):
            if repos_per_run > 1:
                print_step(f"Processing repo {run_idx + 1} of {repos_per_run}")
            main()
    except KeyboardInterrupt:
        shutdown()
    except Exception as err:
        # Redact sensitive config values before printing
        safe_config = dict(settings.config.get("settings", {}))
        if "tts" in safe_config:
            safe_tts = dict(safe_config["tts"])
            for key in [
                "tiktok_sessionid",
                "elevenlabs_api_key",
                "openai_api_key",
            ]:
                if key in safe_tts:
                    safe_tts[key] = "REDACTED"
            safe_config["tts"] = safe_tts

        print_step(
            f"Sorry, something went wrong! Try again, and feel free to report this issue on GitHub.\n"
            f"Version: {__VERSION__} \n"
            f"Error: {err} \n"
            f"Config: {safe_config}"
        )
        raise err
