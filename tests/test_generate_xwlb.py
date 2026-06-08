import json
from datetime import date

from scripts.generate_xwlb import (
    build_latest_payload,
    find_episode_url,
    parse_episode_summary,
    render_markdown,
)


def test_find_episode_url_matches_target_date_and_absolutizes_link():
    html = """
    <html>
      <body>
        <a href="https://tv.cctv.com/2026/06/07/VIDEold.shtml">新闻联播 20260607</a>
        <a href="/2026/06/08/VIDEtarget.shtml">新闻联播 20260608</a>
      </body>
    </html>
    """

    result = find_episode_url(html, date(2026, 6, 8))

    assert result == "https://tv.cctv.com/2026/06/08/VIDEtarget.shtml"


def test_parse_episode_summary_extracts_clean_main_content():
    html = """
    <html>
      <body>
        <p>本期节目主要内容：</p>
        <p>1. 国家重点工程建设稳步推进；</p>
        <p>2. 各地加强夏收服务保障；</p>
        <p>（《新闻联播》 20260608 19:00）</p>
      </body>
    </html>
    """

    result = parse_episode_summary(html)

    assert result == [
        "1. 国家重点工程建设稳步推进；",
        "2. 各地加强夏收服务保障；",
    ]


def test_render_markdown_keeps_source_and_summary_items():
    markdown = render_markdown(
        broadcast_date=date(2026, 6, 8),
        source_url="https://tv.cctv.com/2026/06/08/VIDEtarget.shtml",
        summary_items=["1. 国家重点工程建设稳步推进；", "2. 各地加强夏收服务保障；"],
    )

    assert markdown.startswith("# 新闻联播 2026-06-08\n")
    assert "来源：[央视网](https://tv.cctv.com/2026/06/08/VIDEtarget.shtml)" in markdown
    assert "## 主要内容" in markdown
    assert "1. 国家重点工程建设稳步推进；" in markdown


def test_render_markdown_adds_space_after_ordered_list_marker():
    markdown = render_markdown(
        broadcast_date=date(2026, 6, 8),
        source_url="https://tv.cctv.com/2026/06/08/VIDEtarget.shtml",
        summary_items=["1.国家重点工程建设稳步推进；"],
    )

    assert "1. 国家重点工程建设稳步推进；" in markdown


def test_build_latest_payload_points_to_raw_markdown_and_obsidian_file():
    payload = build_latest_payload(
        broadcast_date=date(2026, 6, 8),
        repo="Ranphanie/xinwenlianbo-md",
        branch="main",
        markdown_path="generated/2026/2026-06-08 新闻联播.md",
        obsidian_vault="新闻联播",
        obsidian_file="2026/2026-06-08 新闻联播",
        source_url="https://tv.cctv.com/2026/06/08/VIDEtarget.shtml",
    )

    assert payload["date"] == "2026-06-08"
    assert payload["markdown_url"] == (
        "https://raw.githubusercontent.com/Ranphanie/xinwenlianbo-md/main/"
        "generated/2026/2026-06-08%20%E6%96%B0%E9%97%BB%E8%81%94%E6%92%AD.md"
    )
    assert payload["obsidian"]["vault"] == "新闻联播"
    assert payload["obsidian"]["file"] == "2026/2026-06-08 新闻联播"
    assert "file=2026%2F2026-06-08%20%E6%96%B0%E9%97%BB%E8%81%94%E6%92%AD" in payload["obsidian"]["uri"]
    assert json.dumps(payload, ensure_ascii=False)
