from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup


def extract_article_id(url: str) -> Optional[int]:
    parsed = urlparse(url)
    for part in reversed(parsed.path.strip("/").split("/")):
        if part.isdigit():
            return int(part)
    qs = parse_qs(parsed.query)
    if "articleid" in qs:
        val = qs["articleid"][0]
        if val.isdigit():
            return int(val)
    return None


def parse_article(html: str) -> Tuple[Optional[str], Optional[str], str, str, bool, bool]:
    """(title, posted_at, clean_text, raw_html_fragment, has_media, has_body_container)"""
    soup = BeautifulSoup(html, "html.parser")

    title_el = (
        soup.select_one("h3.title_text")
        or soup.select_one(".ArticleTitle")
        or soup.select_one("#subject")
        or soup.select_one("title")
    )
    title = title_el.get_text(strip=True) if title_el else None

    date_el = (
        soup.select_one(".article_info .date")
        or soup.select_one(".se_publishDate")
        or soup.select_one("span.date")
        or soup.select_one(".author_date")
        or soup.select_one(".write_time")
    )
    posted_at = date_el.get_text(strip=True) if date_el else None

    article_viewer_el = soup.select_one("div.article_viewer")
    if article_viewer_el:
        # 1) article_viewer 내부 ContentRenderer (구 패턴 — 2020.08.03 이전)
        content_el = article_viewer_el.select_one("div.ContentRenderer")

        # 2) frame 전체에서 ContentRenderer (패턴 2 — article_viewer 형제/외부)
        if content_el is None:
            content_el = soup.select_one("div.ContentRenderer")

        # 3) article_viewer 자체를 본문으로 사용 (패턴 1 — ContentRenderer 없이 직접 본문)
        #    안전 잠금: 텍스트 또는 미디어 최소 하나 있어야 인정
        if content_el is None:
            has_direct_text = bool(article_viewer_el.get_text(strip=True))
            has_direct_media = bool(article_viewer_el.find(
                ["img", "video", "iframe", "embed", "audio", "object"]
            ))
            if has_direct_text or has_direct_media:
                content_el = article_viewer_el

        # 3단계 모두 실패 → 진짜 빈 article_viewer → transient
        if content_el is None:
            return title, posted_at, "", str(article_viewer_el), False, False
    else:
        content_el = (
            soup.select_one("div.ContentRenderer")
            or soup.select_one("div.article_container")
            or soup.select_one("div#tbody")
            or soup.select_one("div.se-main-container")
            or soup.select_one("#postContent")
            or soup.select_one(".ArticleContentsArea")
        )

    if content_el:
        clean_text = content_el.get_text(separator="\n", strip=True)
        raw_html = str(content_el)
    else:
        clean_text = soup.get_text(separator="\n", strip=True)
        raw_html = html

    search_root = content_el if content_el else soup
    has_media = bool(search_root.find(["img", "video", "iframe", "embed", "audio", "object"]))

    return title, posted_at, clean_text, raw_html, has_media, True


def parse_article_list(html: str, base_url: str) -> list[dict]:
    """목록 페이지 HTML에서 글 행 목록을 파싱한다.

    Returns:
        [{"article_id": int, "title": str, "url": str, "posted_at": str}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    rows = (
        soup.select("div.article-board tbody tr")
        or soup.select("table.board-box tbody tr")
        or soup.select("ul.article_list li")
        or soup.select("div.board_list_w ul li")
        or soup.select("li.board-list__item")
    )

    for row in rows:
        link_el = (
            row.select_one("a.article")
            or row.select_one("td.td_article a")
            or row.select_one("a.title")
            or row.select_one(".board-list__title a")
        )
        if link_el is None:
            continue

        href = link_el.get("href", "")
        title = link_el.get_text(strip=True)

        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            parsed = urlparse(base_url)
            url = f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            continue

        article_id = extract_article_id(url)
        if not article_id:
            continue

        date_el = (
            row.select_one("td.td_date")
            or row.select_one("span.date")
            or row.select_one(".board-list__date")
        )
        posted_at = date_el.get_text(strip=True) if date_el else None

        results.append({
            "article_id": article_id,
            "title": title,
            "url": url,
            "posted_at": posted_at,
        })

    return results
