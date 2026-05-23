import multiprocessing
import os
import re
import tempfile
import textwrap
import threading
import time
from os.path import exists
from pathlib import Path
from typing import Dict, Final, Tuple

import ffmpeg
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track

from utils import settings
from utils.cleanup import cleanup
from utils.console import print_step, print_substep
from utils.fonts import getheight
from utils.id import extract_id
from utils.thumbnail import create_thumbnail
from utils.videos import save_data

console = Console()


class ProgressFfmpeg(threading.Thread):
    def __init__(self, vid_duration_seconds, progress_update_callback):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        while not self.stop_event.is_set():
            latest_progress = self.get_latest_ms_progress()
            if latest_progress is not None:
                completed_percent = latest_progress / self.vid_duration_seconds
                self.progress_update_callback(completed_percent)
            time.sleep(1)

    def get_latest_ms_progress(self):
        lines = self.output_file.readlines()

        if lines:
            for line in lines:
                if "out_time_ms" in line:
                    out_time_ms_str = line.split("=")[1].strip()
                    if out_time_ms_str.isnumeric():
                        return float(out_time_ms_str) / 1000000.0
                    else:
                        return None
        return None

    def stop(self):
        self.stop_event.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()


def name_normalize(name: str) -> str:
    """Normalize a name for use as a filename."""
    name = re.sub(r'[?\\\\"%*:|<>]', "", name)
    name = re.sub(r"( [w,W]\s?\/\s?[o,O,0])", r" without", name)
    name = re.sub(r"( [w,W]\s?\/)", r" with", name)
    name = re.sub(r"(\d+)\s?\/\s?(\d+)", r"\1 of \2", name)
    name = re.sub(r"(\w+)\s?\/\s?(\w+)", r"\1 or \2", name)
    name = re.sub(r"\/", r"", name)
    return name


def prepare_background(content_id: str, W: int, H: int) -> str:
    output_path = f"assets/temp/{content_id}/background_noaudio.mp4"
    output = (
        ffmpeg.input(f"assets/temp/{content_id}/background.mp4")
        # Center crop: scale to cover, then crop the center.
        .filter("scale", f"max({W},iw*({H}/ih))", f"max({H},ih*({W}/iw))")
        .filter("crop", W, H)
        .output(
            output_path,
            an=None,
            **{
                "c:v": "h264_nvenc",
                "b:v": "20M",
                "b:a": "192k",
                "threads": multiprocessing.cpu_count(),
            },
        )
        .overwrite_output()
    )
    try:
        output.run(quiet=True)
    except ffmpeg.Error as e:
        print(e.stderr.decode("utf8"))
        exit(1)
    return output_path


def get_text_height(draw, text, font, max_width):
    lines = textwrap.wrap(text, width=max_width)
    total_height = 0
    for line in lines:
        _, _, _, height = draw.textbbox((0, 0), line, font=font)
        total_height += height
    return total_height


def create_fancy_thumbnail(image, text, text_color, padding, wrap=35):
    """
    Create a fancy title card for the video.
    Stretches the middle of the template to accommodate the title text.
    """
    print_step(f"Creating title card for: {text}")
    font_title_size = 47
    font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
    image_width, image_height = image.size

    # Calculate text height to determine new image height
    draw = ImageDraw.Draw(image)
    text_height = get_text_height(draw, text, font, wrap)
    lines = textwrap.wrap(text, width=wrap)
    new_image_height = image_height + text_height + padding * (len(lines) - 1) - 50

    # Separate the image into top, middle (1px), and bottom parts
    top_part_height = image_height // 2
    middle_part_height = 1
    bottom_part_height = image_height - top_part_height - middle_part_height

    top_part = image.crop((0, 0, image_width, top_part_height))
    middle_part = image.crop(
        (0, top_part_height, image_width, top_part_height + middle_part_height)
    )
    bottom_part = image.crop(
        (0, top_part_height + middle_part_height, image_width, image_height)
    )

    # Stretch the middle part
    new_middle_height = new_image_height - top_part_height - bottom_part_height
    middle_part = middle_part.resize((image_width, new_middle_height))

    # Create new image with the calculated height
    new_image = Image.new("RGBA", (image_width, new_image_height))

    # Paste the top, stretched middle, and bottom parts
    new_image.paste(top_part, (0, 0))
    new_image.paste(middle_part, (0, top_part_height))
    new_image.paste(bottom_part, (0, top_part_height + new_middle_height))

    # Draw the title text on the new image
    draw = ImageDraw.Draw(new_image)
    y = top_part_height + padding
    for line in lines:
        draw.text((120, y), line, font=font, fill=text_color, align="left")
        y += get_text_height(draw, line, font, wrap) + padding

    # Draw the channel name at the specific position
    username_font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), 30)
    draw.text(
        (205, 825),
        settings.config["settings"]["channel_name"],
        font=username_font,
        fill=text_color,
        align="left",
    )

    return new_image


