# Zotero arXiv Daily

A customized version of [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) that pulls arXiv papers daily and sends personalized email digests based on your Zotero library.

## 🚀 Features

- **Daily arXiv Integration**: Fetches new arXiv papers every day
- **Smart Paper Ranking**: Sorts papers based on relevance to your existing Zotero collection
- **Personalized Email Digests**: Sends curated paper recommendations directly to your inbox

## 📋 Prerequisites

- Python 3.10+
- Zotero account with API access
- Gmail account (for sending emails)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/xzAscC/zotero-arxiv-daily
   cd zotero-arxiv-daily
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```bash
   # Zotero API credentials
   ZOTERO_ID=YOUR_ZOTERO_USER_ID
   ZOTERO_KEY=YOUR_ZOTERO_API_KEY
   
   # Email configuration
   SENDER=your-email@gmail.com
   RECEIVER=recipient-email@domain.com
   SENDER_PASSWORD=your-app-password
  
   ```

## 🚀 Usage

### Manual Run
```bash
uv run src/main.py
```

## 🏗️ Project Structure

```
zotero-arxiv-daily/
├── src/
│   ├── main.py              # Main execution script
│   ├── paper.py             # arXiv and Zotero integration
│   ├── construct_email.py   # Email generation and sending
│   ├── config.py            # Configuration management
│   └── logger.py            # Logging utilities
├── .env                     # Environment variables
└── README.md               # This file
```

## 📧 Email Format

Each email includes:
- **Paper Title**: Clear, prominent display
- **Authors**: Formatted author list
- **arXiv ID**: Direct link to paper
- **Abstract**: Abstract of the paper
- **PDF Link**: Direct download button

## TODO
- [ ] Local Zotero library support
- [ ] Better ranker function
- [ ] Save the remote Zotero to database