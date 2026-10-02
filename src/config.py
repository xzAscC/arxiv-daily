import argparse


def config():
    """
    Configure the recommender system.
    """
    parser = argparse.ArgumentParser(description='Recommender system for academic papers')

    parser.add_argument('--interests', type=str, help='File of research interests grouped by "## <name>" headers', default='interests.txt')
    parser.add_argument('--send_empty', action=argparse.BooleanOptionalAction, help='Send an email even if no paper is recommended (e.g. weekends)', default=False)
    parser.add_argument('--max_paper_num', type=int, help='Maximum number of papers to recommend, -1 for no limit', default=10)
    parser.add_argument('--arxiv_query', type=str, help='Arxiv search query', default='cs.AI+cs.CL+cs.LG+stat.ML')
    parser.add_argument('--embedding_model', type=str, help='Sentence-transformers model used for the first-stage ranking', default='Qwen/Qwen3-Embedding-0.6B')
    parser.add_argument('--review_num', type=int, help='Number of top-ranked papers sent to the LLM review, 0 to skip the review', default=60)
    parser.add_argument('--review_backend', type=str, choices=['pi', 'claude'], help='CLI used to call the review LLM', default='pi')
    parser.add_argument('--review_model', type=str, help='Model used to review the papers, e.g. zai/glm-5.3 for pi or sonnet for claude', default='zai/glm-5.3')
    parser.add_argument('--min_quality', type=float, help='Minimum LLM quality score (0-10) to recommend a paper', default=5)
    parser.add_argument('--min_relevance', type=float, help='Minimum LLM relevance score (0-10) to recommend a paper', default=4)
    parser.add_argument('--smtp_server', type=str, help='SMTP server', default='smtp.gmail.com')
    parser.add_argument('--smtp_port', type=int, help='SMTP port', default=587)
    parser.add_argument('--dry_run', action='store_true', help='Write the email to logs/preview.html instead of sending it', default=False)
    parser.add_argument('--debug', action='store_true', help='Debug mode', default=False)

    args = parser.parse_args()
    return args
