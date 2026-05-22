import re
from typing import Dict, List

from utils.console import print_step, print_substep


DEFAULT_SYSTEM_PROMPT = """\
You are a tech content creator making a very short video about a trending GitHub repository.
Write a concise, engaging narration script.

Rules:
- MUST start exactly with this phrase: "This repository is trending on GitHub..."
- Do NOT mention or say the repository name or the author name at all.
- Keep it extremely concise and to the point (under {max_words} words).
- Explain why it's interesting or what it does.
- Write in a conversational, enthusiastic tone.
- Do NOT use markdown formatting, emojis, or hashtags.
- Do NOT add a call to action at the end.
"""

USER_PROMPT_TEMPLATE = """\
Repository: {full_name}
Stars: {stars:,} ⭐ | Forks: {forks:,} | Language: {language}
Description: {description}

Topics: {topics}

README excerpt:
{readme_excerpt}
"""


def generate_script(repo_data: Dict, config: Dict) -> str:
    """Generate a narration script for a GitHub repo using an LLM.

    Args:
        repo_data: Enriched repo dict from get_repo_details().
        config: The loaded TOML config dict.

    Returns:
        A narration script string ready for TTS.
    """
    print_step("Generating narration script via LLM...")

    script_config = config.get("script", {})
    provider = script_config.get("provider", "openai")
    max_words = script_config.get("max_script_words", 150)

    # Build the prompts
    system_prompt = script_config.get("custom_prompt", "").strip()
    if not system_prompt:
        system_prompt = DEFAULT_SYSTEM_PROMPT.format(max_words=max_words)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        full_name=repo_data.get("full_name", "unknown/repo"),
        stars=repo_data.get("stars", 0),
        forks=repo_data.get("forks", 0),
        language=repo_data.get("language", "Unknown"),
        description=repo_data.get("description", "No description provided."),
        topics=", ".join(repo_data.get("topics", [])) or "None",
        readme_excerpt=repo_data.get("readme_excerpt", "")[:600] or "Not available.",
    )

    if provider == "openai":
        script = _generate_with_openai(system_prompt, user_prompt, script_config)
    else:
        print_substep(f"Unknown provider '{provider}', falling back to OpenAI.", style="yellow")
        script = _generate_with_openai(system_prompt, user_prompt, script_config)

    if not script:
        print_substep("LLM returned empty script, using fallback.", style="red")
        script = _generate_fallback_script(repo_data)

    # Clean up the script
    script = _clean_script(script)
    print_substep(f"Generated script ({len(script.split())} words).", style="bold green")
    return script


def _generate_with_openai(system_prompt: str, user_prompt: str, script_config: Dict) -> str:
    """Call OpenAI Chat Completions API to generate the script."""
    try:
        from openai import OpenAI
    except ImportError:
        print_substep(
            "openai package not installed. Install with: pip install openai",
            style="red",
        )
        return ""

    api_key = script_config.get("openai_api_key", "")
    if not api_key:
        print_substep("No OpenAI API key configured in [script] section.", style="red")
        return ""

    model = script_config.get("openai_model", "gpt-4o-mini")

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print_substep(f"OpenAI API error: {e}", style="red")
        return ""


def _generate_fallback_script(repo_data: Dict) -> str:
    """Generate a basic script without an LLM, using repo metadata directly."""
    name = repo_data.get("full_name", "this repository")
    desc = repo_data.get("description", "an amazing open-source project")
    stars = repo_data.get("stars", 0)
    lang = repo_data.get("language", "multiple languages")

    return (
        f"Check out {name}, a trending repository on GitHub that's taking the developer "
        f"community by storm! {desc}. "
        f"With over {stars:,} stars and built with {lang}, this project is clearly resonating "
        f"with developers worldwide. "
        f"Whether you're looking for inspiration or a powerful tool to add to your workflow, "
        f"{name.split('/')[-1]} is definitely worth exploring. "
        f"Head over to GitHub, give it a star, and see what all the hype is about!"
    )


def _clean_script(script: str) -> str:
    """Remove unwanted formatting from the LLM-generated script."""
    # Remove markdown-style formatting
    script = re.sub(r"[*_#`]", "", script)
    # Remove emoji characters (common Unicode ranges)
    script = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]",
        "",
        script,
    )
    # Remove hashtags
    script = re.sub(r"#\w+", "", script)
    # Collapse whitespace
    script = re.sub(r"\s+", " ", script).strip()
    return script


def split_script_into_segments(script: str) -> List[str]:
    """Split a narration script into sentence-level segments for TTS + screenshot timing.

    Each segment will get its own TTS audio file and be mapped to a screenshot.

    Args:
        script: The full narration script.

    Returns:
        A list of sentence/segment strings.
    """
    # Split on sentence boundaries (., !, ?) followed by space or end
    raw_segments = re.split(r"(?<=[.!?])\s+", script.strip())

    # Merge very short segments (< 15 chars) with the previous one
    segments = []
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        if segments and len(seg) < 15:
            segments[-1] = segments[-1] + " " + seg
        else:
            segments.append(seg)

    # If we ended up with no segments, use the whole script
    if not segments:
        segments = [script.strip()]

    return segments
