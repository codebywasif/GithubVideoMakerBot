import json
import random
import re
from pathlib import Path
from random import randrange
from typing import Dict, Tuple

import yt_dlp
from moviepy import AudioFileClip, VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip

from utils import settings
from utils.console import print_step, print_substep


def load_background_options():
    _background_options = {}

    # Load background audios
    with open("./utils/background_audios.json") as json_file:
        _background_options["audio"] = json.load(json_file)
    del _background_options["audio"]["__comment"]

    # Load background videos
    with open("./utils/background_videos.json") as json_file:
        _background_options["video"] = json.load(json_file)
    del _background_options["video"]["__comment"]

    return _background_options


def get_start_and_end_times(video_length: int, length_of_clip: int) -> Tuple[int, int]:
    """Generates a random interval of time to be used as the background audio."""
    initialValue = 180
    # Ensures that will be a valid interval in the video
    while int(length_of_clip) <= int(video_length + initialValue):
        if initialValue == initialValue // 2:
            return 0, video_length
        else:
            initialValue //= 2
    random_time = randrange(initialValue, int(length_of_clip) - int(video_length))
    return random_time, random_time + video_length


def get_background_config(mode: str):
    """Fetch the background/s configuration"""
    try:
        choice = str(
            settings.config["settings"]["background"][f"background_{mode}"]
        ).casefold()
    except AttributeError:
        print_substep(f"No background {mode} selected. Picking random background'")
        choice = None

    # Support custom uploaded backgrounds
    if choice and mode == "video" and choice.startswith("custom/"):
        filename = choice.split("/", 1)[1]
        if Path(f"assets/backgrounds/custom/{filename}").exists():
            return ("", filename, "Custom Upload", "center")

    # Handle default / not supported background using default option.
    if not choice or choice not in background_options[mode]:
        choice = random.choice(list(background_options[mode].keys()))

    return background_options[mode][choice]


def download_background_audio(background_config: Tuple[str, str, str]):
    """Downloads the background/s audio from YouTube."""
    Path("./assets/backgrounds/audio/").mkdir(parents=True, exist_ok=True)
    uri, filename, credit = background_config
    if Path(f"assets/backgrounds/audio/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds audio. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds audio... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "outtmpl": f"./assets/backgrounds/audio/{credit}-{filename}",
        "format": "bestaudio/best",
        "extract_audio": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([uri])

    print_substep("Background audio downloaded successfully! 🎉", style="bold green")


def download_background(background_config: Tuple[str, str, str, str]):
    """Downloads the background/s video from YouTube."""
    Path("./assets/backgrounds/").mkdir(parents=True, exist_ok=True)
    uri, filename, credit, _ = background_config
    
    # Custom background logic
    if credit == "Custom Upload":
        return

    if Path(f"assets/backgrounds/{credit}-{filename}").is_file():
        return
    print_step(
        "We need to download the backgrounds video. they are fairly large but it's only done once. 😎"
    )
    print_substep("Downloading the backgrounds video... please be patient 🙏 ")
    print_substep(f"Downloading {filename} from {uri}")
    ydl_opts = {
        "outtmpl": f"./assets/backgrounds/{credit}-{filename}",
        "merge_output_format": "mp4",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([uri])

    print_substep("Background video downloaded successfully! 🎉", style="bold green")


def chop_background(
    background_config: Dict[str, Tuple],
    video_length: int,
    content_object: dict,
):
    """Generates the background audio and footage to be used in the video."""
    thread_id = re.sub(r"[^\w\s-]", "", content_object["thread_id"])

    # 1. Chop Audio
    if settings.config["settings"]["background"]["background_audio_volume"] == 0:
        print_step("Volume was set to 0. Skipping background audio creation . . .")
    else:
        print_step("Finding a spot in the backgrounds audio to chop...✂️")
        audio_choice = (
            f"{background_config['audio'][2]}-{background_config['audio'][1]}"
        )
        background_audio = AudioFileClip(f"assets/backgrounds/audio/{audio_choice}")
        start_time_audio, end_time_audio = get_start_and_end_times(
            video_length, background_audio.duration
        )
        background_audio = background_audio.subclipped(start_time_audio, end_time_audio)
        background_audio.write_audiofile(f"assets/temp/{thread_id}/background.mp3")

    # 2. Chop Video
    print_step("Finding a spot in the backgrounds video to chop...✂️")
    video_config = background_config["video"]
    
    if video_config[2] == "Custom Upload":
        video_choice = f"custom/{video_config[1]}"
    else:
        video_choice = f"{video_config[2]}-{video_config[1]}"
        
    input_video_path = f"assets/backgrounds/{video_choice}"
    output_video_path = f"assets/temp/{thread_id}/background.mp4"
    
    # Check if the custom background is an image
    suffix = Path(input_video_path).suffix.lower()
    if suffix in [".png", ".jpg", ".jpeg"]:
        import subprocess
        # Convert image to a looping video of the right length
        print_substep("Converting custom background image to video...")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", input_video_path, "-t", str(video_length), "-c:v", "libx264", "-pix_fmt", "yuv420p", output_video_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return video_config[2]

    try:
        with VideoFileClip(input_video_path) as video:
            start_time, end_time = get_start_and_end_times(video_length, video.duration)
            ffmpeg_extract_subclip(
                input_video_path,
                start_time,
                end_time,
                outputfile=output_video_path,
            )
        print_substep("Background video chopped successfully!", style="bold green")
    except Exception as e:
        print_substep(f"Error chopping background video: {e}", style="red")

    return video_config[2]

# Create a tuple for downloads background
background_options = load_background_options()
