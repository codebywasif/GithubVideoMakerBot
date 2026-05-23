"""
GUI.py — Flask REST API + SPA server for the GitHub Video Maker Bot.

Serves the single-page application and provides REST API endpoints
for video creation, script approval, settings management, background
management, and video history.
"""

import sys

# Fix Windows console encoding — the pipeline uses emoji characters (✅, ⭐, etc.)
# that cp1252 can't handle. Force UTF-8 with error replacement.
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import os
import re
import time
import webbrowser
from pathlib import Path
from queue import Queue, Empty

import tomlkit
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    request,
    send_file,
    send_from_directory,
)
from werkzeug.utils import secure_filename

from api_runner import current_job, JobState

# ── Configuration ──
HOST = "localhost"
PORT = 4000

RESULTS_DIR = Path("results/github")
VIDEOS_JSON = Path("video_creation/data/videos.json")
BACKGROUNDS_DIR = Path("assets/backgrounds")
CUSTOM_BG_DIR = Path("assets/backgrounds/custom")
BG_VIDEOS_JSON = Path("utils/background_videos.json")
BG_AUDIOS_JSON = Path("utils/background_audios.json")
CONFIG_FILE = Path("config.toml")

# ── Flask App ──
app = Flask(
    __name__,
    static_folder="GUI/static",
    static_url_path="/static",
)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB upload limit


# ── No caching ──
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = "0"
    response.headers["Pragma"] = "no-cache"
    return response


# ═══════════════════════════════════════════════════════
#   SPA Routes
# ═══════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the single-page application."""
    return send_file("GUI/index.html")


# ═══════════════════════════════════════════════════════
#   Status API
# ═══════════════════════════════════════════════════════

@app.route("/api/status")
def api_status():
    """Get current pipeline status."""
    return jsonify(current_job.get_status())


# ═══════════════════════════════════════════════════════
#   Video Creation API
# ═══════════════════════════════════════════════════════

@app.route("/api/create", methods=["POST"])
def api_create():
    """Start a new video creation run."""
    try:
        overrides = request.get_json(silent=True) or {}
        current_job.start(config_overrides=overrides)
        return jsonify({"ok": True, "message": "Video creation started"})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409


@app.route("/api/script/pending")
def api_script_pending():
    """Get the pending script awaiting approval."""
    status = current_job.get_status()
    if status["state"] != JobState.AWAITING_APPROVAL.value:
        return jsonify({"pending": False, "state": status["state"]})

    return jsonify({
        "pending": True,
        "script": status.get("script", ""),
        "segments": status.get("segments", []),
        "repo": status.get("repo", {}),
    })


@app.route("/api/script/approve", methods=["POST"])
def api_script_approve():
    """Approve or edit the pending script."""
    try:
        data = request.get_json(silent=True) or {}
        edited_script = data.get("script")
        current_job.approve_script(edited_script)
        return jsonify({"ok": True, "message": "Script approved"})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409


@app.route("/api/script/reject", methods=["POST"])
def api_script_reject():
    """Reject the script and regenerate."""
    try:
        current_job.reject_script()
        return jsonify({"ok": True, "message": "Script rejected, regenerating..."})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409


# ═══════════════════════════════════════════════════════
#   SSE Progress Stream
# ═══════════════════════════════════════════════════════

@app.route("/api/progress")
def api_progress():
    """Server-Sent Events stream for real-time progress updates."""

    def generate():
        q = Queue()

        def on_progress(state, progress, message):
            q.put({"state": state.value, "progress": progress, "message": message})

        current_job.subscribe(on_progress)

        try:
            # Send current state immediately
            status = current_job.get_status()
            yield f"data: {json.dumps(status)}\n\n"

            while True:
                try:
                    update = q.get(timeout=30)
                    yield f"data: {json.dumps(update)}\n\n"

                    # End stream when job is complete or errored
                    if update["state"] in (JobState.COMPLETE.value, JobState.ERROR.value):
                        # Send final full status
                        yield f"data: {json.dumps(current_job.get_status())}\n\n"
                        break
                except Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"
        finally:
            current_job.unsubscribe(on_progress)

    return Response(generate(), mimetype="text/event-stream")


# ═══════════════════════════════════════════════════════
#   Video Library API
# ═══════════════════════════════════════════════════════

