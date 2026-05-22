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

    # Remove "__comment" from backgrounds
    del _background_options["audio"]["__comment"]

    return _background_options


def get_start_and_end_times(video_length: int, length_of_clip: int) -> Tuple[int, int]:
    """Generates a random interval of time to be used as the background audio."""
    initialValue = 180
    # Ensures that will be a valid interval in the video
    while int(length_of_clip) <= int(video_length + initialValue):
        if initialValue == initialValue // 2:
            raise Exception("Your background audio is too short for this video length")
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


def chop_background(
    background_config: Dict[str, Tuple],
    video_length: int,
    content_object: dict,
):
    """Generates the background audio and footage to be used in the video.

    Args:
        content_object: Content object with thread_id.
        background_config: Current background configuration.
        video_length: Length of the clip where the background footage is to be taken out of.
    """
    thread_id = re.sub(r"[^\w\s-]", "", content_object["thread_id"])

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

    print_step("Processing scrolling repository background video...✂️")
    # Playwright generates a webm. We convert it to mp4 (and ensure it's not too long).
    input_video = f"assets/temp/{thread_id}/repo_scroll.webm"
    output_video = f"assets/temp/{thread_id}/background.mp4"
    
    if Path(input_video).exists():
        import subprocess
        fixed_video = f"assets/temp/{thread_id}/fixed_scroll.mp4"
        print_substep("Fixing webm duration and converting to mp4...")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_video, "-c:v", "libx264", "-preset", "ultrafast", fixed_video],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            with VideoFileClip(fixed_video) as video:
                # The video has loading/static screen at the start. The scrolling happens at the end.
                # We want the last `video_length` seconds to skip the blank white screen.
                start_t = max(0, video.duration - video_length)
                new = video.subclipped(start_t, video.duration)
                new.write_videofile(output_video, codec="libx264")
        except Exception as e:
            print_substep(f"FFMPEG issue: {e}. Trying again...", style="red")
            ffmpeg_extract_subclip(
                fixed_video,
                0,
                video_length,
                outputfile=output_video,
            )
        print_substep("Background video chopped successfully!", style="bold green")
    else:
        print_substep("Could not find repo_scroll.webm, background video processing failed.", style="red")

    return "GitHub Scroll"


# Create a tuple for downloads background
background_options = load_background_options()
