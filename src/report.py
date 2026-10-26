"""Load demo Instagram post metrics, store them in SQLite, and render a PDF."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from src.ai_analyzer import AnalysisAPIError, InputValidationError, analyze_post


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "mock_posts.json"
DEFAULT_DB = ROOT / "data" / "reporting.sqlite3"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "biweekly_report.pdf"

INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#65718A")
PURPLE = colors.HexColor("#6547D5")
PALE = colors.HexColor("#F5F3FC")
LINE = colors.HexColor("#E5E8EF")
GREEN = colors.HexColor("#16805D")
RED = colors.HexColor("#C34444")


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    def label(self) -> str:
        return f"{self.start:%b %d} - {self.end:%b %d, %Y}"


def get_windows(as_of: date) -> tuple[Window, Window]:
    """Return two completed, adjacent 14-day windows before as_of."""
    current = Window(as_of - timedelta(days=14), as_of - timedelta(days=1))
    previous = Window(as_of - timedelta(days=28), as_of - timedelta(days=15))
    return current, previous


def load_demo_posts(path: Path, as_of: date) -> list[dict[str, Any]]:
    """Materialize relative-day demo records for the requested reporting date."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    posts: list[dict[str, Any]] = []
    for item in raw:
        days_ago = int(item["days_ago"])
        if days_ago < 1:
            raise ValueError(f"days_ago must be at least 1 for post {item.get('id')}")
        posts.append(
            {
                "post_id": str(item["id"]),
                "published_at": (as_of - timedelta(days=days_ago)).isoformat(),
                "post_type": str(item["type"]).upper(),
                "caption": str(item["caption"]),
                "reach": int(item["reach"]),
                "likes": int(item["likes"]),
                "comments": int(item["comments"]),
                "shares": int(item["shares"]),
                "saves": int(item["saves"]),
                "source": "SIMULATED DEMO DATA",
            }
        )
    return posts


def save_posts(db_path: Path, posts: list[dict[str, Any]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                published_at TEXT NOT NULL,
                post_type TEXT NOT NULL,
                caption TEXT NOT NULL,
                reach INTEGER NOT NULL CHECK (reach >= 0),
                likes INTEGER NOT NULL CHECK (likes >= 0),
                comments INTEGER NOT NULL CHECK (comments >= 0),
                shares INTEGER NOT NULL CHECK (shares >= 0),
                saves INTEGER NOT NULL CHECK (saves >= 0),
                source TEXT NOT NULL,
                collected_at TEXT NOT NULL
            )"""
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        connection.executemany(
            """INSERT INTO posts
                (post_id, published_at, post_type, caption, reach, likes,
                 comments, shares, saves, source, collected_at)
                VALUES (:post_id, :published_at, :post_type, :caption, :reach,
                        :likes, :comments, :shares, :saves, :source, :collected_at)
                ON CONFLICT(post_id) DO UPDATE SET
                    published_at=excluded.published_at,
                    post_type=excluded.post_type,
                    caption=excluded.caption,
                    reach=excluded.reach,
                    likes=excluded.likes,
                    comments=excluded.comments,
                    shares=excluded.shares,
                    saves=excluded.saves,
                    source=excluded.source,
                    collected_at=excluded.collected_at""",
            [{**post, "collected_at": now} for post in posts],
        )


def interactions(post: dict[str, Any]) -> int:
    return sum(int(post[key]) for key in ("likes", "comments", "shares", "saves"))


def engagement_rate(post: dict[str, Any]) -> float:
    reach = int(post["reach"])
    return interactions(post) / reach * 100 if reach else 0.0


def rows_for_window(db_path: Path, window: Window) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT post_id, published_at, post_type, caption, reach,
                      likes, comments, shares, saves, source
               FROM posts WHERE published_at BETWEEN ? AND ?
               ORDER BY published_at DESC""",
            (window.start.isoformat(), window.end.isoformat()),
        ).fetchall()
    return [dict(row) for row in rows]


def summarize(posts: list[dict[str, Any]]) -> dict[str, Any]:
    reach = sum(post["reach"] for post in posts)
    total_interactions = sum(interactions(post) for post in posts)
    return {
        "posts": len(posts),
        "reach": reach,
        "interactions": total_interactions,
        "engagement_rate": total_interactions / reach * 100 if reach else 0.0,
    }


def change_label(current: float, previous: float, *, percentage_points: bool = False) -> tuple[str, colors.Color]:
    if percentage_points:
        delta = current - previous
        return f"{delta:+.2f} pp", GREEN if delta >= 0 else RED
    if previous == 0:
        return ("new" if current else "0%"), (GREEN if current else MUTED)
    delta = (current - previous) / previous * 100
    return f"{delta:+.1f}%", GREEN if delta >= 0 else RED


