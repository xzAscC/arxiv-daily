import os
import sys

from dotenv import load_dotenv

from src.logger import setup_logger
from src.config import config
from src.paper import get_zotero_corpus, get_arxiv_paper, rerank_paper
from src.construct_email import render_email, send_email

load_dotenv(override=True)
ZOTERO_ID = os.getenv("ZOTERO_ID")
ZOTERO_KEY = os.getenv("ZOTERO_KEY")
SENDER = os.getenv("SENDER")
RECEIVER = os.getenv("RECEIVER")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

if __name__ == "__main__":

    args = config()
    logger = setup_logger(args.debug)
    if args.debug:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG")
        logger.debug("Debug mode is on.")
    else:
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    logger.info("Retrieving Zotero corpus...")

    corpus = get_zotero_corpus(ZOTERO_ID, ZOTERO_KEY)
    logger.info(f"Retrieved {len(corpus)} papers from Zotero.")

    logger.info("Retrieving Arxiv papers...")
    papers = get_arxiv_paper(args.arxiv_query, args.debug)
    if args.max_paper_num == -1:
        logger.info(f"Retrieved {len(papers)} papers from Arxiv.")
    else:
        logger.info(
            f"Retrieved {max(args.max_paper_num, len(papers))} papers from Arxiv."
        )

    if len(papers) == 0:
        logger.info(
            "No new papers found. Yesterday maybe a holiday and no one submit their work :). If this is not the case, please check the ARXIV_QUERY."
        )
        if not args.send_empty:
            exit(0)
    else:
        logger.info("Reranking papers...")
        papers = rerank_paper(papers, corpus)
        if args.max_paper_num != -1:
            papers = papers[: args.max_paper_num]

    html = render_email(papers)
    logger.info("Sending email...")
    send_email(
        SENDER, RECEIVER, SENDER_PASSWORD, args.smtp_server, args.smtp_port, html
    )
    logger.success(
        "Email sent successfully! If you don't receive the email, please check the configuration and the junk box."
    )
