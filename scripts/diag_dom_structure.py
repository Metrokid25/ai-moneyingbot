import sys
from pathlib import Path

sys.path.insert(0, "src")

from browser import BrowserSession, wait_for_login
from db import get_article_by_id

CAFE_MEMBERS_URL = (
    "https://cafe.naver.com/f-e/cafes/29082876/members/"
    "THEA7uBzD6uKXKno57_Bl7jItzRnvmuDMltnPsGI9BY"
)

DIAG_DIR = Path("data/diag")

_JS_CANDIDATES = r"""
() => {
    const candidates = [];
    document.querySelectorAll('div, article, section, main').forEach(el => {
        const text = el.innerText || '';
        if (text.length >= 500) {
            let selector = el.tagName.toLowerCase();
            if (el.id) selector += '#' + el.id;
            if (el.className && typeof el.className === 'string') {
                selector += '.' + el.className.trim().split(/\s+/).join('.');
            }
            candidates.push({
                selector,
                textLength: text.length,
                preview: text.slice(0, 100),
                tagName: el.tagName,
                id: el.id,
                className: typeof el.className === 'string' ? el.className : '',
            });
        }
    });
    candidates.sort((a, b) => b.textLength - a.textLength);
    return candidates.slice(0, 10);
}
"""


def _analyze(target, label, save_path):
    SEP = "─" * 70
    print()
    print(SEP)
    print(f"[frame] {label}")
    print(f"  url : {target.url}")

    try:
        html = target.content()
    except Exception as e:
        print(f"  [error] content() 실패: {e}")
        return

    save_path.write_text(html, encoding="utf-8")
    print(f"  DOM : {len(html):,} bytes  →  {save_path.name}")

    try:
        raw_text = target.evaluate("() => document.body?.innerText || ''")
        preview = " ".join(raw_text[:500].split())[:200]
        print(f"  text preview: {preview}")
    except Exception as e:
        print(f"  [warn] innerText 평가 실패: {e}")

    print()
    print(f"  {'rank':>4}  {'chars':>7}  {'selector':<55}  preview(80자)")
    print(f"  {'----':>4}  {'-------':>7}  {'-------':<55}  --------")

    try:
        candidates = target.evaluate(_JS_CANDIDATES)
        if not candidates:
            print("  (텍스트 500자 이상 블록 없음)")
        else:
            for i, c in enumerate(candidates, 1):
                sel = c["selector"][:54]
                prev = " ".join(c["preview"].split())[:80]
                print(f"  {i:>4}  {c['textLength']:>7,}  {sel:<55}  {prev}")
    except Exception as e:
        print(f"  [error] JS 평가 실패: {e}")


def main():
    article_id = int(sys.argv[1]) if len(sys.argv) > 1 else 219

    SEP = "=" * 70
    print(SEP)
    print(f"[diag] diag_dom_structure  article_id={article_id}")
    print(SEP)

    article = get_article_by_id(article_id)
    if article is None:
        print(f"[error] article_id={article_id} DB에 없음")
        return 1

    print(f"[diag] title  : {(article.title or '(none)')[:60]}")
    print(f"[diag] url    : {article.url}")
    print(f"[diag] status : {article.status}")
    print()

    DIAG_DIR.mkdir(parents=True, exist_ok=True)

    print("[diag] 브라우저 세션 시작...")
    session = BrowserSession()

    try:
        print(f"[diag] 카페 멤버 페이지 진입: {CAFE_MEMBERS_URL}")
        session.goto(CAFE_MEMBERS_URL)
        wait_for_login(session.page)

        print(f"\n[diag] article URL 이동: {article.url}")
        session.goto(article.url)

        print("[diag] networkidle 대기 (최대 30초)...")
        try:
            session.page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            print("[warn] networkidle 30초 초과 — 계속 진행")

        print("[diag] Next.js hydration 여유 2초...")
        session.page.wait_for_timeout(2000)

        print(f"[diag] 최종 URL: {session.page.url}")

        frames = session.page.frames
        print(f"\n[diag] 총 frame 수: {len(frames)}")
        print(f"  {'idx':>3}  {'name':<20}  url")
        print(f"  {'---':>3}  {'----':<20}  ---")
        for i, fr in enumerate(frames):
            name = fr.name or "(no name)"
            url = fr.url or "(no url)"
            marker = ""
            if fr.name and ("cafe" in fr.name.lower() or fr.name == "main"):
                marker = "  ← [본문 iframe 후보]"
            print(f"  {i:>3}  {name:<20}  {url}{marker}")

        main_path = DIAG_DIR / f"article_{article_id}_dom_main.html"
        _analyze(session.page, label="MAIN PAGE", save_path=main_path)

        for idx, frame in enumerate(frames[1:], start=1):
            frame_label = f"FRAME[{idx}]  name={frame.name!r}  url={frame.url}"
            frame_path = DIAG_DIR / f"article_{article_id}_dom_frame_{idx}.html"
            _analyze(frame, label=frame_label, save_path=frame_path)

        print()
        print("=" * 70)
        print(f"[diag] 완료. 저장 위치: {DIAG_DIR.resolve()}")
        saved = sorted(DIAG_DIR.glob(f"article_{article_id}_dom_*.html"))
        for f in saved:
            print(f"  {f.name}  ({f.stat().st_size:,} bytes)")

        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
