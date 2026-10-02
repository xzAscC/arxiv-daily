# arXiv Daily

Pulls new arXiv papers every day, ranks them against your research interests, has an LLM review their relevance and quality, and emails you the top 10. Originally based on [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily), now without Zotero.

## 🚀 Features

- **Daily arXiv Integration**: Fetches new (and cross-listed) papers from the arXiv RSS feed every day
- **Interest-based Ranking**: Ranks papers with [Qwen3-Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) against the interests in `interests.txt`
- **LLM Quality Review**: The top candidates are reviewed by GLM-5.3 via the local [pi](https://github.com/badlogic/pi-mono) CLI (or Claude via `--review_backend claude`) for relevance and quality; only the best 10 that pass the bar are sent
- **Code & Model Links**: Flags papers with open-source code, Hugging Face models/datasets, or code promised "soon"
- **Robust Daily Runs**: Never recommends a paper twice (`cache/sent.json`), retries the RSS feed, and emails you the traceback if a run fails
- **Readable Email Digest**: Interest tags, scores, a Chinese TL;DR and reason, and links to PDF / arXiv / HTML / alphaXiv

## 📋 Prerequisites

- Python 3.11+, a CUDA GPU is recommended (falls back to CPU)
- `pi` CLI with the `zai` provider logged in (or `claude` CLI for `--review_backend claude`); without it the review step is skipped
- Gmail account (for sending emails)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/xzAscC/arxiv-daily
   cd arxiv-daily
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```bash
   # Email configuration
   SENDER=your-email@gmail.com
   RECEIVER=recipient-email@domain.com
   SENDER_PASSWORD=your-app-password
  
   ```

4. **Describe your interests**
   Edit `interests.txt`: one interest per line, either free text or an arXiv ID of a representative paper.
   Each paper is scored by its best match among these lines.

## 🚀 Usage

### Manual Run
```bash
uv run src/main.py            # send the email
uv run src/main.py --dry_run  # write logs/preview.html instead
uv run pytest                 # offline unit tests
uv run src/main.py --help     # all options (query, top-k, review pool, quality bar, models)
```

## 🏗️ Project Structure

```
arxiv-daily/
├── src/
│   ├── main.py              # Main execution script
│   ├── paper.py             # arXiv fetching and interest-based ranking
│   ├── review.py            # LLM relevance / quality review (pi or claude)
│   ├── construct_email.py   # Email generation and sending
│   ├── config.py            # Configuration management
│   └── logger.py            # Logging utilities
├── interests.txt            # Research interests
├── .env                     # Environment variables
└── README.md               # This file
```

## TODO
- [ ] auto run it in server