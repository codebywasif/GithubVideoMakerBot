import json
import time

from utils.console import print_step


def save_data(source: str, filename: str, title: str, id: str, background_credit: str):
    """Saves the videos that have already been generated to a JSON file.

    Args:
        source (str): Source of the video (e.g. "github")
        filename (str): The finished video filename
        title (str): The title of the repository/video
        id (str): The sanitized ID of the repository
        background_credit (str): Background video credit
    """
    filepath = "./video_creation/data/videos.json"
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            done_vids = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        done_vids = []

    if id in [video.get("id") for video in done_vids]:
        return

    payload = {
        "source": source,
        "id": id,
        "time": str(int(time.time())),
        "background_credit": background_credit,
        "video_title": title,
        "filename": filename,
    }
    
    done_vids.append(payload)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(done_vids, f, ensure_ascii=False, indent=4)
