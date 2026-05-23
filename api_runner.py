"""
api_runner.py — Interruptible video creation pipeline for the web UI.

Provides a VideoCreationJob class that runs the existing pipeline in a
background thread, pausing after script generation to allow user
approval/editing before proceeding to TTS + rendering.

Progress is reported via callback functions that the Flask SSE endpoint
can consume.
"""

import json
import math
import re
import threading
import time
import traceback
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional


class JobState(str, Enum):
    IDLE = "idle"
    FETCHING = "fetching"
    SCRIPT_READY = "script_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    GENERATING_TTS = "generating_tts"
    SCREENSHOTS = "screenshots"
    BACKGROUND = "background"
    RENDERING = "rendering"
    COMPLETE = "complete"
    ERROR = "error"


class VideoCreationJob:
    """Manages a single video creation run with pause/resume semantics."""

    def __init__(self):
        self.state: JobState = JobState.IDLE
        self.progress: int = 0
        self.message: str = ""
        self.error: Optional[str] = None

        # Repo data populated during FETCHING
        self.repo_data: Optional[Dict] = None
        self.trending_repos: List[Dict] = []

        # Script populated during SCRIPT_READY
        self.script: Optional[str] = None
        self.segments: Optional[List[str]] = None

        # Result populated during COMPLETE
        self.result_filename: Optional[str] = None
        self.result_video_id: Optional[str] = None

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._approval_event = threading.Event()
        self._approved_script: Optional[str] = None
        self._lock = threading.Lock()

        # Progress subscribers (SSE consumers)
        self._subscribers: List[Callable] = []

    def subscribe(self, callback: Callable):
        """Register a callback that receives (state, progress, message) updates."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """Remove a progress subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _notify(self, state: JobState, progress: int, message: str):
        """Update state and notify all subscribers."""
        with self._lock:
            self.state = state
            self.progress = progress
            self.message = message

        for cb in self._subscribers[:]:
            try:
                cb(state, progress, message)
            except Exception:
                pass

    def start(self, config_overrides: Optional[Dict] = None):
        """Start the video creation pipeline in a background thread."""
        if self.state not in (JobState.IDLE, JobState.COMPLETE, JobState.ERROR):
            raise RuntimeError(f"Cannot start job in state {self.state}")

        # Reset
        self.state = JobState.IDLE
        self.progress = 0
        self.error = None
        self.repo_data = None
        self.script = None
        self.segments = None
        self.result_filename = None
        self.result_video_id = None
        self._approval_event.clear()
        self._approved_script = None

        self._thread = threading.Thread(
            target=self._run_pipeline,
            args=(config_overrides,),
            daemon=True,
        )
        self._thread.start()

    def approve_script(self, edited_script: Optional[str] = None):
        """Approve the pending script (optionally with edits) and resume the pipeline."""
        if self.state != JobState.AWAITING_APPROVAL:
            raise RuntimeError(f"No script pending approval (state={self.state})")

        if edited_script and edited_script.strip():
            self._approved_script = edited_script.strip()
        else:
            self._approved_script = self.script

        self._approval_event.set()

    def reject_script(self):
        """Reject the script and regenerate it."""
        if self.state != JobState.AWAITING_APPROVAL:
            raise RuntimeError(f"No script pending rejection (state={self.state})")

        self._approved_script = None  # Signal to regenerate
        self._approval_event.set()

    def get_status(self) -> Dict:
        """Return current job status as a dict."""
        with self._lock:
            status = {
                "state": self.state.value,
                "progress": self.progress,
                "message": self.message,
                "error": self.error,
            }
            if self.repo_data:
                status["repo"] = {
                    "full_name": self.repo_data.get("full_name", ""),
                    "description": self.repo_data.get("description", ""),
                    "stars": self.repo_data.get("stars", 0),
                    "language": self.repo_data.get("language", ""),
                    "url": self.repo_data.get("url", ""),
                }
            if self.script:
                status["script"] = self.script
            if self.segments:
                status["segments"] = self.segments
            if self.result_filename:
                status["result_filename"] = self.result_filename
            if self.result_video_id:
                status["result_video_id"] = self.result_video_id
            return status

    def _run_pipeline(self, config_overrides: Optional[Dict] = None):
        """Execute the full video creation pipeline with pause points."""
        try:
            self._do_pipeline(config_overrides)
        except Exception as e:
            self.error = f"{type(e).__name__}: {str(e)}"
            self._notify(JobState.ERROR, self.progress, f"Error: {self.error}")
            traceback.print_exc()

    def _do_pipeline(self, config_overrides: Optional[Dict] = None):
        """Internal pipeline execution."""
        from utils import settings
        from utils.console import print_step

        config = settings.config

        # Apply any config overrides from the UI
        if config_overrides:
            for section, values in config_overrides.items():
                if section in config:
                    if isinstance(values, dict):
                        config[section].update(values)
                    else:
                        config[section] = values

        # Force storymode for GitHub content (always uses script segments)
        if "settings" not in config:
            config["settings"] = {}
        if "storymode" not in config["settings"]:
            config["settings"]["storymode"] = True
        if "storymodemethod" not in config["settings"]:
            config["settings"]["storymodemethod"] = 1
        
        # Ensure it's explicitly set to 1 for this run
        config["settings"]["storymodemethod"] = 1
        config["settings"]["storymode"] = True

        # ── Step 1: Fetch trending repos ──
        self._notify(JobState.FETCHING, 5, "Fetching trending repositories from GitHub...")

        from github.trending import (
            fetch_trending_repos,
            get_repo_details,
            get_undone_repo,
            sanitize_repo_id,
        )

        github_config = config.get("github", {})
        language = github_config.get("trending_language", "")
        since = github_config.get("trending_since", "daily")
        min_stars = github_config.get("min_stars", 100)
        token = github_config.get("api", {}).get("token", "")

        repos = fetch_trending_repos(language=language, since=since, min_stars=min_stars)
        self.trending_repos = repos

        if not repos:
            self._notify(JobState.ERROR, 5, "No trending repos found. Try adjusting filters.")
            self.error = "No trending repos found"
            return

        self._notify(JobState.FETCHING, 10, f"Found {len(repos)} trending repos. Selecting one...")

        # ── Step 2: Find an undone repo ──
        done_ids = self._load_done_ids()
        repo = get_undone_repo(repos, done_ids)

        if repo is None:
            self._notify(JobState.ERROR, 10, "All trending repos already processed!")
            self.error = "All trending repos already processed"
            return

        self._notify(JobState.FETCHING, 15, f"Selected: {repo['full_name']} ⭐ {repo.get('stars', 0):,}")

        # ── Step 3: Get full repo details ──
        repo_data = get_repo_details(repo["full_name"], token=token)
        self.repo_data = repo_data

        self._notify(JobState.FETCHING, 20, "Generating narration script...")

        # ── Step 4: Generate script ──
        from github.script_generator import generate_script, split_script_into_segments

        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            script = generate_script(repo_data, config)
            segments = split_script_into_segments(script)

            self.script = script
            self.segments = segments

            self._notify(
                JobState.AWAITING_APPROVAL,
                25,
                f"Script generated ({len(script.split())} words, {len(segments)} segments). Awaiting your approval...",
            )

            # ── PAUSE: Wait for user approval ──
            self._approval_event.wait()
            self._approval_event.clear()

            if self._approved_script is None:
                # User rejected — regenerate
                self._notify(JobState.FETCHING, 20, f"Regenerating script (attempt {attempt + 1})...")
                continue
            else:
                # User approved (possibly with edits)
                script = self._approved_script
                segments = split_script_into_segments(script)
                self.script = script
                self.segments = segments
                break
        else:
            # Exhausted regeneration attempts, use last script
            pass

        self._notify(JobState.GENERATING_TTS, 30, "Converting script to speech...")

        # ── Step 5: Build content object ──
        content_id = sanitize_repo_id(repo_data["full_name"])
        self.result_video_id = content_id

        content_obj = {
            "thread_id": content_id,
            "thread_title": (
                f"{repo_data['full_name']} — {repo_data['description'][:100]}"
                if repo_data["description"]
                else repo_data["full_name"]
            ),
            "thread_post": segments,
            "is_nsfw": False,
        }

        # ── Step 6: Generate TTS audio ──
        from video_creation.voices import save_text_to_mp3

        length, number_of_segments = save_text_to_mp3(content_obj)
        length = math.ceil(length)

        self._notify(JobState.SCREENSHOTS, 50, f"Taking screenshots of {repo_data['full_name']}...")

        # ── Step 7: Take screenshots ──
        from video_creation.screenshot_downloader import get_screenshots_of_github_repo

        get_screenshots_of_github_repo(repo_data, number_of_segments, length)

        self._notify(JobState.BACKGROUND, 65, "Preparing background audio & video...")

        # ── Step 8: Prepare background ──
        from video_creation.background import (
            chop_background,
            download_background,
            download_background_audio,
            get_background_config,
        )

        bg_config = {
            "audio": get_background_config("audio"),
            "video": get_background_config("video"),
        }
        download_background(bg_config["video"])
        download_background_audio(bg_config["audio"])
        chop_background(bg_config, length, content_obj)

        self._notify(JobState.RENDERING, 75, "Rendering final video... This may take a few minutes.")

        # ── Step 9: Render final video ──
        from video_creation.final_video import make_final_video

        make_final_video(number_of_segments, length, content_obj, bg_config)

        # ── Step 10: Find the output file ──
        results_dir = Path("results/github")
        if results_dir.exists():
            # Find the most recently created file
            files = sorted(results_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                self.result_filename = files[0].name

        self._notify(JobState.COMPLETE, 100, "Video created successfully! 🎉")

    @staticmethod
    def _load_done_ids() -> list:
        """Load the list of already-processed repo IDs from videos.json."""
        videos_json_path = Path("video_creation/data/videos.json")
        if not videos_json_path.exists():
            return []
        try:
            with open(videos_json_path, "r", encoding="utf-8") as f:
                done_videos = json.load(f)
            return [video["id"] for video in done_videos]
        except (json.JSONDecodeError, KeyError):
            return []


# ── Singleton job instance ──
current_job = VideoCreationJob()
