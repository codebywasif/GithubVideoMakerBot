# GitHub Video Maker Bot 🚀

Scrapes the trending repositories on GitHub and Automatically create engaging, short-form videos (for TikTok, YouTube Shorts, or Instagram Reels) showcasing trending GitHub repositories!

All done WITHOUT manual video editing or asset compiling. Just pure ✨programming magic✨.

## How it Works 🤔

This bot automatically:
1. Scrapes the **trending repositories** on GitHub.
2. Uses **OpenAI** (or a fallback method) to generate a catchy, concise narration script about the repository.
3. Uses **Text-to-Speech (TTS)** to read the generated script.
4. Uses **Playwright** to navigate to the repository and capture a smooth, dynamic, scrolling video of the actual page.
5. Merges the scrolling video with the TTS voiceover and some chill background music.

The result? A ready-to-upload, high-quality, short-form video that highlights cool open-source projects!

## Requirements

- Python 3.10+
- An OpenAI API Key (for script generation)
- Playwright (installed automatically via the installation steps)

## Installation 👩‍💻

1. **Clone this repository:**
    ```sh
    git clone https://github.com/elebumm/GithubVideoMakerBot.git
    cd GithubVideoMakerBot
    ```

2. **Create and activate a virtual environment:**
    - On **Windows**:
        ```sh
        python -m venv ./venv
        .\venv\Scripts\activate
        ```
    - On **macOS and Linux**:
        ```sh
        python3 -m venv ./venv
        source ./venv/bin/activate
        ```

3. **Install the required dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

4. **Install Playwright and its dependencies:**
    ```sh
    python -m playwright install
    python -m playwright install-deps
    ```

5. **Run the bot:**
    ```sh
    python main.py
    ```

6. **Configuration:**
    - On the first run, the bot will create a `config.toml` file.
    - You must provide your **OpenAI API Key** when prompted.
    - If you need to reconfigure the bot, simply edit `config.toml` directly.

(Note: If you encounter any errors installing or running the bot, try using `python3` or `pip3` instead of `python` or `pip`.)

## Output

Videos are rendered and saved in the `results/github/` directory. The bot keeps track of repositories it has already processed so it won't create duplicate videos.

## Contributing & Ways to improve 📈

In its current state, this bot does exactly what it needs to do. However, improvements can always be made!

- Feel free to submit pull requests or issues.
- Please read our [contributing guidelines](CONTRIBUTING.md) for more detailed information.

## LICENSE
[Roboto Fonts](https://fonts.google.com/specimen/Roboto/about) are licensed under [Apache License V2](https://www.apache.org/licenses/LICENSE-2.0).
This project was initially forked and modified from the Reddit Video Maker Bot project.