def truncate(text: str, max_width: float, font: str, size: float) -> str:
    text = " ".join(text.split())
    while text and stringWidth(text, font, size) > max_width:
        text = text[:-2].rstrip() + "…"
    return text


def wrap_text(text: str, max_width: float, font: str, size: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def generate_top_post_ideas(posts: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Get local AI suggestions for the top-engagement post, without blocking the report."""
    if not posts:
        return None, "No current-period posts are available for AI suggestions."

    top_post = max(posts, key=lambda post: (engagement_rate(post), post["reach"]))
    payload = {
        "caption": top_post["caption"],
        "post_type": top_post["post_type"],
        "metrics": {key: int(top_post[key]) for key in ("reach", "likes", "comments", "shares", "saves")},
    }
    try:
        return analyze_post(payload), None
    except (AnalysisAPIError, InputValidationError, OSError) as exc:
        return None, str(exc)


def draw_report(
    output_path: Path,
    current_window: Window,
    previous_window: Window,
    current_posts: list[dict[str, Any]],
    previous_posts: list[dict[str, Any]],
    generated_on: date,
    ai_result: dict[str, Any] | None = None,
    ai_error: str | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    current = summarize(current_posts)
    previous = summarize(previous_posts)
    page_w, page_h = A4
    margin = 42
    usable = page_w - 2 * margin
    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    pdf.setTitle("Bi-weekly Social Media Performance Report - Demo")

    # Header
    pdf.setFillColor(PURPLE)
    pdf.roundRect(margin, page_h - 72, 125, 19, 9, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(margin + 62.5, page_h - 65.5, "SIMULATED DATA | DEMO ONLY")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(margin, page_h - 111, "Meme Page Performance")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, page_h - 130, "Instagram bi-weekly report  |  Generated " + generated_on.strftime("%b %d, %Y"))

    # Current period and comparison summary
    top = page_h - 164
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin, top, "Reporting period")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(page_w - margin, top, current_window.label())

    card_gap = 10
    card_w = (usable - 2 * card_gap) / 3
    card_y = top - 78
    kpis = [
        ("TOTAL REACH", f"{current['reach']:,}", "vs previous", change_label(current["reach"], previous["reach"])),
        ("INTERACTIONS", f"{current['interactions']:,}", "vs previous", change_label(current["interactions"], previous["interactions"])),
        ("ENGAGEMENT RATE", f"{current['engagement_rate']:.2f}%", "vs previous", change_label(current["engagement_rate"], previous["engagement_rate"], percentage_points=True)),
    ]
    for index, (label, value, sublabel, change) in enumerate(kpis):
        x = margin + index * (card_w + card_gap)
        pdf.setFillColor(PALE)
        pdf.roundRect(x, card_y, card_w, 65, 8, fill=1, stroke=0)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(x + 12, card_y + 48, label)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(x + 12, card_y + 24, value)
        pdf.setFillColor(change[1])
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawRightString(x + card_w - 12, card_y + 12, change[0])

    # Period table
    table_top = card_y - 28
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, table_top, "Period comparison")
    col_x = [margin, margin + usable * 0.48, margin + usable * 0.72]
    headers = [(col_x[0], "METRIC"), (col_x[1], "CURRENT"), (col_x[2], "PREVIOUS")]
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 8)
    for x, label in headers:
        pdf.drawString(x, table_top - 18, label)
    pdf.drawRightString(page_w - margin, table_top - 18, "CHANGE")
    pdf.setStrokeColor(LINE)
    pdf.line(margin, table_top - 24, page_w - margin, table_top - 24)
    table_rows = [
        ("Posts published", str(current["posts"]), str(previous["posts"]), change_label(current["posts"], previous["posts"])),
        ("Total reach", f"{current['reach']:,}", f"{previous['reach']:,}", change_label(current["reach"], previous["reach"])),
        ("Interactions", f"{current['interactions']:,}", f"{previous['interactions']:,}", change_label(current["interactions"], previous["interactions"])),
        ("Engagement rate", f"{current['engagement_rate']:.2f}%", f"{previous['engagement_rate']:.2f}%", change_label(current["engagement_rate"], previous["engagement_rate"], percentage_points=True)),
    ]
    y = table_top - 43
    for metric, current_v, previous_v, change in table_rows:
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(col_x[0], y, metric)
        pdf.drawString(col_x[1], y, current_v)
        pdf.drawString(col_x[2], y, previous_v)
        pdf.setFillColor(change[1])
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawRightString(page_w - margin, y, change[0])
        y -= 20

    # Top posts
    section_y = y - 12
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, section_y, "Top 3 posts this period")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, section_y - 14, "Ranked by post engagement rate: interactions / reach")
    columns = [margin, margin + 27, margin + 290, margin + 367, margin + 430]
    headers = [(columns[0], "#"), (columns[1], "POST / DATE"), (columns[2], "TYPE"), (columns[3], "REACH"), (columns[4], "ENG. RATE")]
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 7)
    for x, label in headers:
        pdf.drawString(x, section_y - 33, label)
    pdf.setStrokeColor(LINE)
    pdf.line(margin, section_y - 39, page_w - margin, section_y - 39)

    ranked = sorted(current_posts, key=lambda post: (engagement_rate(post), post["reach"]), reverse=True)[:3]
    row_y = section_y - 57
    for rank, post in enumerate(ranked, 1):
        pdf.setFillColor(PURPLE)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(columns[0], row_y, str(rank))
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(columns[1], row_y + 2, truncate(post["caption"], 250, "Helvetica-Bold", 8.5))
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(columns[1], row_y - 11, date.fromisoformat(post["published_at"]).strftime("%b %d"))
        pdf.drawString(columns[2], row_y, post["post_type"].replace("_ALBUM", ""))
        pdf.drawString(columns[3], row_y, f"{post['reach']:,}")
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(columns[4], row_y, f"{engagement_rate(post):.2f}%")
        pdf.setStrokeColor(LINE)
        pdf.line(margin, row_y - 19, page_w - margin, row_y - 19)
        row_y -= 42

    # Local AI suggestions for the top post
    ai_y = max(margin + 82, row_y - 3)
    hashtag_lines = (
        wrap_text("Hashtags: " + " ".join(ai_result["hashtags"]), usable - 20, "Helvetica", 7.5)
        if ai_result
        else []
    )
    panel_bottom = ai_y - (48 + 10 * max(1, len(hashtag_lines)))
    pdf.setFillColor(PALE)
    pdf.roundRect(margin, panel_bottom, usable, ai_y + 14 - panel_bottom, 7, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin + 10, ai_y, "LOCAL AI IDEAS FOR TOP POST")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    if ai_result:
        pdf.drawString(
            margin + 10,
            ai_y - 14,
            truncate(ai_result["performance_summary"], usable - 20, "Helvetica", 7.5),
        )
        pdf.drawString(
            margin + 10,
            ai_y - 28,
            truncate("1. " + ai_result["caption_options"][0], usable - 20, "Helvetica", 7.5),
        )
        pdf.drawString(
            margin + 10,
            ai_y - 40,
            truncate("2. " + ai_result["caption_options"][1], usable - 20, "Helvetica", 7.5),
        )
        for line_no, line in enumerate(hashtag_lines):
            pdf.drawString(margin + 10, ai_y - 52 - line_no * 10, line)
    else:
        status = ai_error or "Start Ollama to generate suggestions."
        pdf.drawString(margin + 10, ai_y - 20, truncate("Suggestions unavailable: " + status, usable - 20, "Helvetica", 7.5))

    # Previous-window note and metric definition
    note_y = margin + 22
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, note_y + 14, f"Previous period: {previous_window.label()}")
    pdf.drawString(margin, note_y, "Engagement rate = (likes + comments + shares + saves) / reach. Period rate uses total interactions / total reach.")
    pdf.setStrokeColor(LINE)
    pdf.line(margin, note_y + 29, page_w - margin, note_y + 29)

    pdf.showPage()
    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a bi-weekly Instagram demo report.")
    parser.add_argument("--as-of", help="Date used as the exclusive end of the report window (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to the relative-day demo JSON fixture.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    current_window, previous_window = get_windows(as_of)
    posts = load_demo_posts(args.data, as_of)
    save_posts(args.database, posts)
    current_posts = rows_for_window(args.database, current_window)
    previous_posts = rows_for_window(args.database, previous_window)
    ai_result, ai_error = generate_top_post_ideas(current_posts)
    draw_report(
        args.output,
        current_window,
        previous_window,
        current_posts,
        previous_posts,
        as_of,
        ai_result=ai_result,
        ai_error=ai_error,
    )
    print(f"Demo posts stored: {len(posts)}")
    print(f"Current period: {current_window.label()} ({len(current_posts)} posts)")
    print(f"Previous period: {previous_window.label()} ({len(previous_posts)} posts)")
    if ai_result:
        print("Local AI ideas: added for the top post")
    else:
        print(f"Local AI ideas unavailable: {ai_error}")
    print(f"Report created: {args.output.resolve()}")


if __name__ == "__main__":
    main()
