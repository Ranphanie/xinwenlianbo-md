import json
from datetime import date, datetime, timezone

import pytest

import scripts.generate_xwlb as generate_xwlb
from scripts.generate_xwlb import (
    BroadcastNotReady,
    build_latest_payload,
    episode_url_matches_date,
    find_episode_url,
    generate_or_skip,
    parse_episode_summary,
    render_markdown,
    resolve_default_broadcast_date,
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


def test_find_episode_url_raises_not_ready_when_target_date_is_missing():
    html = """
    <html>
      <body>
        <a href="https://tv.cctv.com/2026/06/09/VIDEold.shtml">新闻联播 20260609</a>
      </body>
    </html>
    """

    with pytest.raises(BroadcastNotReady, match="20260610"):
        find_episode_url(html, date(2026, 6, 10))


def test_episode_url_matches_date_accepts_cctv_date_patterns():
    assert episode_url_matches_date(
        "https://tv.cctv.com/2026/06/10/VIDEabcdef260610.shtml",
        date(2026, 6, 10),
    )
    assert not episode_url_matches_date(
        "https://tv.cctv.com/2026/06/09/VIDEabcdef260609.shtml",
        date(2026, 6, 10),
    )


def test_resolve_default_broadcast_date_uses_previous_day_before_20_beijing():
    result = resolve_default_broadcast_date(
        datetime(2026, 6, 11, 19, 59, tzinfo=generate_xwlb.BEIJING_TZ)
    )

    assert result == date(2026, 6, 10)


def test_resolve_default_broadcast_date_uses_current_day_at_20_beijing():
    result = resolve_default_broadcast_date(
        datetime(2026, 6, 11, 20, 0, tzinfo=generate_xwlb.BEIJING_TZ)
    )

    assert result == date(2026, 6, 11)


def test_resolve_default_broadcast_date_converts_aware_time_to_beijing():
    result = resolve_default_broadcast_date(datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc))

    assert result == date(2026, 6, 11)


def test_generate_or_skip_keeps_latest_when_episode_is_not_ready(tmp_path, monkeypatch):
    existing_latest = '{"date": "2026-06-08"}\n'
    (tmp_path / "latest.json").write_text(existing_latest, encoding="utf-8")

    def fake_fetch_text(url: str, timeout: int = 20) -> str:
        return """
        <html>
          <body>
            <a href="https://tv.cctv.com/2026/06/09/VIDEold.shtml">新闻联播 20260609</a>
          </body>
        </html>
        """

    monkeypatch.setattr(generate_xwlb, "fetch_text", fake_fetch_text)

    result = generate_or_skip(
        broadcast_date=date(2026, 6, 10),
        out_dir=tmp_path,
        repo="Ranphanie/xinwenlianbo-md",
        branch="main",
        obsidian_vault="新闻联播",
        use_year_folder=True,
        index_url="https://example.test/index.shtml",
    )

    assert result["date"] == "2026-06-10"
    assert result["status"] == "skipped"
    assert result["reason"] == "episode_not_ready"
    assert (tmp_path / "latest.json").read_text(encoding="utf-8") == existing_latest
    assert not (tmp_path / "2026" / "2026-06-10 新闻联播.md").exists()


def test_generate_or_skip_rejects_episode_url_for_a_different_date(tmp_path, monkeypatch):
    fetch_calls: list[str] = []

    def fake_fetch_text(url: str, timeout: int = 20) -> str:
        fetch_calls.append(url)
        if len(fetch_calls) == 1:
            return """
            <html>
              <body>
                <a href="https://tv.cctv.com/2026/06/09/VIDEwrong260609.shtml">
                  新闻联播 20260610
                </a>
              </body>
            </html>
            """
        raise AssertionError("date-mismatched episode page should not be fetched")

    monkeypatch.setattr(generate_xwlb, "fetch_text", fake_fetch_text)

    result = generate_or_skip(
        broadcast_date=date(2026, 6, 10),
        out_dir=tmp_path,
        repo="Ranphanie/xinwenlianbo-md",
        branch="main",
        obsidian_vault="新闻联播",
        use_year_folder=True,
        index_url="https://example.test/index.shtml",
    )

    assert result["date"] == "2026-06-10"
    assert result["status"] == "skipped"
    assert result["reason"] == "date_mismatch"
    assert fetch_calls == ["https://example.test/index.shtml"]
    assert not (tmp_path / "latest.json").exists()


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
    markdown_content = "# 新闻联播 2026-06-08\n\n## 主要内容\n\n1. 内容一\n"

    payload = build_latest_payload(
        broadcast_date=date(2026, 6, 8),
        repo="Ranphanie/xinwenlianbo-md",
        branch="main",
        markdown_path="generated/2026/2026-06-08 新闻联播.md",
        markdown_content=markdown_content,
        obsidian_vault="新闻联播",
        obsidian_file="2026/2026-06-08 新闻联播",
        source_url="https://tv.cctv.com/2026/06/08/VIDEtarget.shtml",
    )

    assert payload["date"] == "2026-06-08"
    assert payload["markdown_url"] == (
        "https://raw.githubusercontent.com/Ranphanie/xinwenlianbo-md/main/"
        "generated/2026/2026-06-08%20%E6%96%B0%E9%97%BB%E8%81%94%E6%92%AD.md"
    )
    assert payload["markdown_content"] == markdown_content
    assert payload["obsidian"]["vault"] == "新闻联播"
    assert payload["obsidian"]["file"] == "2026/2026-06-08 新闻联播"
    assert "file=2026%2F2026-06-08%20%E6%96%B0%E9%97%BB%E8%81%94%E6%92%AD" in payload["obsidian"]["uri"]
    assert json.dumps(payload, ensure_ascii=False)
