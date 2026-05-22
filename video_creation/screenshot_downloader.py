import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Final

from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.imagenarator import imagemaker

__all__ = ["get_screenshots_of_github_repo"]


def get_screenshots_of_github_repo(repo_data: dict, screenshot_num: int, video_length: int):
    """Takes screenshots of a GitHub repository page for use in the video.

    Captures:
    1. Title screenshot — repo header (name, description, stars, language badge)
    2. Per-segment screenshots — README sections or repeated repo visuals
    3. Records a scrolling background video of the repository page.

    Args:
        repo_data: Enriched repo dict with full_name, url, etc.
        screenshot_num: Number of script segments (determines how many screenshots to take).
        video_length: Total length of the video in seconds for background recording.
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Taking screenshots and recording scrolling background...")

    repo_id = re.sub(r"[^\w\s-]", "", repo_data["full_name"].replace("/", "-"))
    repo_url = repo_data.get("url", f"https://github.com/{repo_data['full_name']}")

    # Ensure the screenshots folder exists
    Path(f"assets/temp/{repo_id}/png").mkdir(parents=True, exist_ok=True)

    # Determine theme
    if settings.config["settings"]["theme"] == "dark":
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
        color_scheme = "dark"
    else:
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False
        color_scheme = "light"

    # If storymode method 1, generate text images instead of screenshots
    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        # We still want the title screenshot from GitHub, but segment images are text-based
        _take_github_screenshots(repo_url, repo_id, W, H, color_scheme, screenshot_num, video_length)
        # Also generate text overlay images for each segment
        # (the imagemaker will be called from final_video.py or we handle it here)
        return

    _take_github_screenshots(repo_url, repo_id, W, H, color_scheme, screenshot_num, video_length)

    print_substep("Screenshots and background captured successfully.", style="bold green")


def _take_github_screenshots(
    repo_url: str,
    repo_id: str,
    W: int,
    H: int,
    color_scheme: str,
    num_segments: int,
    video_length: int,
):
    """Use Playwright to navigate to a GitHub repo, take screenshots, and record a scrolling video."""
    with sync_playwright() as p:
        print_substep("Launching headless browser...")

        browser = p.chromium.launch(headless=True)

        # Device scale factor for high-res screenshots
        dsf = (W // 600) + 1
        
        video_dir = f"assets/temp/{repo_id}/video"
        Path(video_dir).mkdir(parents=True, exist_ok=True)

        # Set viewport to something wide enough so it's not a mobile layout,
        # but keep it proportional if possible. We'll use 1280x900 for static images,
        # but for the recorded video, we want the video size to match WxH.
        # Playwright records the viewport. Let's make viewport match final video resolution, 
        # or just 1280x(something tall) and scale it later.
        record_width = 1280
        record_height = int(1280 * (H / W)) # Maintain aspect ratio

        context = browser.new_context(
            color_scheme=color_scheme,
            viewport=ViewportSize(width=record_width, height=record_height),
            device_scale_factor=dsf,
            user_agent=(
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{browser.version}.0.0.0 Safari/537.36"
            ),
            record_video_dir=video_dir,
            record_video_size={"width": record_width, "height": record_height}
        )

        page = context.new_page()

        # Navigate to the repository page
        print_substep(f"Navigating to {repo_url}...")
        try:
            page.goto(repo_url, timeout=30000, wait_until="networkidle")
        except Exception as e:
            print_substep(f"Navigation timeout, continuing anyway: {e}", style="yellow")

        page.wait_for_timeout(3000)  # Extra wait for dynamic content

        # --- Screenshot 1: Title / Repo Header ---
        _take_title_screenshot(page, repo_id, record_width, record_height)

        # --- Screenshot 2+: README / content sections ---
        _take_content_screenshots(page, repo_id, record_width, record_height, num_segments)

        # --- Record dynamic scroll for background ---
        print_substep(f"Recording scrolling background for {video_length} seconds...")
        
        fps = 30
        total_frames = int(video_length * fps)
        
        # Calculate scroll distance per frame
        # Let's try to scroll to the bottom over the course of the video.
        page_height = page.evaluate("document.body.scrollHeight")
        viewport_height = record_height
        max_scroll = max(0, page_height - viewport_height)
        
        if max_scroll > 0:
            scroll_per_frame = max_scroll / total_frames
        else:
            scroll_per_frame = 0

        # Scroll to top first
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)
        
        current_scroll = 0
        
        # Perform smooth scrolling loop
        # We'll just do a simpler time-based sleep loop. Playwright will naturally record it.
        start_time = time.time()
        while time.time() - start_time < video_length + 2:  # Add 2 seconds padding
            if scroll_per_frame > 0:
                current_scroll += scroll_per_frame * (fps / 10) # 10 ticks per second
                page.evaluate(f"window.scrollTo(0, {current_scroll})")
            page.wait_for_timeout(100)
            
            # If we hit the bottom, bounce back to top (infinite scroll loop)
            if current_scroll >= max_scroll:
                current_scroll = 0
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)

        # Get the path to the recorded video
        video_path = page.video.path()
        
        browser.close()

    # Move/Rename the recorded webm file to background.webm in the temp folder
    final_video_path = f"assets/temp/{repo_id}/repo_scroll.webm"
    if video_path and os.path.exists(video_path):
        import shutil
        shutil.move(video_path, final_video_path)
        print_substep(f"Saved scrolling background to {final_video_path}", style="bold green")
    else:
        print_substep("Failed to record scrolling background.", style="red")

    print_substep("All screenshots and background captured.", style="bold green")


def _take_title_screenshot(page, repo_id: str, W: int, H: int):
    """Take a screenshot of the repository header area."""
    title_path = f"assets/temp/{repo_id}/png/title.png"

    try:
        header_selectors = [
            '[data-testid="repository-title-area"]',
            ".AppHeader-context",
            "#repository-container-header",
            ".pagehead",
        ]

        header_element = None
        for selector in header_selectors:
            element = page.locator(selector).first
            if element.is_visible(timeout=2000):
                header_element = element
                break

        if header_element:
            header_element.screenshot(path=title_path)
        else:
            page.screenshot(
                path=title_path,
                clip={"x": 0, "y": 0, "width": 1280, "height": 400},
            )

        print_substep("Title screenshot captured.", style="green")
    except Exception as e:
        print_substep(f"Title screenshot failed, using full page: {e}", style="yellow")
        page.screenshot(
            path=title_path,
            clip={"x": 0, "y": 0, "width": 1280, "height": 400},
        )


def _take_content_screenshots(page, repo_id: str, W: int, H: int, num_segments: int):
    """Take screenshots of the README and other content sections."""
    readme_selectors = [
        '[data-testid="read-me-content"]',
        "#readme",
        "article.markdown-body",
        ".Box-body .markdown-body",
    ]

    readme_element = None
    for selector in readme_selectors:
        element = page.locator(selector).first
        try:
            if element.is_visible(timeout=2000):
                readme_element = element
                break
        except Exception:
            continue

    if readme_element:
        try:
            box = readme_element.bounding_box()
            if box:
                readme_height = box["height"]
                readme_width = box["width"]
                readme_x = box["x"]
                readme_y = box["y"]

                segment_height = min(readme_height / max(num_segments, 1), 500)

                for i in range(num_segments):
                    segment_y = readme_y + (i * segment_height)
                    if segment_y >= readme_y + readme_height:
                        segment_y = readme_y + readme_height - segment_height

                    clip_region = {
                        "x": max(0, readme_x),
                        "y": max(0, segment_y),
                        "width": min(readme_width, 1280),
                        "height": min(segment_height, 500),
                    }

                    screenshot_path = f"assets/temp/{repo_id}/png/img{i}.png"
                    page.screenshot(path=screenshot_path, clip=clip_region)

                print_substep(
                    f"Captured {num_segments} README segment screenshots.",
                    style="green",
                )
                return
        except Exception as e:
            print_substep(
                f"README segment screenshots failed: {e}", style="yellow"
            )

    readme_path = f"assets/temp/{repo_id}/png/story_content.png"
    try:
        if readme_element:
            readme_element.screenshot(path=readme_path)
        else:
            page.screenshot(
                path=readme_path,
                clip={"x": 0, "y": 400, "width": 1280, "height": 600},
            )

        import shutil
        for i in range(num_segments):
            shutil.copy(readme_path, f"assets/temp/{repo_id}/png/img{i}.png")

        print_substep("README screenshot captured and duplicated for segments.", style="green")
    except Exception as e:
        print_substep(f"Content screenshot failed: {e}", style="red")
        _create_placeholder_screenshots(repo_id, num_segments, W, H)


def _create_placeholder_screenshots(repo_id: str, num_segments: int, W: int, H: int):
    """Create simple placeholder images when screenshots fail."""
    from PIL import Image, ImageDraw, ImageFont
    import os

    for i in range(num_segments):
        img = Image.new("RGBA", (1280, 500), (33, 33, 36, 255))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(os.path.join("fonts", "Roboto-Regular.ttf"), 40)
        except Exception:
            font = ImageFont.load_default()
        draw.text(
            (100, 200),
            f"GitHub Repository",
            fill=(240, 240, 240),
            font=font,
        )
        img.save(f"assets/temp/{repo_id}/png/img{i}.png")

    print_substep("Created placeholder screenshots.", style="yellow")
