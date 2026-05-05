"""tests/test_parser.py — parse_article() 순수 단위 테스트.

BeautifulSoup 파싱만 검증하므로 DB·브라우저 mock 불필요.
"""
import sys

sys.path.insert(0, "src")

from parser import parse_article


def test_parse_article_viewer_without_content_renderer():
    """진짜 빈 article_viewer 거부 — 텍스트·미디어 모두 없으면 has_body_container=False."""
    # 구 안전망: "ContentRenderer 미로드 + placeholder img → has_media 오판 차단"
    # 새 시스템: img-only 글도 정상 인정 (차트 1장 게시글 실존).
    # 현재 테스트는 "진짜 빈 article_viewer(텍스트도 미디어도 없음)는 거부"를 검증.
    html = """
    <html><body>
      <div class="article_viewer"></div>
    </body></html>
    """
    title, posted_at, clean_text, raw_html_frag, has_media, has_body_container = parse_article(html)
    assert has_body_container is False
    assert has_media is False
    assert clean_text == ""
    assert "article_viewer" in raw_html_frag


def test_parse_article_viewer_with_content_renderer_and_text():
    """article_viewer + ContentRenderer + 텍스트 → renderer_loaded=True, clean_text 추출."""
    html = """
    <html><body>
      <div class="article_viewer">
        <div class="ContentRenderer">
          <p>오늘 시장 분석 내용입니다.</p>
        </div>
      </div>
    </body></html>
    """
    title, posted_at, clean_text, raw_html_frag, has_media, renderer_loaded = parse_article(html)
    assert renderer_loaded is True
    assert "오늘 시장 분석 내용입니다." in clean_text
    assert has_media is False


def test_parse_article_viewer_with_content_renderer_media_only():
    """article_viewer + ContentRenderer + 이미지만(텍스트 없음) → renderer_loaded=True, has_media=True."""
    html = """
    <html><body>
      <div class="article_viewer">
        <div class="ContentRenderer">
          <img src="chart.png">
        </div>
      </div>
    </body></html>
    """
    title, posted_at, clean_text, raw_html_frag, has_media, renderer_loaded = parse_article(html)
    assert renderer_loaded is True
    assert has_media is True
    assert clean_text == ""