@app.route("/api/videos")
def api_videos():
    """List all generated videos."""
    if not VIDEOS_JSON.exists():
        return jsonify([])

    try:
        with open(VIDEOS_JSON, "r", encoding="utf-8") as f:
            videos = json.load(f)
    except (json.JSONDecodeError, IOError):
        return jsonify([])

    # Enrich with file size and existence check
    for video in videos:
        filepath = RESULTS_DIR / video.get("filename", "")
        video["exists"] = filepath.exists()
        video["file_size"] = filepath.stat().st_size if filepath.exists() else 0
        video["file_size_mb"] = round(video["file_size"] / (1024 * 1024), 1)

    # Sort by time, newest first
    videos.sort(key=lambda v: int(v.get("time", "0")), reverse=True)
    return jsonify(videos)


@app.route("/api/videos/<path:filename>")
def api_video_download(filename):
    """Download a specific video file."""
    safe_name = secure_filename(filename)
    filepath = RESULTS_DIR / safe_name
    if not filepath.exists():
        # Try the original filename (may contain spaces)
        filepath = RESULTS_DIR / filename
        if not filepath.exists():
            abort(404)
    return send_file(filepath, as_attachment=True)


@app.route("/api/videos/<video_id>", methods=["DELETE"])
def api_video_delete(video_id):
    """Delete a video from history and disk."""
    if not VIDEOS_JSON.exists():
        abort(404)

    with open(VIDEOS_JSON, "r", encoding="utf-8") as f:
        videos = json.load(f)

    # Find and remove the video
    removed = None
    new_videos = []
    for v in videos:
        if v.get("id") == video_id:
            removed = v
        else:
            new_videos.append(v)

    if not removed:
        abort(404)

    # Delete from JSON
    with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
        json.dump(new_videos, f, ensure_ascii=False, indent=4)

    # Delete file from disk
    filepath = RESULTS_DIR / removed.get("filename", "")
    if filepath.exists():
        filepath.unlink()

    return jsonify({"ok": True, "message": f"Deleted video {video_id}"})


@app.route("/api/videos/<video_id>/redo", methods=["POST"])
def api_video_redo(video_id):
    """Redo a video (re-create). Deletes the old one and starts fresh."""
    # For now, just delete and start a new creation
    # In a future version, we could pass the repo info to target that specific repo
    if VIDEOS_JSON.exists():
        with open(VIDEOS_JSON, "r", encoding="utf-8") as f:
            videos = json.load(f)

        new_videos = [v for v in videos if v.get("id") != video_id]
        with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
            json.dump(new_videos, f, ensure_ascii=False, indent=4)

        # Delete file
        for v in videos:
            if v.get("id") == video_id:
                filepath = RESULTS_DIR / v.get("filename", "")
                if filepath.exists():
                    filepath.unlink()
                break

    # Start a new creation
    try:
        current_job.start()
        return jsonify({"ok": True, "message": "Redo started"})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409


# ═══════════════════════════════════════════════════════
#   Trending API
# ═══════════════════════════════════════════════════════

