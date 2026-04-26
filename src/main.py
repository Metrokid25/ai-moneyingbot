import sys
from db import init_db, upsert_article, article_exists
from browser import fetch_page
from parser import extract_article_id, parse_article
from models import Article


def run(url: str) -> None:
    init_db()

    article_id = extract_article_id(url)
    if not article_id:
        print(f"[ERROR] URL에서 article_id를 추출할 수 없습니다: {url}")
        sys.exit(1)

    print(f"[INFO] article_id: {article_id}")

    if article_exists(article_id):
        print(f"[SKIP] 이미 저장된 글입니다 (article_id={article_id})")
        return

    print("[INFO] 브라우저를 열어 페이지를 로드합니다 ...")
    final_url, html, error_reason = fetch_page(url)

    if error_reason:
        article = Article(
            article_id=article_id,
            url=url,
            status="FAILED",
            error_reason=error_reason,
        )
        upsert_article(article)
        print(f"[FAILED] {error_reason}")
        return

    title, posted_at, clean_text, raw_html = parse_article(html)

    article = Article(
        article_id=article_id,
        url=url,
        title=title,
        posted_at=posted_at,
        raw_html=raw_html,
        clean_text=clean_text,
        status="OK",
    )
    upsert_article(article)

    print("[OK] 저장 완료")
    print(f"  title     : {title}")
    print(f"  posted_at : {posted_at}")
    print(f"  chars     : {len(clean_text or '')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python src/main.py <네이버카페_글_URL>")
        sys.exit(1)
    run(sys.argv[1])
