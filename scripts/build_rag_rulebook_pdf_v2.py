from __future__ import annotations

import argparse
import html
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "artifacts" / "rulebook_v2" / "rules_v2.json"
DELTA_PATH = (
    ROOT
    / "artifacts"
    / "rulebook_v2"
    / "minipc_articles_172570_173508.jsonl"
)
DEFAULT_DB = Path(r"C:\projects\naver_cafe_archive\data\archive.db")
DEFAULT_OUT = ROOT / "output" / "pdf" / "굿머닝_매매원칙_검증판_v2.pdf"
MALGUN = Path(r"C:\Windows\Fonts\malgun.ttf")
MALGUN_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

NAVY = HexColor("#15253B")
NAVY_2 = HexColor("#203A5F")
TEAL = HexColor("#0E7C7B")
TEAL_LIGHT = HexColor("#E8F5F3")
ORANGE = HexColor("#E67E22")
ORANGE_LIGHT = HexColor("#FFF2E8")
RED = HexColor("#C0392B")
RED_LIGHT = HexColor("#FCEDEC")
BLUE_LIGHT = HexColor("#EAF1F8")
INK = HexColor("#17202A")
MUTED = HexColor("#5E6B75")
LINE = HexColor("#D6DEE5")
PAPER = HexColor("#F7F9FB")
WHITE = colors.white


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the evidence-backed Good Morning trading rulebook PDF v2."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--rules-path", type=Path, default=RULES_PATH)
    parser.add_argument("--delta-path", type=Path, default=DELTA_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        if raw.strip():
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def load_archive_union(
    db_path: Path, delta_path: Path
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        if con.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise RuntimeError("archive connection is not query_only")
        columns = [
            row[1] for row in con.execute("PRAGMA table_info(articles)").fetchall()
        ]
        required = {"article_id", "title", "url", "posted_at", "clean_text", "status"}
        if not required.issubset(columns):
            raise RuntimeError(f"archive schema missing: {sorted(required - set(columns))}")
        archive: dict[int, dict[str, Any]] = {}
        sql = (
            "SELECT article_id,title,url,posted_at,clean_text,status "
            "FROM articles ORDER BY article_id"
        )
        for row in con.execute(sql):
            archive[int(row[0])] = {
                "article_id": int(row[0]),
                "title": row[1] or "",
                "url": row[2] or "",
                "posted_at": row[3] or "",
                "clean_text": row[4] or "",
                "status": row[5] or "",
                "provenance": "desktop_archive_db",
            }
    finally:
        con.close()

    local_count = len(archive)
    overlap: list[int] = []
    delta_rows = read_jsonl(delta_path)
    for row in delta_rows:
        article_id = int(row["article_id"])
        if article_id in archive:
            overlap.append(article_id)
        archive[article_id] = {
            "article_id": article_id,
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "posted_at": row.get("posted_at") or "",
            "clean_text": row.get("clean_text") or "",
            "status": row.get("status") or "",
            "provenance": "minipc_readonly_jsonl",
        }
    stats = {
        "local_count": local_count,
        "delta_count": len(delta_rows),
        "union_count": len(archive),
        "delta_overlap_count": len(overlap),
        "min_article_id": min(archive),
        "max_article_id": max(archive),
        "status_counts": dict(Counter(row["status"] for row in archive.values())),
        "query_only": True,
    }
    return archive, stats


def normalize_space(value: str) -> str:
    return " ".join((value or "").replace("\u200b", " ").replace("\xa0", " ").split())


def validate_rules(
    package: dict[str, Any], archive: dict[int, dict[str, Any]], stats: dict[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    rule_ids: set[str] = set()
    source_ids: set[int] = set()
    exact_quote_checks = 0
    grade_counts: Counter[str] = Counter()

    if package.get("current_archive_article_count") != stats["union_count"]:
        errors.append(
            "configured current_archive_article_count does not match archive union"
        )
    if package.get("local_archive_article_count") != stats["local_count"]:
        errors.append("configured local_archive_article_count does not match local DB")
    if package.get("minipc_delta_export_count") != stats["delta_count"]:
        errors.append("configured minipc_delta_export_count does not match JSONL")
    if stats["delta_overlap_count"]:
        errors.append("desktop DB and miniPC delta JSONL overlap")
    if package.get("latest_article_id") != stats["max_article_id"]:
        errors.append("configured latest_article_id does not match archive union")

    required_rule_fields = {
        "rule_id",
        "name",
        "one_line",
        "mentor_claim",
        "operational_hypothesis",
        "prerequisites",
        "action",
        "invalidation",
        "exceptions",
        "automation_grade",
        "evidence_grade",
        "data_required",
        "validation",
        "sources",
    }
    for index, rule in enumerate(package.get("rules", []), start=1):
        missing = required_rule_fields - set(rule)
        if missing:
            errors.append(f"rule #{index} missing fields: {sorted(missing)}")
        rule_id = rule.get("rule_id", f"#{index}")
        if rule_id in rule_ids:
            errors.append(f"duplicate rule_id: {rule_id}")
        rule_ids.add(rule_id)
        grade = rule.get("automation_grade")
        grade_counts[grade] += 1
        if grade not in {"A", "B", "C"}:
            errors.append(f"{rule_id}: invalid automation grade {grade!r}")
        if not rule.get("exceptions"):
            errors.append(f"{rule_id}: at least one exception/caveat is required")
        if "검증" not in rule.get("validation", ""):
            warnings.append(f"{rule_id}: validation field does not include '검증'")
        for source in rule.get("sources", []):
            article_id = int(source["article_id"])
            source_ids.add(article_id)
            article = archive.get(article_id)
            if article is None:
                errors.append(f"{rule_id}: article_id {article_id} not found")
                continue
            quote = normalize_space(source.get("quote", ""))
            body = normalize_space(article.get("clean_text", ""))
            if not quote:
                errors.append(f"{rule_id}: empty quote for article_id {article_id}")
            elif quote not in body:
                errors.append(
                    f"{rule_id}: quote not found verbatim after whitespace normalization "
                    f"for article_id {article_id}: {quote!r}"
                )
            else:
                exact_quote_checks += 1

    if not package.get("rules"):
        errors.append("no rules")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema_version": package.get("schema_version"),
        "rule_count": len(package["rules"]),
        "source_article_count": len(source_ids),
        "quote_checks_passed": exact_quote_checks,
        "automation_grade_counts": dict(sorted(grade_counts.items())),
        "warnings": warnings,
        "archive": stats,
    }


def register_fonts() -> None:
    if not MALGUN.exists() or not MALGUN_BOLD.exists():
        raise FileNotFoundError("Malgun Gothic font files were not found")
    pdfmetrics.registerFont(TTFont("Malgun", str(MALGUN)))
    pdfmetrics.registerFont(TTFont("Malgun-Bold", str(MALGUN_BOLD)))
    pdfmetrics.registerFontFamily(
        "Malgun",
        normal="Malgun",
        bold="Malgun-Bold",
        italic="Malgun",
        boldItalic="Malgun-Bold",
    )


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName="Malgun-Bold",
            fontSize=10,
            leading=14,
            textColor=TEAL,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Malgun-Bold",
            fontSize=29,
            leading=37,
            textColor=NAVY,
            spaceAfter=11,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName="Malgun",
            fontSize=14,
            leading=21,
            textColor=MUTED,
            spaceAfter=20,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Malgun-Bold",
            fontSize=21,
            leading=27,
            textColor=NAVY,
            spaceBefore=3,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Malgun-Bold",
            fontSize=14,
            leading=19,
            textColor=NAVY_2,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Malgun-Bold",
            fontSize=10,
            leading=14,
            textColor=TEAL,
            spaceBefore=4,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Malgun",
            fontSize=9.1,
            leading=14.2,
            textColor=INK,
            spaceAfter=5,
            wordWrap="CJK",
        ),
        "body_small": ParagraphStyle(
            "body_small",
            parent=base["BodyText"],
            fontName="Malgun",
            fontSize=7.7,
            leading=11.5,
            textColor=INK,
            spaceAfter=3,
            wordWrap="CJK",
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["BodyText"],
            fontName="Malgun",
            fontSize=7.7,
            leading=11.5,
            textColor=MUTED,
            wordWrap="CJK",
        ),
        "quote": ParagraphStyle(
            "quote",
            parent=base["BodyText"],
            fontName="Malgun",
            fontSize=8.1,
            leading=12.2,
            textColor=NAVY_2,
            leftIndent=4,
            rightIndent=3,
            wordWrap="CJK",
        ),
        "table": ParagraphStyle(
            "table",
            parent=base["BodyText"],
            fontName="Malgun",
            fontSize=7.4,
            leading=10.5,
            textColor=INK,
            wordWrap="CJK",
        ),
        "table_bold": ParagraphStyle(
            "table_bold",
            parent=base["BodyText"],
            fontName="Malgun-Bold",
            fontSize=7.4,
            leading=10.5,
            textColor=NAVY,
            wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["BodyText"],
            fontName="Malgun-Bold",
            fontSize=7.4,
            leading=10.5,
            textColor=WHITE,
            wordWrap="CJK",
        ),
        "badge": ParagraphStyle(
            "badge",
            parent=base["Normal"],
            fontName="Malgun-Bold",
            fontSize=8,
            leading=11,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "metric_number": ParagraphStyle(
            "metric_number",
            parent=base["Normal"],
            fontName="Malgun-Bold",
            fontSize=20,
            leading=23,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "metric_label",
            parent=base["Normal"],
            fontName="Malgun",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Malgun",
            fontSize=6.8,
            leading=8,
            textColor=MUTED,
        ),
    }


def P(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(esc(text).replace("\n", "<br/>"), style)


def rich(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def bullets(items: Iterable[str], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable(
        [
            ListItem(P(item, styles["body"]), leftIndent=12, bulletColor=TEAL)
            for item in items
        ],
        bulletType="bullet",
        start="circle",
        leftIndent=15,
        bulletFontName="Malgun",
        bulletFontSize=6,
        spaceAfter=4,
    )


def section_title(
    number: str, title: str, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    return [
        P(f"{number}  {title}", styles["h1"]),
        HRFlowable(width="100%", thickness=1.2, color=TEAL, spaceAfter=10),
    ]


def callout(
    title: str,
    body: str,
    styles: dict[str, ParagraphStyle],
    background: colors.Color = BLUE_LIGHT,
    accent: colors.Color = TEAL,
) -> Table:
    content = [
        P(title, styles["table_bold"]),
        P(body, styles["table"]),
    ]
    table = Table([[content]], colWidths=[169 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.7, accent),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def metric_cards(
    metrics: list[tuple[str, str]], styles: dict[str, ParagraphStyle]
) -> Table:
    cells = []
    for number, label in metrics:
        cells.append(
            [
                P(number, styles["metric_number"]),
                P(label, styles["metric_label"]),
            ]
        )
    table = Table([cells], colWidths=[169 * mm / len(cells)])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def grade_chart(
    grade_counts: dict[str, int], styles: dict[str, ParagraphStyle]
) -> Drawing:
    drawing = Drawing(480, 170)
    chart = VerticalBarChart()
    chart.x = 65
    chart.y = 35
    chart.height = 105
    chart.width = 350
    chart.data = [[grade_counts.get("A", 0), grade_counts.get("B", 0), grade_counts.get("C", 0)]]
    chart.categoryAxis.categoryNames = ["A 자동화 가능", "B 정의 필요", "C 연구/수동"]
    chart.categoryAxis.labels.fontName = "Malgun"
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(6, max(grade_counts.values()) + 1)
    chart.valueAxis.valueStep = 1
    chart.valueAxis.labels.fontName = "Malgun"
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = TEAL
    chart.bars[0].strokeColor = TEAL
    drawing.add(chart)
    drawing.add(
        String(
            240,
            155,
            "자동화 등급 분포",
            fontName="Malgun-Bold",
            fontSize=11,
            fillColor=NAVY,
            textAnchor="middle",
        )
    )
    return drawing


def page_decorator(canvas: Any, doc: BaseDocTemplate, package: dict[str, Any]) -> None:
    canvas.saveState()
    width, height = A4
    if doc.page > 1:
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(19 * mm, height - 14.5 * mm, width - 19 * mm, height - 14.5 * mm)
        canvas.setFont("Malgun", 6.8)
        canvas.setFillColor(MUTED)
        canvas.drawString(19 * mm, height - 11.7 * mm, "굿머닝 매매원칙 검증판 v2")
        canvas.drawRightString(
            width - 19 * mm,
            height - 11.7 * mm,
            f"Archive {package['current_archive_article_count']:,}건 · {package['as_of_kst']} KST",
        )
        canvas.line(19 * mm, 13 * mm, width - 19 * mm, 13 * mm)
        canvas.drawString(19 * mm, 9 * mm, "연구·검증용 / 수익 보장 아님")
        canvas.setFont("Malgun-Bold", 7.5)
        canvas.drawCentredString(width - 14 * mm, 9 * mm, f"{doc.page:02d}")
    canvas.restoreState()


class RulebookDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, package: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(filename, **kwargs)
        self.package = package
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="content",
                    frames=[frame],
                    onPage=lambda canvas, doc: page_decorator(canvas, doc, package),
                )
            ]
        )

    def beforeDocument(self) -> None:
        self.canv.setTitle(self.package["title"])
        self.canv.setAuthor("ai-moneyingbot RAG research")
        self.canv.setSubject("Evidence-backed trading rule research specification")
        self.canv.setKeywords("RAG, article_id, trading rules, validation")


def source_link(article: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Paragraph:
    title = article["title"] or "(제목 없음)"
    label = f"article_id {article['article_id']} · {article['posted_at']} · {title}"
    if article["url"]:
        return rich(
            f'<link href="{esc(article["url"])}" color="#0E7C7B">{esc(label)}</link>',
            styles["muted"],
        )
    return P(label, styles["muted"])


def rule_card(
    rule: dict[str, Any],
    archive: dict[int, dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    grade_color = {"A": TEAL, "B": ORANGE, "C": RED}[rule["automation_grade"]]
    header = Table(
        [
            [
                P(rule["rule_id"], styles["badge"]),
                P(rule["name"], styles["h2"]),
                P(f"자동화 {rule['automation_grade']}", styles["badge"]),
                P(f"근거 {rule['evidence_grade']}", styles["badge"]),
            ]
        ],
        colWidths=[22 * mm, 100 * mm, 24 * mm, 23 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), NAVY),
                ("BACKGROUND", (2, 0), (2, 0), grade_color),
                ("BACKGROUND", (3, 0), (3, 0), NAVY_2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
            ]
        )
    )

    distinction = Table(
        [
            [
                P("선생님 직접 가르침", styles["table_header"]),
                P(rule["mentor_claim"], styles["table"]),
            ],
            [
                P("연구자 구현 가설", styles["table_header"]),
                P(rule["operational_hypothesis"], styles["table"]),
            ],
        ],
        colWidths=[34 * mm, 135 * mm],
    )
    distinction.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), NAVY),
                ("TEXTCOLOR", (0, 0), (0, -1), WHITE),
                ("BACKGROUND", (1, 0), (1, 0), TEAL_LIGHT),
                ("BACKGROUND", (1, 1), (1, 1), ORANGE_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    logic_rows = [
        [
            P("필요 조건", styles["table_bold"]),
            P(" · ".join(rule["prerequisites"]), styles["table"]),
        ],
        [P("행동", styles["table_bold"]), P(rule["action"], styles["table"])],
        [
            P("무효화/해제", styles["table_bold"]),
            P(rule["invalidation"], styles["table"]),
        ],
        [
            P("필요 데이터", styles["table_bold"]),
            P(" · ".join(rule["data_required"]), styles["table"]),
        ],
    ]
    logic = Table(logic_rows, colWidths=[28 * mm, 141 * mm])
    logic.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )

    quote_rows = []
    for source in rule["sources"]:
        article = archive[int(source["article_id"])]
        quote_rows.append(
            [
                source_link(article, styles),
                P(f"“{source['quote']}”", styles["quote"]),
                P(source["role"], styles["muted"]),
            ]
        )
    quotes = Table(quote_rows, colWidths=[55 * mm, 92 * mm, 22 * mm])
    quotes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    exception_text = " / ".join(rule["exceptions"])
    validation = callout(
        "검증 전제",
        f"{rule['validation']}  |  예외·충돌: {exception_text}",
        styles,
        background=RED_LIGHT if rule["automation_grade"] == "C" else ORANGE_LIGHT,
        accent=RED if rule["automation_grade"] == "C" else ORANGE,
    )

    return [
        header,
        Spacer(1, 5),
        P(rule["one_line"], styles["body"]),
        distinction,
        Spacer(1, 6),
        logic,
        Spacer(1, 6),
        P("원문 근거", styles["h3"]),
        quotes,
        Spacer(1, 6),
        validation,
    ]


def landscape_table(
    rules: list[dict[str, Any]], styles: dict[str, ParagraphStyle]
) -> Table:
    rows = [
        [
            P("ID", styles["table_header"]),
            P("원칙", styles["table_header"]),
            P("자동화", styles["table_header"]),
            P("근거", styles["table_header"]),
            P("현재 상태", styles["table_header"]),
        ]
    ]
    for rule in rules:
        rows.append(
            [
                P(rule["rule_id"], styles["table_bold"]),
                P(rule["name"], styles["table"]),
                P(rule["automation_grade"], styles["table_bold"]),
                P(rule["evidence_grade"], styles["table"]),
                P("검증 전 가설", styles["table"]),
            ]
        )
    table = Table(rows, colWidths=[22 * mm, 78 * mm, 20 * mm, 20 * mm, 29 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row in range(1, len(rows)):
        if row % 2 == 0:
            style.append(("BACKGROUND", (0, row), (-1, row), PAPER))
    table.setStyle(TableStyle(style))
    return table


def source_index_table(
    package: dict[str, Any],
    archive: dict[int, dict[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    source_to_rules: dict[int, set[str]] = {}
    source_to_roles: dict[int, set[str]] = {}
    for rule in package["rules"]:
        for source in rule["sources"]:
            article_id = int(source["article_id"])
            source_to_rules.setdefault(article_id, set()).add(rule["rule_id"])
            source_to_roles.setdefault(article_id, set()).add(source["role"])
    rows = [
        [
            P("article_id", styles["table_header"]),
            P("게시일", styles["table_header"]),
            P("제목", styles["table_header"]),
            P("사용 규칙", styles["table_header"]),
            P("역할", styles["table_header"]),
        ]
    ]
    for article_id in sorted(source_to_rules):
        article = archive[article_id]
        rows.append(
            [
                source_link(article, styles),
                P(article["posted_at"], styles["table"]),
                P(article["title"], styles["table"]),
                P(", ".join(sorted(source_to_rules[article_id])), styles["table"]),
                P(", ".join(sorted(source_to_roles[article_id])), styles["muted"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[35 * mm, 25 * mm, 55 * mm, 27 * mm, 27 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def latest_rows_table(
    archive: dict[int, dict[str, Any]], styles: dict[str, ParagraphStyle]
) -> Table:
    latest_ids = [173477, 173478, 173479, 173480, 173506, 173507, 173508]
    rows = [
        [
            P("article_id", styles["table_header"]),
            P("게시 시각", styles["table_header"]),
            P("제목", styles["table_header"]),
            P("PDF 반영 방식", styles["table_header"]),
        ]
    ]
    for article_id in latest_ids:
        article = archive[article_id]
        mode = (
            "핵심 규칙 근거(R01)"
            if article_id == 173480
            else "최신성·주제 검토, 직접 규칙 미채택"
        )
        rows.append(
            [
                rich(
                    f'<link href="{esc(article["url"])}" color="#0E7C7B">'
                    f'article_id {article_id}</link>',
                    styles["table"],
                ),
                P(article["posted_at"], styles["table"]),
                P(article["title"], styles["table"]),
                P(mode, styles["table"]),
            ]
        )
    table = Table(rows, colWidths=[35 * mm, 32 * mm, 66 * mm, 36 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_story(
    package: dict[str, Any],
    archive: dict[int, dict[str, Any]],
    qa: dict[str, Any],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = []

    # Cover
    story.extend(
        [
            Spacer(1, 29 * mm),
            P("AI-MONEYINGBOT · RAG EVIDENCE EDITION", styles["cover_kicker"]),
            P(package["title"], styles["cover_title"]),
            P(package["subtitle"], styles["cover_subtitle"]),
            HRFlowable(width=75 * mm, thickness=3, color=TEAL, spaceAfter=16),
            callout(
                "이 판의 목적",
                "요약을 다시 요약하는 책이 아니라, 선생님의 원문 근거(article_id)를 "
                "조건·행동·무효화·예외·데이터 요구사항으로 분해한 트레이딩봇 연구 명세입니다.",
                styles,
                background=TEAL_LIGHT,
                accent=TEAL,
            ),
            Spacer(1, 16),
            metric_cards(
                [
                    (f"{package['current_archive_article_count']:,}", "현재 Archive 원문"),
                    (
                        f"+{package['current_archive_article_count'] - package['previous_pdf_article_count']:,}",
                        "기존 PDF 표기 대비 증가",
                    ),
                    (str(len(package["rules"])), "검증 규칙 카드"),
                    (
                        str(qa["quote_checks_passed"]),
                        "원문 인용 일치 검사",
                    ),
                ],
                styles,
            ),
            Spacer(1, 20),
            P(
                f"기준 시각  {package['as_of_kst']} KST  ·  최신 article_id {package['latest_article_id']}",
                styles["muted"],
            ),
            Spacer(1, 7),
            callout(
                "중요",
                package["disclaimer"],
                styles,
                background=RED_LIGHT,
                accent=RED,
            ),
            PageBreak(),
        ]
    )

    # Executive summary
    story.extend(section_title("01", "이번 판에서 달라진 것", styles))
    story.append(
        P(
            "기존 113쪽 PDF는 42,979건에서 1,361건을 선별해 가르침을 폭넓게 설명한 교육용 "
            "해설서였다. 새 판은 범위를 줄이는 대신, 트레이딩봇이 검증할 수 있도록 주장과 "
            "구현 가설을 분리하고 모든 채택 근거에 article_id를 붙였다.",
            styles["body"],
        )
    )
    comparison = Table(
        [
            [
                P("항목", styles["table_header"]),
                P("기존 그림해설판", styles["table_header"]),
                P("이번 검증판 v2", styles["table_header"]),
            ],
            [
                P("주요 목적", styles["table_bold"]),
                P("가르침 이해·교육", styles["table"]),
                P("규칙 후보의 원문 충실도·검증 가능성", styles["table"]),
            ],
            [
                P("출처 표기", styles["table_bold"]),
                P("날짜·‘외 N건’ 중심", styles["table"]),
                P("article_id·URL·짧은 원문 인용", styles["table"]),
            ],
            [
                P("숫자 처리", styles["table_bold"]),
                P("설명 속 숫자 혼재", styles["table"]),
                P("직접 발언과 구현 가설을 분리", styles["table"]),
            ],
            [
                P("예외·반례", styles["table_bold"]),
                P("주제별 서술에 분산", styles["table"]),
                P("각 규칙 카드에 의무 기재", styles["table"]),
            ],
            [
                P("성과 주장", styles["table_bold"]),
                P("매매법 참고 자료", styles["table"]),
                P("전부 ‘검증 전 가설’; 백테스트 결과 없음", styles["table"]),
            ],
        ],
        colWidths=[34 * mm, 62 * mm, 73 * mm],
    )
    comparison.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (0, -1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            Spacer(1, 5),
            comparison,
            Spacer(1, 10),
            callout(
                "핵심 결론",
                "선생님의 가르침은 단일 ‘매수 공식’보다 시장 레짐 → 비중 → 진입 방식 → "
                "손절/익절의 계층 구조에 가깝다. 트레이딩봇은 신호 하나를 찾기보다 이 위험관리 "
                "계층을 먼저 재현해야 한다.",
                styles,
                background=TEAL_LIGHT,
                accent=TEAL,
            ),
            PageBreak(),
        ]
    )

    # Provenance
    story.extend(section_title("02", "데이터 계보와 최신성", styles))
    story.append(
        P(
            "데스크톱 Archive DB는 43,506건까지 보유하고 있었다. 미니PC 운영 DB를 "
            "SQLite mode=ro + query_only로 열고, 그 이후 article_id 283건을 JSONL로만 "
            "스트리밍했다. 두 집합의 article_id 중복은 0건이며 합집합은 현재 운영 원문 "
            "43,789건과 일치한다.",
            styles["body"],
        )
    )
    pipeline = Table(
        [
            [
                P("기존 PDF", styles["table_header"]),
                P("→", styles["table_header"]),
                P("데스크톱 Archive", styles["table_header"]),
                P("+", styles["table_header"]),
                P("미니PC 읽기전용 JSONL", styles["table_header"]),
                P("=", styles["table_header"]),
                P("검증판 입력", styles["table_header"]),
            ],
            [
                P("42,979건 표기", styles["table"]),
                P("", styles["table"]),
                P("43,506건", styles["table"]),
                P("", styles["table"]),
                P("283건", styles["table"]),
                P("", styles["table"]),
                P("43,789건", styles["table"]),
            ],
        ],
        colWidths=[27 * mm, 8 * mm, 32 * mm, 7 * mm, 38 * mm, 7 * mm, 36 * mm],
    )
    pipeline.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, 1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            pipeline,
            Spacer(1, 10),
            P("RAG 인덱스 상태", styles["h2"]),
            P(
                "점검 시 Qdrant/manifest는 50,957청크였고 Archive 기준 dry-run은 50,969청크였다. "
                "즉 최신 7개 글, 12청크가 정규 증분색인 전이었다. 이번 판은 그 7개 글을 semantic "
                "검색 결과인 것처럼 다루지 않고 Archive 원문에서 직접 읽어 검증했다.",
                styles["body"],
            ),
            callout(
                "소유권 경계 준수",
                "Archive DB에는 읽기만 수행했다. 미니PC DB·Qdrant·manifest·스케줄·시크릿·"
                "운영 체크아웃을 변경하지 않았고, 산출물은 RAG 전용 개발 브랜치에만 작성했다.",
                styles,
                background=BLUE_LIGHT,
                accent=NAVY_2,
            ),
            Spacer(1, 10),
            P("가장 최근 수집된 7개 글", styles["h2"]),
            latest_rows_table(archive, styles),
            PageBreak(),
        ]
    )

    # Method
    story.extend(section_title("03", "채택 기준과 읽는 법", styles))
    story.append(
        P(
            "짧은 본문이 많은 Archive 특성상 한 글을 곧바로 한 규칙으로 만들지 않았다. "
            "직접 발언, 보조 근거, 금지문, 문맥 제한, 숫자 충돌을 묶고 최소 한 개 이상의 "
            "예외를 기록했다.",
            styles["body"],
        )
    )
    method_rows = [
        [
            P("1. 후보 회수", styles["table_bold"]),
            P("기존 PDF·기존 R1~R6·전체 원문 키워드·신규 810건 후보를 넓게 탐색", styles["table"]),
        ],
        [
            P("2. 원문 대조", styles["table_bold"]),
            P("article_id로 Archive 원문을 다시 열어 인용문 존재를 자동 검사", styles["table"]),
        ],
        [
            P("3. 충돌 보존", styles["table_bold"]),
            P("3~5%, 10~15%처럼 범위가 다르면 평균내지 않고 조건 분기로 남김", styles["table"]),
        ],
        [
            P("4. 가설 분리", styles["table_bold"]),
            P("선생님 직접 발언과 구현자가 정해야 할 임계치·프록시를 별도 칸에 기록", styles["table"]),
        ],
        [
            P("5. 자동화 등급", styles["table_bold"]),
            P("A=데이터로 구현 가능, B=정의/검증 필요, C=현재 데이터로 자동화 불가", styles["table"]),
        ],
    ]
    method = Table(method_rows, colWidths=[35 * mm, 134 * mm])
    method.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            method,
            Spacer(1, 11),
            callout(
                "숫자를 읽는 원칙",
                "원문에 숫자가 있어도 곧바로 최적값은 아니다. 20% 비중, 3~4% 손절, "
                "30% 익절, 거래량 1.3배는 ‘검증할 후보값’이며 시장·종목·비용 조건에서 "
                "다시 시험해야 한다.",
                styles,
                background=ORANGE_LIGHT,
                accent=ORANGE,
            ),
            PageBreak(),
        ]
    )

    # Landscape
    story.extend(section_title("04", "12개 규칙 지도", styles))
    story.append(landscape_table(package["rules"], styles))
    story.extend(
        [
            Spacer(1, 8),
            grade_chart(qa["automation_grade_counts"], styles),
            callout(
                "권장 우선순위",
                "먼저 A등급의 비중·분할·추격 태그·손절 구조를 검증하고, 다음으로 B등급의 "
                "무릎·눌림·장대양봉·거래량 정의를 좁힌다. C등급 어깨·호가는 데이터와 라벨 "
                "설계가 끝나기 전 trading-bot에 넣지 않는다.",
                styles,
                background=TEAL_LIGHT,
                accent=TEAL,
            ),
            PageBreak(),
        ]
    )

    # Rule cards
    for index, rule in enumerate(package["rules"], start=1):
        story.extend(section_title(f"{index + 4:02d}", rule["name"], styles))
        story.extend(rule_card(rule, archive, styles))
        story.append(PageBreak())

    # Decision flow
    story.extend(section_title("17", "규칙을 한 전략으로 연결하는 순서", styles))
    flow_rows = [
        [
            P("1 시장", styles["table_header"]),
            P("2 진입 자격", styles["table_header"]),
            P("3 주문/비중", styles["table_header"]),
            P("4 보유 관리", styles["table_header"]),
            P("5 청산", styles["table_header"]),
        ],
        [
            P("R01 불확실성<br/>R02 레짐", styles["table"]),
            P("R04 반전<br/>R05 눌림<br/>R06 추격 제한", styles["table"]),
            P("R03 분할매수<br/>총노출 상한", styles["table"]),
            P("R07 손절<br/>R12 호가(보류)", styles["table"]),
            P("R08 장대양봉<br/>R09 분할익절<br/>R10 어깨<br/>R11 거래량", styles["table"]),
        ],
    ]
    flow = Table(flow_rows, colWidths=[34 * mm] * 5)
    flow.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, 1), TEAL_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.7, WHITE),
                ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.extend(
        [
            flow,
            Spacer(1, 12),
            P("상태 전이의 핵심", styles["h2"]),
            bullets(
                [
                    "시장 게이트가 닫히면 종목 셋업이 좋아도 신규 진입하지 않는다.",
                    "모든 진입은 ‘왜 샀는지’ 태그를 만들고, 태그가 손절·보유시간·익절법을 결정한다.",
                    "분할매수는 동일한 진입 논리가 여전히 유효할 때만 다음 단계로 이동한다.",
                    "재매수는 이전 포지션의 복구가 아니라 새 셋업으로 평가한다.",
                    "C등급 규칙은 사람의 감각을 숫자로 가장하지 않고 연구 큐에 둔다.",
                ],
                styles,
            ),
            Spacer(1, 7),
            callout(
                "봇 설계 원칙",
                "신호 생성기보다 먼저 RegimeGate, ExposureManager, ThesisTag, "
                "PositionState, ExitPolicy를 분리한다. 그래야 규칙 충돌과 숫자 출처를 추적할 수 있다.",
                styles,
                background=BLUE_LIGHT,
                accent=NAVY_2,
            ),
            PageBreak(),
        ]
    )

    # Validation
    story.extend(section_title("18", "검증 프로토콜", styles))
    validation_rows = [
        [
            P("게이트", styles["table_header"]),
            P("통과 조건", styles["table_header"]),
            P("실패 시", styles["table_header"]),
        ],
        [
            P("V0 출처", styles["table_bold"]),
            P("article_id 존재, 인용문 원문 일치, 직접 발언/가설 분리", styles["table"]),
            P("규칙 후보 폐기 또는 보완", styles["table"]),
        ],
        [
            P("V1 데이터", styles["table_bold"]),
            P("생존편향·수정주가·거래정지·가격제한폭·수수료 정의", styles["table"]),
            P("백테스트 금지", styles["table"]),
        ],
        [
            P("V2 구현", styles["table_bold"]),
            P("룩어헤드 없음, 결정 시각과 체결 시각 분리, 단위테스트", styles["table"]),
            P("코드 수정 후 재검증", styles["table"]),
        ],
        [
            P("V3 연구", styles["table_bold"]),
            P("워크포워드·기간 분할·기준전략 대비·비용 포함", styles["table"]),
            P("임계치 단순화 또는 폐기", styles["table"]),
        ],
        [
            P("V4 운영 전", styles["table_bold"]),
            P("모의투자, 최대손실·체결오차·장애 시나리오 확인", styles["table"]),
            P("trading-bot 전달 금지", styles["table"]),
        ],
    ]
    validation_table = Table(validation_rows, colWidths=[25 * mm, 100 * mm, 44 * mm])
    validation_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (0, -1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            validation_table,
            Spacer(1, 12),
            P("필수 보고 지표", styles["h2"]),
            bullets(
                [
                    "연환산 수익률만이 아니라 최대낙폭, 회복기간, 회전율, 거래당 기대값, 꼬리손실",
                    "수수료·세금·슬리피지·호가 공백을 반영한 순성과",
                    "전체 성과와 레짐별·연도별·종목군별 성과의 일관성",
                    "임계치 주변 민감도와 단순 기준전략 대비 개선폭",
                    "학습·튜닝에 쓰지 않은 최종 홀드아웃과 모의투자 결과",
                ],
                styles,
            ),
            callout(
                "금지",
                "백테스트 전 ‘수익 전략’, 동일 표본 튜닝 후 ‘검증 완료’, 거래비용 없는 "
                "성과, C등급 감각 규칙의 임의 수치화는 모두 금지한다.",
                styles,
                background=RED_LIGHT,
                accent=RED,
            ),
            PageBreak(),
        ]
    )

    # Backlog
    story.extend(section_title("19", "권장 연구 백로그", styles))
    backlog = [
        ("1", "GM-R01 + R03 + R07", "시장 게이트·분할진입·손절을 최소 위험관리 베이스라인으로 구현"),
        ("2", "GM-R08 + R09", "장대양봉 방어선과 분할익절을 독립 변수로 검증"),
        ("3", "GM-R04 + R05", "무릎·눌림 정의를 여러 후보로 사전 등록하고 룩어헤드 제거"),
        ("4", "GM-R11", "가격 위치×거래량 배수의 조건부 효과 검증"),
        ("5", "GM-R10", "‘숨고르기/추세훼손’ 프록시 연구; 성급한 자동화 금지"),
        ("6", "GM-R12", "10호가·틱 데이터 확보 여부 판단 후 별도 미시구조 연구"),
    ]
    backlog_rows = [
        [
            P("순서", styles["table_header"]),
            P("대상", styles["table_header"]),
            P("완료 정의", styles["table_header"]),
        ]
    ] + [
        [P(order, styles["table_bold"]), P(target, styles["table"]), P(done, styles["table"])]
        for order, target, done in backlog
    ]
    backlog_table = Table(backlog_rows, colWidths=[18 * mm, 43 * mm, 108 * mm])
    backlog_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            backlog_table,
            Spacer(1, 12),
            callout(
                "trading-bot 경계",
                "이 문서는 RAG 소유의 reviewer-facing 연구 산출물이다. trading-bot 상태나 "
                "데이터를 읽거나 쓰지 않았으며, 전달은 승인된 API/JSONL 계약으로만 해야 한다.",
                styles,
                background=BLUE_LIGHT,
                accent=NAVY_2,
            ),
            PageBreak(),
        ]
    )

    # Source index
    story.extend(section_title("20", "근거 article_id 색인", styles))
    story.append(
        P(
            "표의 article_id 링크는 Archive 원문 URL을 가리킨다. 제목은 중복이 많으므로 "
            "출처 식별은 article_id와 URL을 기준으로 한다.",
            styles["body"],
        )
    )
    story.append(source_index_table(package, archive, styles))
    story.append(PageBreak())

    # Limitations
    story.extend(section_title("21", "한계와 다음 판의 조건", styles))
    story.append(
        bullets(
            [
                "이번 판은 대표 규칙 12개를 깊게 구조화한 것이며 Archive의 모든 가르침을 포괄하지 않는다.",
                "Archive 글은 짧은 글과 연속 게시가 많다. 인접 article_id만으로 문맥을 자동 결합하지 않았다.",
                "일부 posted_at은 시간만 있어 게시일 계보의 신뢰도가 낮다. article_id와 URL을 정본키로 사용했다.",
                "직접 인용은 공백 정규화 후 원문 포함 여부를 검사했지만, 발언의 시장 당시성까지 제거해 주지는 않는다.",
                "백테스트·포워드 결과가 없으므로 어떤 규칙도 수익성이 검증됐다고 말할 수 없다.",
                "RAG 최신 12청크는 점검 당시 미색인이어서 최신 글은 semantic retrieval이 아니라 Archive 원문 직접검토로 반영했다.",
            ],
            styles,
        )
    )
    story.extend(
        [
            Spacer(1, 9),
            callout(
                "다음 판 승격 조건",
                "각 규칙별 gold 질문셋 → retrieve+rereank 재현 → 원문 검토 → 백테스트 사전등록 → "
                "워크포워드 → 모의투자까지 통과한 규칙만 ‘검증 중/검증 완료’ 상태로 승격한다.",
                styles,
                background=TEAL_LIGHT,
                accent=TEAL,
            ),
            Spacer(1, 14),
            P("제작 검증 기록", styles["h2"]),
            metric_cards(
                [
                    (str(qa["rule_count"]), "규칙 스키마 통과"),
                    (str(qa["source_article_count"]), "고유 근거 글"),
                    (str(qa["quote_checks_passed"]), "인용문 일치"),
                    ("0", "DB 쓰기·운영 변경"),
                ],
                styles,
            ),
            Spacer(1, 12),
            P(
                f"생성 시각: {datetime.now().astimezone().isoformat(timespec='seconds')} · "
                "생성기: scripts/build_rag_rulebook_pdf_v2.py",
                styles["muted"],
            ),
        ]
    )
    return story


def enriched_rule_rows(
    package: dict[str, Any], archive: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule in package["rules"]:
        enriched = dict(rule)
        enriched["status"] = "research_hypothesis_unvalidated"
        enriched["sources"] = []
        for source in rule["sources"]:
            article = archive[int(source["article_id"])]
            enriched["sources"].append(
                {
                    **source,
                    "title": article["title"],
                    "posted_at": article["posted_at"],
                    "url": article["url"],
                    "provenance": article["provenance"],
                }
            )
        rows.append(enriched)
    return rows


def write_outputs(
    output_path: Path,
    package: dict[str, Any],
    archive: dict[int, dict[str, Any]],
    qa: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stem = output_path.stem
    jsonl_path = output_path.with_name(f"{stem}_rules.jsonl")
    qa_path = output_path.with_name(f"{stem}_QA.json")
    md_path = output_path.with_name(f"{stem}_README.md")

    rows = enriched_rule_rows(package, archive)
    jsonl_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    qa_path.write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(
        "\n".join(
            [
                f"# {package['title']}",
                "",
                f"- 기준 시각: {package['as_of_kst']} KST",
                f"- Archive 합집합: {qa['archive']['union_count']:,}건",
                f"- 규칙: {qa['rule_count']}개",
                f"- 고유 근거 글: {qa['source_article_count']}개",
                f"- 원문 인용 일치 검사: {qa['quote_checks_passed']}건 통과",
                "- 상태: 모든 규칙은 백테스트 전 연구 가설",
                "- 운영 변경: 없음",
                "",
                "PDF는 설명용 산출물이고, `_rules.jsonl`이 후속 검토·자동화 입력용 구조화 정본입니다.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    package = json.loads(args.rules_path.read_text(encoding="utf-8"))
    archive, stats = load_archive_union(args.db_path, args.delta_path)
    qa = validate_rules(package, archive, stats)
    print(
        json.dumps(
            {
                "validation": "passed",
                "rule_count": qa["rule_count"],
                "source_article_count": qa["source_article_count"],
                "quote_checks_passed": qa["quote_checks_passed"],
                "archive_union_count": stats["union_count"],
                "archive_max_article_id": stats["max_article_id"],
                "query_only": stats["query_only"],
            },
            ensure_ascii=False,
        )
    )
    if args.check_only:
        return 0

    register_fonts()
    styles = make_styles()
    story = build_story(package, archive, qa, styles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = RulebookDocTemplate(
        str(args.output),
        package,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=19 * mm,
        bottomMargin=18 * mm,
        title=package["title"],
        author="ai-moneyingbot RAG research",
    )
    doc.build(story)
    write_outputs(args.output, package, archive, qa)
    print(
        json.dumps(
            {
                "pdf": str(args.output),
                "pdf_bytes": args.output.stat().st_size,
                "rules_jsonl": str(
                    args.output.with_name(f"{args.output.stem}_rules.jsonl")
                ),
                "qa_json": str(args.output.with_name(f"{args.output.stem}_QA.json")),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