@app.route("/api/trending")
def api_trending():
    """Fetch and return currently trending repos (preview only)."""
    try:
        from github.trending import fetch_trending_repos
        from utils import settings

        config = settings.config
        github_config = config.get("github", {})

        repos = fetch_trending_repos(
            language=github_config.get("trending_language", ""),
            since=github_config.get("trending_since", "daily"),
            min_stars=github_config.get("min_stars", 100),
        )
        return jsonify(repos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════
#   Settings API
# ═══════════════════════════════════════════════════════

# Keys to redact in API responses
SENSITIVE_KEYS = {"openai_api_key", "token", "elevenlabs_api_key", "tiktok_sessionid"}


def _redact_config(obj, reveal=False):
    """Deep-copy config and redact sensitive values."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in SENSITIVE_KEYS and not reveal and isinstance(v, str) and v:
                result[k] = "•" * min(len(v), 12)
            else:
                result[k] = _redact_config(v, reveal)
        return result
    elif isinstance(obj, list):
        return [_redact_config(item, reveal) for item in obj]
    return obj


def _flatten_config(obj, prefix="", result=None):
    """Flatten nested config dict into dotted keys."""
    if result is None:
        result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _flatten_config(v, new_key, result)
            else:
                result[new_key] = v
    return result


@app.route("/api/settings")
def api_settings():
    """Get current config (keys redacted unless ?reveal=true)."""
    reveal = request.args.get("reveal", "false").lower() == "true"
    try:
        config_data = tomlkit.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        redacted = _redact_config(dict(config_data), reveal=reveal)
        return jsonify(redacted)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["POST"])
def api_settings_update():
    """Update config.toml with new values."""
    try:
        updates = request.get_json()
        if not updates:
            return jsonify({"ok": False, "error": "No data provided"}), 400

        config_data = tomlkit.loads(CONFIG_FILE.read_text(encoding="utf-8"))

        def _deep_update(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    _deep_update(target[key], value)
                else:
                    # Skip masked values (don't overwrite keys with dots)
                    if isinstance(value, str) and re.match(r"^•+$", value):
                        continue
                    target[key] = value

        _deep_update(config_data, updates)

        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(config_data))

        # Reload settings in memory
        try:
            from utils import settings
            settings.config = dict(config_data)
        except Exception:
            pass

        return jsonify({"ok": True, "message": "Settings saved successfully"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════
#   Background Management API
# ═══════════════════════════════════════════════════════

@app.route("/api/backgrounds/videos")
def api_bg_videos():
    """List available background videos."""
    try:
        with open(BG_VIDEOS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("__comment", None)
        result = []
        for key, val in data.items():
            result.append({
                "key": key,
                "youtube_url": val[0] if len(val) > 0 else "",
                "filename": val[1] if len(val) > 1 else "",
                "credit": val[2] if len(val) > 2 else "",
                "position": val[3] if len(val) > 3 else "center",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/backgrounds/audios")
def api_bg_audios():
    """List available background audio tracks."""
    try:
        with open(BG_AUDIOS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("__comment", None)
        result = []
        for key, val in data.items():
            result.append({
                "key": key,
                "youtube_url": val[0] if len(val) > 0 else "",
                "filename": val[1] if len(val) > 1 else "",
                "credit": val[2] if len(val) > 2 else "",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/backgrounds/upload", methods=["POST"])
def api_bg_upload():
    """Upload a custom background image or video."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "No filename"}), 400

    # Validate extension
    allowed = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        return jsonify({"ok": False, "error": f"File type {ext} not allowed"}), 400

    # Save to custom backgrounds folder
    CUSTOM_BG_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file.filename)
    save_path = CUSTOM_BG_DIR / safe_name
    file.save(str(save_path))

    return jsonify({
        "ok": True,
        "message": f"Uploaded {safe_name}",
        "filename": safe_name,
        "path": str(save_path),
    })


@app.route("/api/backgrounds/<key>", methods=["DELETE"])
def api_bg_delete(key):
    """Remove a background video."""
    try:
        with open(BG_VIDEOS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)

        if key not in data:
            return jsonify({"ok": False, "error": "Background not found"}), 404

        del data[key]
        with open(BG_VIDEOS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return jsonify({"ok": True, "message": f"Deleted background '{key}'"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/backgrounds/custom")
def api_bg_custom_list():
    """List uploaded custom backgrounds."""
    CUSTOM_BG_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in CUSTOM_BG_DIR.iterdir():
        if f.is_file():
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "ext": f.suffix.lower(),
                "is_video": f.suffix.lower() in {".mp4", ".webm", ".avi", ".mov", ".mkv"},
                "is_image": f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"},
            })
    return jsonify(files)


# ═══════════════════════════════════════════════════════
#   Legacy compat: serve results files
# ═══════════════════════════════════════════════════════

@app.route("/results/<path:name>")
def results(name):
    return send_from_directory("results", name, as_attachment=True)


# ═══════════════════════════════════════════════════════
#   Run
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    # Ensure required directories exist
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_BG_DIR.mkdir(parents=True, exist_ok=True)
    Path("GUI/static/css").mkdir(parents=True, exist_ok=True)
    Path("GUI/static/js").mkdir(parents=True, exist_ok=True)

    # Load config.toml into settings so API endpoints can use it
    import toml
    from utils import settings as _settings
    try:
        _settings.config = toml.load(str(CONFIG_FILE))
        print(f"Config loaded from {CONFIG_FILE}")
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
        _settings.config = {}

    webbrowser.open(f"http://{HOST}:{PORT}", new=2)
    print(f">>> GitHub Video Maker Bot Dashboard running at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)

