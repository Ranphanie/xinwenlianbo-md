from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


CCTV_XWLB_INDEX_URL = "https://tv.cctv.com/lm/xwlb/index.shtml"
DEFAULT_REPO = "Ranphanie/xinwenlianbo-md"
DEFAULT_BRANCH = "main"
DEFAULT_OBSIDIAN_VAULT = "新闻联播"
BEIJING_TZ = timezone(timedelta(hours=8))


class BroadcastNotReady(ValueError):
    """The target broadcast is not published on the CCTV index yet."""


class BroadcastDateMismatch(ValueError):
    """The discovered episode URL does not belong to the requested date."""


@dataclass(frozen=True)
class GeneratedPaths:
    markdown_path: Path
    latest_path: Path
    obsidian_file: str


def beijing_today() -> date:
    return now_beijing().date()


def now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def fetch_text(url: str, timeout: int = 20) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return response.text


def find_episode_url(index_html: str, target_date: date, base_url: str = CCTV_XWLB_INDEX_URL) -> str:
    soup = BeautifulSoup(index_html, "html.parser")
    yyyymmdd = target_date.strftime("%Y%m%d")
    slash_date = target_date.strftime("%Y/%m/%d")

    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        haystack = " ".join(
            value.strip()
            for value in [
                anchor.get_text(" ", strip=True),
                anchor.get("title", ""),
                anchor["href"],
            ]
            if value
        )
        if "新闻联播" not in haystack:
            continue
        if yyyymmdd in haystack or slash_date in haystack:
            candidates.append(urljoin(base_url, anchor["href"]))

    if candidates:
        return candidates[0]

    raise BroadcastNotReady(f"没有在央视网栏目页找到 {yyyymmdd} 的《新闻联播》节目链接")


def episode_url_matches_date(episode_url: str, target_date: date) -> bool:
    slash_date = target_date.strftime("/%Y/%m/%d/")
    compact_date = target_date.strftime("%Y%m%d")
    short_compact_date = target_date.strftime("%y%m%d")
    return (
        slash_date in episode_url
        or compact_date in episode_url
        or short_compact_date in episode_url
    )


