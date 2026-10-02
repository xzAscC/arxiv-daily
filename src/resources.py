import html
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field

from loguru import logger

from paper import ArxivPaper

USER_AGENT = "arxiv-daily/0.1 (personal paper digest)"
URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}]+")
CODE_HOSTS = ("github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "anonymous.4open.science")
# "code ... will be released / made available / open-sourced"
CODE_PROMISE_RE = re.compile(
    r"\b(code|implementation|checkpoints?|models?|weights)\b[^.]{0,80}\b(will|to) be\b[^.]{0,30}\b(released|available|open[- ]?sourced|public)",
    re.IGNORECASE,
)


@dataclass
class Resources:
    comment: str = ""
    code: list[str] = field(default_factory=list)
    code_stars: int | None = None
    models: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    project: str = ""
    code_promised: bool = False


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def fetch_abs_page(arxiv_id: str) -> dict:
    """Read title, abstract, comment and the links inside abstract/comment from the arXiv abs page."""
    page = fetch(f"https://arxiv.org/abs/{arxiv_id}")

    def block(pattern: str) -> str:
        m = re.search(pattern, page, re.DOTALL)
        return m.group(1) if m else ""

    title = strip_tags(block(r'<h1 class="title mathjax">(.*?)</h1>')).removeprefix("Title:").strip()
    abstract_html = block(r'<blockquote class="abstract mathjax">(.*?)</blockquote>')
    comment_html = block(r'<td class="tablecell comments mathjax">(.*?)</td>')
    abstract = strip_tags(abstract_html).removeprefix("Abstract:").strip()
    links = [u.rstrip(".,;:") for u in URL_RE.findall(html.unescape(abstract_html + " " + comment_html))]
    return {
        "title": title,
        "abstract": abstract,
        "comment": strip_tags(comment_html),
        "links": list(dict.fromkeys(links)),
    }


def fetch_hf_paper(arxiv_id: str) -> dict:
    """Hugging Face paper page: GitHub repo, stars and linked models/datasets (empty if not indexed yet)."""
    try:
        return json.loads(fetch(f"https://huggingface.co/api/papers/{arxiv_id}"))
    except Exception:
        return {}


def classify_link(url: str, res: Resources) -> None:
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
    path = url.split(host, 1)[-1].strip("/")
    if host in CODE_HOSTS and path:
        res.code.append(url)
    elif host == "huggingface.co" and path:
        if path.startswith("datasets/"):
            res.datasets.append(url)
        elif path.startswith("spaces/") or path.startswith("papers/") or path.startswith("docs/"):
            res.project = res.project or url
        else:
            res.models.append(url)
    elif not res.project and host.endswith(".github.io"):
        res.project = url


def find_resources(paper: ArxivPaper) -> Resources:
    res = Resources()
    try:
        page = fetch_abs_page(paper.arxiv_id)
        res.comment = page["comment"]
        for url in page["links"]:
            classify_link(url, res)
    except Exception as e:
        logger.debug(f"Failed to read the abs page of {paper.arxiv_id}: {e!r}")

    hf = fetch_hf_paper(paper.arxiv_id)
    if repo := hf.get("githubRepo"):
        if repo.rstrip("/").lower() not in {c.rstrip("/").lower() for c in res.code}:
            res.code.insert(0, repo)
        res.code_stars = hf.get("githubStars")
    if not res.project and hf.get("projectPage"):
        res.project = hf["projectPage"]
    res.models += [f"https://huggingface.co/{m['id']}" for m in hf.get("linkedModels", [])[:2]]
    res.datasets += [f"https://huggingface.co/datasets/{d['id']}" for d in hf.get("linkedDatasets", [])[:2]]

    res.code = list(dict.fromkeys(res.code))
    res.models = list(dict.fromkeys(res.models))
    res.datasets = list(dict.fromkeys(res.datasets))
    if not res.code:
        res.code_promised = bool(CODE_PROMISE_RE.search(paper.summary + " " + res.comment))
    return res


def attach_resources(papers: list[ArxivPaper]) -> None:
    """Look up open-source code, models and datasets for the recommended papers."""
    for p in papers:
        p.resources = find_resources(p)
        time.sleep(1)  # be polite to arxiv.org
    n_code = sum(bool(p.resources.code) for p in papers)
    logger.info(f"{n_code}/{len(papers)} recommended papers have open-source code.")
