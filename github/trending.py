import base64
import json
import re
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from utils.console import print_step, print_substep


def fetch_trending_repos(
    language: str = "",
    since: str = "daily",
    min_stars: int = 0,
) -> List[Dict]:
    """Scrape GitHub Trending page and return a list of trending repositories.

    Args:
        language: Filter by programming language (e.g. "python"). Empty string for all.
        since: Time range — "daily", "weekly", or "monthly".
        min_stars: Minimum star count to include a repo.

    Returns:
        List of dicts with keys: full_name, description, stars, language, url.
    """
    print_step("Fetching trending repositories from GitHub...")

    url = "https://github.com/trending"
    params = {}
    if language:
        url += f"/{language.lower()}"
    if since:
        params["since"] = since

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print_substep(f"Failed to fetch trending page: {e}", style="red")
        print_substep("Falling back to GitHub API search...", style="yellow")
        return _fallback_api_search(language, since, min_stars)

    soup = BeautifulSoup(resp.text, "html.parser")
    repo_articles = soup.select("article.Box-row")

    if not repo_articles:
        print_substep("No trending repos found via scraping, trying API fallback...", style="yellow")
        return _fallback_api_search(language, since, min_stars)

    repos = []
    for article in repo_articles:
        try:
            repo = _parse_trending_article(article)
            if repo and repo["stars"] >= min_stars:
                repos.append(repo)
        except Exception:
            continue  # skip malformed entries

    print_substep(f"Found {len(repos)} trending repositories.", style="bold green")
    return repos


def _parse_trending_article(article) -> Optional[Dict]:
    """Parse a single <article> element from the GitHub trending page."""
    # Repo name link: h2 > a with href like /owner/repo
    name_link = article.select_one("h2 a")
    if not name_link:
        return None

    href = name_link.get("href", "").strip("/")
    full_name = "/".join(href.split("/")[:2])  # "owner/repo"
    if not full_name or "/" not in full_name:
        return None

    # Description
    desc_tag = article.select_one("p")
    description = desc_tag.get_text(strip=True) if desc_tag else ""

    # Stars — look for the link containing a star SVG or the star count text
    stars = 0
    star_links = article.select("a.Link")
    for link in star_links:
        href_val = link.get("href", "")
        if "/stargazers" in href_val:
            stars_text = link.get_text(strip=True).replace(",", "").replace(".", "")
            try:
                stars = int(stars_text)
            except ValueError:
                stars = 0
            break

    # If the above didn't work, try a broader search for star count
    if stars == 0:
        for link in article.select("a"):
            href_val = link.get("href", "")
            if "/stargazers" in href_val:
                stars_text = link.get_text(strip=True).replace(",", "").replace(".", "")
                try:
                    stars = int(stars_text)
                except ValueError:
                    stars = 0
                break

    # Language
    lang_span = article.select_one('[itemprop="programmingLanguage"]')
    language = lang_span.get_text(strip=True) if lang_span else ""

    return {
        "full_name": full_name,
        "description": description,
        "stars": stars,
        "language": language,
        "url": f"https://github.com/{full_name}",
    }


def _fallback_api_search(
    language: str = "",
    since: str = "daily",
    min_stars: int = 0,
    token: str = "",
) -> List[Dict]:
    """Fallback: use GitHub REST API search to find popular recent repos."""
    from datetime import datetime, timedelta

    days_map = {"daily": 1, "weekly": 7, "monthly": 30}
    days = days_map.get(since, 1)
    date_threshold = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = f"created:>{date_threshold} stars:>={max(min_stars, 10)}"
    if language:
        query += f" language:{language}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GithubVideoMakerBot/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": 30}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print_substep(f"API search also failed: {e}", style="red")
        return []

    repos = []
    for item in data.get("items", []):
        repos.append(
            {
                "full_name": item["full_name"],
                "description": item.get("description") or "",
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language") or "",
                "url": item["html_url"],
            }
        )

    print_substep(f"Found {len(repos)} repos via API search.", style="bold green")
    return repos


def get_repo_details(repo_full_name: str, token: str = "") -> Dict:
    """Fetch full details for a single repository via the GitHub API.

    Args:
        repo_full_name: e.g. "vercel/next.js"
        token: Optional GitHub PAT for higher rate limits.

    Returns:
        Enriched dict with: full_name, description, stars, forks, language,
        topics, readme_excerpt, url, owner_avatar_url.
    """
    print_step(f"Fetching details for {repo_full_name}...")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GithubVideoMakerBot/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Fetch repo metadata
    repo_url = f"https://api.github.com/repos/{repo_full_name}"
    try:
        resp = requests.get(repo_url, headers=headers, timeout=30)
        resp.raise_for_status()
        repo_data = resp.json()
    except requests.RequestException as e:
        print_substep(f"Failed to fetch repo details: {e}", style="red")
        return {
            "full_name": repo_full_name,
            "description": "",
            "stars": 0,
            "forks": 0,
            "language": "",
            "topics": [],
            "readme_excerpt": "",
            "url": f"https://github.com/{repo_full_name}",
            "owner_avatar_url": "",
        }

    # Fetch README
    readme_excerpt = ""
    readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
    try:
        readme_resp = requests.get(readme_url, headers=headers, timeout=30)
        if readme_resp.status_code == 200:
            readme_data = readme_resp.json()
            content_b64 = readme_data.get("content", "")
            if content_b64:
                raw_readme = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                # Strip markdown formatting for the excerpt
                clean_readme = _strip_markdown(raw_readme)
                readme_excerpt = clean_readme[:800].strip()
    except Exception:
        readme_excerpt = ""

    result = {
        "full_name": repo_data.get("full_name", repo_full_name),
        "description": repo_data.get("description") or "",
        "stars": repo_data.get("stargazers_count", 0),
        "forks": repo_data.get("forks_count", 0),
        "language": repo_data.get("language") or "",
        "topics": repo_data.get("topics", []),
        "readme_excerpt": readme_excerpt,
        "url": repo_data.get("html_url", f"https://github.com/{repo_full_name}"),
        "owner_avatar_url": repo_data.get("owner", {}).get("avatar_url", ""),
    }

    print_substep(
        f"✅ {result['full_name']} — ⭐ {result['stars']} — {result['language']}",
        style="bold green",
    )
    return result


def _strip_markdown(text: str) -> str:
    """Crudely strip markdown formatting from text for use in LLM prompts."""
    # Remove images
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Remove links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"[*_]{1,3}", "", text)
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def get_undone_repo(repos: List[Dict], done_ids: List[str]) -> Optional[Dict]:
    """Return the first trending repo not already in the done list.

    Args:
        repos: List of trending repo dicts (must have 'full_name').
        done_ids: List of repo IDs (sanitized full_name) that are already processed.

    Returns:
        The first undone repo dict, or None if all are done.
    """
    for repo in repos:
        repo_id = sanitize_repo_id(repo["full_name"])
        if repo_id not in done_ids:
            return repo

    print_substep("All trending repos have already been processed!", style="yellow")
    return None


def sanitize_repo_id(full_name: str) -> str:
    """Convert a repo full_name like 'owner/repo' into a safe ID string."""
    return re.sub(r"[^\w\s-]", "", full_name.replace("/", "-"))
