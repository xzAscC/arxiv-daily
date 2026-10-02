import argparse

def config():
    """
    Configure the recommender system.
    """
    parser = argparse.ArgumentParser(description='Recommender system for academic papers')

    parser.add_argument('--zotero_ignore',type=str,help='Zotero collection to ignore, using gitignore-style pattern.')
    parser.add_argument('--send_empty', type=bool, help='If get no arxiv paper, send empty email',default=True)
    parser.add_argument('--max_paper_num', type=int, help='Maximum number of papers to recommend, -1 for no limit',default=-1)
    parser.add_argument('--arxiv_query', type=str, help='Arxiv search query',default='cs.AI+cs.CV+cs.LG+cs.CL')
    parser.add_argument('--smtp_server', type=str, help='SMTP server',default='smtp.gmail.com')
    parser.add_argument('--smtp_port', type=int, help='SMTP port',default=587)
    parser.add_argument('--debug', action='store_true', help='Debug mode', default=True)
    
    args = parser.parse_args()
    return args