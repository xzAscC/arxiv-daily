import datetime
import json
import os
import sys
import traceback
from pathlib import Path

# Progress bars turn into "[blob data]" in the systemd journal
if not sys.stderr.isatty():
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from dotenv import load_dotenv

from logger import setup_logger
from config import config
from paper import load_interests, get_arxiv_paper, rerank_paper
from review import review_papers, select_papers
from resources import attach_resources
from construct_email import render_email, render_error, send_email

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
SENDER = os.getenv("SENDER")
RECEIVER = os.getenv("RECEIVER")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
HISTORY = ROOT / "cache/sent.json"
HISTORY_DAYS = 60


def load_history() -> dict[str, str]:
    """arXiv IDs already recommended, mapped to the date they were sent."""
    if not HISTORY.exists():
        return {}
    cutoff = (datetime.date.today() - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    return {k: v for k, v in json.loads(HISTORY.read_text()).items() if v >= cutoff}


def save_history(history: dict[str, str]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(history, indent=1))


def run(args, logger) -> None:
    interests_path = Path(args.interests)
    if not interests_path.is_absolute():
        interests_path = ROOT / interests_path
    logger.info(f"Loading interests from {interests_path}...")
    interests = load_interests(interests_path)
    logger.info(f"Loaded {len(interests)} interest groups: {', '.join(interests)}.")

    logger.info("Retrieving Arxiv papers...")
    papers = get_arxiv_paper(args.arxiv_query, args.debug)
    history = load_history()
    if not args.debug:
        # Skip papers sent before, e.g. when the RSS feed has not been refreshed yet
        sent_before = sum(p.arxiv_id in history for p in papers)
        papers = [p for p in papers if p.arxiv_id not in history]
        if sent_before:
            logger.info(f"Skipped {sent_before} papers that were already recommended.")
    n_total = len(papers)
    top_k = len(papers) if args.max_paper_num == -1 else args.max_paper_num
    stats = f"{n_total} new papers in {args.arxiv_query.replace('+', ', ')}"

    if n_total == 0:
        logger.info(
            "No new papers found. Yesterday maybe a holiday and no one submit their work :). If this is not the case, please check the ARXIV_QUERY."
        )
        if not args.send_empty:
            return
    elif not interests:
        logger.warning("No interests found, keeping the arXiv order.")
        papers = papers[:top_k]
    else:
        logger.info("Ranking papers by embedding similarity...")
        papers = rerank_paper(papers, interests, model=args.embedding_model)
        pool = papers[: args.review_num]
        if args.review_num > 0 and review_papers(pool, interests, args.review_backend, args.review_model):
            papers = select_papers(pool, top_k, args.min_quality, args.min_relevance)
            stats += f" · {len(pool)} reviewed by {args.review_model} · top {len(papers)} shown"
        else:
            papers = papers[:top_k]
            stats += f" · LLM review unavailable, top {len(papers)} by embedding similarity"

        logger.info("Looking up open-source code and models...")
        attach_resources(papers)
        for p in papers:
            code = "code" if p.resources.code else "-"
            logger.info(f"{p.final_score:5.2f}  {code:4}  [{p.interest}] {p.title}")

    if not papers and not args.send_empty:
        logger.info("No paper passed the review, skipping the email.")
        return

    html = render_email(papers, list(interests), stats)
    if args.dry_run:
        preview = ROOT / "logs/preview.html"
        preview.write_text(html, encoding="utf-8")
        logger.success(f"Dry run: email written to {preview}.")
        return

    logger.info("Sending email...")
    today = datetime.date.today().strftime("%Y/%m/%d")
    send_email(
        SENDER, RECEIVER, SENDER_PASSWORD, args.smtp_server, args.smtp_port, html,
        subject=f"arXiv Daily {today} · {len(papers)} papers",
    )
    logger.success(
        "Email sent successfully! If you don't receive the email, please check the configuration and the junk box."
    )
    if not args.debug:
        today = datetime.date.today().isoformat()
        save_history(history | {p.arxiv_id: today for p in papers})


if __name__ == "__main__":
    args = config()
    logger = setup_logger(args.debug, log_file=str(ROOT / "logs/app.log"))
    logger.debug("Debug mode is on.")
    try:
        run(args, logger)
    except Exception:
        logger.exception("arXiv Daily failed.")
        if not args.dry_run:
            # Let the failure show up in the inbox instead of only in the journal
            today = datetime.date.today().strftime("%Y/%m/%d")
            send_email(
                SENDER, RECEIVER, SENDER_PASSWORD, args.smtp_server, args.smtp_port,
                render_error(traceback.format_exc()), subject=f"arXiv Daily {today} · failed",
            )
        sys.exit(1)