def merge_background_audio(audio: ffmpeg, content_id: str):
    """Merge TTS audio with background audio.

    Args:
        audio: The TTS final audio.
        content_id: The content ID for temp file paths.
    """
    background_audio_volume = settings.config["settings"]["background"][
        "background_audio_volume"
    ]
    if background_audio_volume == 0:
        return audio
    else:
        bg_audio = ffmpeg.input(f"assets/temp/{content_id}/background.mp3").filter(
            "volume",
            background_audio_volume,
        )
        merged_audio = ffmpeg.filter([audio, bg_audio], "amix", duration="longest")
        return merged_audio


def make_final_video(
    number_of_clips: int,
    length: int,
    content_obj: dict,
    background_config: Dict[str, Tuple],
):
    """Gathers audio clips, screenshots, stitches them together and saves the final video.

    Args:
        number_of_clips: Number of script segments.
        length: Length of the video in seconds.
        content_obj: The content object with thread_id, thread_title, etc.
        background_config: The background config to use.
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])

    opacity = settings.config["settings"]["opacity"]

    content_id = extract_id(content_obj)

    allowOnlyTTSFolder: bool = (
        settings.config["settings"]["background"]["enable_extra_audio"]
        and settings.config["settings"]["background"]["background_audio_volume"] != 0
    )

    print_step("Creating the final video 🎥")

    background_clip = ffmpeg.input(prepare_background(content_id, W=W, H=H))

    # Gather all audio clips and durations
    audio_clips = list()
    audio_clips_durations = list()
    
    if settings.config["settings"]["storymode"]:
        if settings.config["settings"]["storymodemethod"] == 0:
            audio_clips = [ffmpeg.input(f"assets/temp/{content_id}/mp3/title.mp3")]
            audio_clips.insert(
                1, ffmpeg.input(f"assets/temp/{content_id}/mp3/postaudio.mp3")
            )
            audio_clips_durations = [
                float(ffmpeg.probe(f"assets/temp/{content_id}/mp3/title.mp3")["format"]["duration"]),
                float(ffmpeg.probe(f"assets/temp/{content_id}/mp3/postaudio.mp3")["format"]["duration"])
            ]
        elif settings.config["settings"]["storymodemethod"] == 1:
            audio_clips = [
                ffmpeg.input(f"assets/temp/{content_id}/mp3/postaudio-{i}.mp3")
                for i in track(
                    range(number_of_clips + 1), "Collecting the audio files..."
                )
            ]
            audio_clips.insert(
                0, ffmpeg.input(f"assets/temp/{content_id}/mp3/title.mp3")
            )
            audio_clips_durations = [
                float(ffmpeg.probe(f"assets/temp/{content_id}/mp3/postaudio-{i}.mp3")["format"]["duration"])
                for i in range(number_of_clips + 1)
            ]
            audio_clips_durations.insert(
                0, float(ffmpeg.probe(f"assets/temp/{content_id}/mp3/title.mp3")["format"]["duration"])
            )
    else:
        audio_clips = [
            ffmpeg.input(f"assets/temp/{content_id}/mp3/{i}.mp3")
            for i in range(number_of_clips)
        ]
        audio_clips.insert(
            0, ffmpeg.input(f"assets/temp/{content_id}/mp3/title.mp3")
        )

        audio_clips_durations = [
            float(
                ffmpeg.probe(f"assets/temp/{content_id}/mp3/{i}.mp3")["format"][
                    "duration"
                ]
            )
            for i in range(number_of_clips)
        ]
        audio_clips_durations.insert(
            0,
            float(
                ffmpeg.probe(f"assets/temp/{content_id}/mp3/title.mp3")["format"][
                    "duration"
                ]
            ),
        )

    audio_concat = ffmpeg.concat(*audio_clips, a=1, v=0)
    ffmpeg.output(
        audio_concat, f"assets/temp/{content_id}/audio.mp3", **{"b:a": "192k"}
    ).overwrite_output().run(quiet=True)

    console.log(f"[bold green] Video Will Be: {length} Seconds Long")

    screenshot_width = int((W * 90) // 100)
    audio = ffmpeg.input(f"assets/temp/{content_id}/audio.mp3")
    final_audio = merge_background_audio(audio, content_id)

    print_step("Overlaying screenshots over background.")
    
    # Overlay the images
    current_time = 0.0
    
    # Title image
    title_path = f"assets/temp/{content_id}/png/title.png"
    if exists(title_path):
        img_clip = ffmpeg.input(title_path)
        img_clip = img_clip.filter("scale", screenshot_width, -1)
        background_clip = ffmpeg.overlay(
            background_clip, 
            img_clip, 
            x="(W-w)/2", y="(H-h)/2", 
            enable=f"between(t,{current_time},{current_time + audio_clips_durations[0]})"
        )
    current_time += audio_clips_durations[0]

    # Segment images
    for i in range(number_of_clips + 1 if settings.config["settings"]["storymodemethod"] == 1 else number_of_clips):
        img_path = f"assets/temp/{content_id}/png/img{i}.png"
        if exists(img_path):
            img_clip = ffmpeg.input(img_path)
            img_clip = img_clip.filter("scale", screenshot_width, -1)
            duration = audio_clips_durations[i + 1]
            background_clip = ffmpeg.overlay(
                background_clip, 
                img_clip, 
                x="(W-w)/2", y="(H-h)/2", 
                enable=f"between(t,{current_time},{current_time + duration})"
            )
            current_time += duration

    title = extract_id(content_obj, "thread_title")
    idx = extract_id(content_obj)
    title_thumb = content_obj["thread_title"]

    filename = f"{name_normalize(title)[:251]}"

    if not exists(f"./results/github"):
        print_substep(
            "The 'results/github' folder could not be found so it was automatically created."
        )
        os.makedirs(f"./results/github")

    if not exists(f"./results/github/OnlyTTS") and allowOnlyTTSFolder:
        print_substep(
            "The 'OnlyTTS' folder could not be found so it was automatically created."
        )
        os.makedirs(f"./results/github/OnlyTTS")

    # Create a thumbnail for the video
    settingsbackground = settings.config["settings"]["background"]

    if settingsbackground["background_thumbnail"]:
        if not exists(f"./results/github/thumbnails"):
            print_substep(
                "The 'results/thumbnails' folder could not be found so it was automatically created."
            )
            os.makedirs(f"./results/github/thumbnails")
        first_image = next(
            (
                file
                for file in os.listdir("assets/backgrounds")
                if file.endswith(".png")
            ),
            None,
        )
        if first_image is None:
            print_substep("No png files found in assets/backgrounds", "red")
        else:
            font_family = settingsbackground["background_thumbnail_font_family"]
            font_size = settingsbackground["background_thumbnail_font_size"]
            font_color = settingsbackground["background_thumbnail_font_color"]
            thumbnail = Image.open(f"assets/backgrounds/{first_image}")
            width, height = thumbnail.size
            thumbnailSave = create_thumbnail(
                thumbnail,
                font_family,
                font_size,
                font_color,
                width,
                height,
                title_thumb,
            )
            thumbnailSave.save(f"./assets/temp/{content_id}/thumbnail.png")
            print_substep(
                f"Thumbnail built in assets/temp/{content_id}/thumbnail.png"
            )

    text = f"Background by {background_config['video'][2]}"
    background_clip = ffmpeg.drawtext(
        background_clip,
        text=text,
        x=f"(w-text_w)",
        y=f"(h-text_h)",
        fontsize=5,
        fontcolor="White",
        fontfile=os.path.join("fonts", "Roboto-Regular.ttf"),
    )
    background_clip = background_clip.filter("scale", W, H)
    print_step("Rendering the video 🎥")
    from tqdm import tqdm

    pbar = tqdm(total=100, desc="Progress: ", bar_format="{l_bar}{bar}", unit=" %")

    def on_update_example(progress) -> None:
        status = round(progress * 100, 2)
        old_percentage = pbar.n
        pbar.update(status - old_percentage)

    defaultPath = f"results/github"
    with ProgressFfmpeg(length, on_update_example) as progress:
        path = defaultPath + f"/{filename}"
        path = path[:251] + ".mp4"
        try:
            ffmpeg.output(
                background_clip,
                final_audio,
                path,
                f="mp4",
                **{
                    "c:v": "h264_nvenc",
                    "b:v": "20M",
                    "b:a": "192k",
                    "threads": multiprocessing.cpu_count(),
                },
            ).overwrite_output().global_args(
                "-progress", progress.output_file.name
            ).run(
                quiet=True,
                overwrite_output=True,
                capture_stdout=False,
                capture_stderr=False,
            )
        except ffmpeg.Error as e:
            print(e.stderr.decode("utf8"))
            exit(1)
    old_percentage = pbar.n
    pbar.update(100 - old_percentage)
    if allowOnlyTTSFolder:
        path = defaultPath + f"/OnlyTTS/{filename}"
        path = path[:251] + ".mp4"
        print_step("Rendering the Only TTS Video 🎥")
        with ProgressFfmpeg(length, on_update_example) as progress:
            try:
                ffmpeg.output(
                    background_clip,
                    audio,
                    path,
                    f="mp4",
                    **{
                        "c:v": "h264_nvenc",
                        "b:v": "20M",
                        "b:a": "192k",
                        "threads": multiprocessing.cpu_count(),
                    },
                ).overwrite_output().global_args(
                    "-progress", progress.output_file.name
                ).run(
                    quiet=True,
                    overwrite_output=True,
                    capture_stdout=False,
                    capture_stderr=False,
                )
            except ffmpeg.Error as e:
                print(e.stderr.decode("utf8"))
                exit(1)

        old_percentage = pbar.n
        pbar.update(100 - old_percentage)
    pbar.close()
    save_data("github", filename + ".mp4", title, idx, background_config["video"][2])
    print_step("Removing temporary files 🗑")
    cleanups = cleanup(content_id)
    print_substep(f"Removed {cleanups} temporary files 🗑")
    print_step("Done! 🎉 The video is in the results/github folder 📁")
