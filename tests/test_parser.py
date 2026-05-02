"""tests/test_parser.py — parse_article() 순수 단위 테스트.

BeautifulSoup 파싱만 검증하므로 DB·브라우저 mock 불필요.
"""
import sys

sys.path.insert(0, "src")

from parser import parse_article


def test_parse_article_viewer_without_content_renderer():
    """article_viewer 존재 + ContentRenderer 미로드 → renderer_loaded=False, has_media=False."""
    html = """
    <html><body>
      <div class="article_viewer">
        <img src="loading.gif" alt="loading">
      </div>
    </body></html>
    """
    title, posted_at, clean_text, raw_html_frag, has_media, renderer_loaded = parse_article(html)
    assert renderer_loaded is False
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