def parse_episode_summary(episode_html: str) -> list[str]:
    soup = BeautifulSoup(episode_html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    lines = [
        _normalize_text(line)
        for line in soup.get_text("\n").splitlines()
        if _normalize_text(line)
    ]

    start_index = _find_summary_start(lines)
    if start_index is None:
        raise ValueError("节目页中没有找到“本期节目主要内容”")

    items: list[str] = []
    first_line = lines[start_index]
    after_marker = re.sub(r"^.*?本期节目主要内容[:：]\s*", "", first_line).strip()
    if after_marker and after_marker != first_line:
        items.extend(_split_summary_line(after_marker))

    for line in lines[start_index + 1 :]:
        if _is_summary_end(line):
            break
        if line == "本期节目主要内容：":
            continue
        items.extend(_split_summary_line(line))

    cleaned = [_strip_noise(item) for item in items]
    return [item for item in cleaned if item]


def render_markdown(broadcast_date: date, source_url: str, summary_items: Iterable[str]) -> str:
    lines = [
        f"# 新闻联播 {broadcast_date.isoformat()}",
        "",
        f"来源：[央视网]({source_url})",
        "",
        "## 主要内容",
        "",
    ]
    lines.extend(_format_markdown_item(item) for item in summary_items)
    lines.append("")
    return "\n".join(lines)


def build_latest_payload(
    broadcast_date: date,
    repo: str,
    branch: str,
    markdown_path: str,
    obsidian_vault: str,
    obsidian_file: str,
    source_url: str,
) -> dict:
    encoded_path = quote(markdown_path.replace("\\", "/"), safe="/")
    encoded_vault = quote(obsidian_vault, safe="")
    encoded_file = quote(obsidian_file, safe="")
    markdown_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{encoded_path}"
    obsidian_uri = (
        f"obsidian://new?vault={encoded_vault}"
        f"&file={encoded_file}"
        "&clipboard=true"
        "&overwrite=true"
    )
    return {
        "date": broadcast_date.isoformat(),
        "title": f"新闻联播 {broadcast_date.isoformat()}",
        "source_url": source_url,
        "markdown_path": markdown_path.replace("\\", "/"),
        "markdown_url": markdown_url,
        "obsidian": {
            "vault": obsidian_vault,
            "file": obsidian_file,
            "uri": obsidian_uri,
        },
    }


def make_generated_paths(out_dir: Path, broadcast_date: date, use_year_folder: bool = True) -> GeneratedPaths:
    filename = f"{broadcast_date.isoformat()} 新闻联播.md"
    year = str(broadcast_date.year)
    markdown_path = out_dir / year / filename if use_year_folder else out_dir / filename
    obsidian_file = f"{year}/{broadcast_date.isoformat()} 新闻联播" if use_year_folder else f"{broadcast_date.isoformat()} 新闻联播"
    return GeneratedPaths(
        markdown_path=markdown_path,
        latest_path=out_dir / "latest.json",
        obsidian_file=obsidian_file,
    )


def generate(
    broadcast_date: date,
    out_dir: Path,
    repo: str,
    branch: str,
    obsidian_vault: str,
    use_year_folder: bool,
    index_url: str = CCTV_XWLB_INDEX_URL,
) -> dict:
    index_html = fetch_text(index_url)
    episode_url = find_episode_url(index_html, broadcast_date, base_url=index_url)
    if not episode_url_matches_date(episode_url, broadcast_date):
        raise BroadcastDateMismatch(
            f"栏目页链接日期与目标日期不一致：target={broadcast_date.isoformat()} url={episode_url}"
        )
    episode_html = fetch_text(episode_url)
    summary_items = parse_episode_summary(episode_html)

    paths = make_generated_paths(out_dir, broadcast_date, use_year_folder=use_year_folder)
    paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(broadcast_date, episode_url, summary_items)
    paths.markdown_path.write_text(markdown, encoding="utf-8", newline="\n")

    payload = build_latest_payload(
        broadcast_date=broadcast_date,
        repo=repo,
        branch=branch,
        markdown_path=paths.markdown_path.as_posix(),
        obsidian_vault=obsidian_vault,
        obsidian_file=paths.obsidian_file,
        source_url=episode_url,
    )
    paths.latest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def generate_or_skip(
    broadcast_date: date,
    out_dir: Path,
    repo: str,
    branch: str,
    obsidian_vault: str,
    use_year_folder: bool,
    index_url: str = CCTV_XWLB_INDEX_URL,
) -> dict:
    try:
        return generate(
            broadcast_date=broadcast_date,
            out_dir=out_dir,
            repo=repo,
            branch=branch,
            obsidian_vault=obsidian_vault,
            use_year_folder=use_year_folder,
            index_url=index_url,
        )
    except BroadcastNotReady as exc:
        return build_skip_payload(
            broadcast_date=broadcast_date,
            reason="episode_not_ready",
            message=str(exc),
        )
    except BroadcastDateMismatch as exc:
        return build_skip_payload(
            broadcast_date=broadcast_date,
            reason="date_mismatch",
            message=str(exc),
        )


def build_skip_payload(broadcast_date: date, reason: str, message: str) -> dict:
    return {
        "date": broadcast_date.isoformat(),
        "status": "skipped",
        "reason": reason,
        "message": message,
        "timezone": "Asia/Shanghai",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成当天《新闻联播》Markdown 文稿。")
    parser.add_argument("--date", help="指定日期，格式为 YYYY-MM-DD。默认使用北京时间当天。")
    parser.add_argument("--out-dir", default="generated", help="输出目录。")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub 仓库，格式为 owner/repo。")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="raw 文件所在分支。")
    parser.add_argument("--obsidian-vault", default=DEFAULT_OBSIDIAN_VAULT, help="Obsidian vault 名称。")
    parser.add_argument(
        "--no-year-folder",
        action="store_true",
        help="不使用年份子目录，直接生成到输出目录根部。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    broadcast_date = date.fromisoformat(args.date) if args.date else beijing_today()
    payload = generate_or_skip(
        broadcast_date=broadcast_date,
        out_dir=Path(args.out_dir),
        repo=args.repo,
        branch=args.branch,
        obsidian_vault=args.obsidian_vault,
        use_year_folder=not args.no_year_folder,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _find_summary_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if "本期节目主要内容" in line:
            return index
    return None


def _is_summary_end(line: str) -> bool:
    end_markers = [
        "《新闻联播》",
        "（新闻联播）",
        "央视网消息",
        "来源：",
        "责任编辑：",
        "编辑：",
    ]
    return any(marker in line for marker in end_markers)


def _split_summary_line(line: str) -> list[str]:
    line = _strip_noise(line)
    if not line:
        return []
    matches = list(re.finditer(r"(?=(?:^|\s)(?:\d+|[一二三四五六七八九十]+)[.、])", line))
    if len(matches) <= 1:
        return [line]
    items: list[str] = []
    for current, next_match in zip(matches, matches[1:] + [None]):
        start = current.start()
        end = next_match.start() if next_match else len(line)
        items.append(line[start:end].strip())
    return items


def _strip_noise(value: str) -> str:
    value = re.sub(r"^本期节目主要内容[:：]\s*", "", value)
    value = re.sub(r"（?《新闻联播》.*$", "", value)
    return value.strip()


def _format_markdown_item(value: str) -> str:
    return re.sub(r"^(\d+)\.(\S)", r"\1. \2", value.strip())


if __name__ == "__main__":
    main()
