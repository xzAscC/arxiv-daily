import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from paper import ArxivPaper

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "interest": {"type": "string"},
                    "relevance": {"type": "integer", "minimum": 0, "maximum": 10},
                    "quality": {"type": "integer", "minimum": 0, "maximum": 10},
                    "tldr": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "interest", "relevance", "quality", "tldr", "reason"],
            },
        }
    },
    "required": ["reviews"],
}

REVIEW_PROMPT = """You are screening today's new arXiv papers for a PhD researcher. Their research interests:

{interests}

Review every paper below. Judge only from the title, authors and abstract; do not invent facts.

- interest: the name of the interest above the paper fits best (exactly as written before the colon), or "Other".
- relevance (0-10): how directly the paper serves the interests above. 9-10 = core topic they must read; 6-8 = clearly related method or finding; 3-5 = tangential (e.g. only uses LLMs, or only mentions the topic); 0-2 = unrelated.
- quality (0-10): how likely the paper is a solid, worthwhile contribution. Reward a clear and novel question or insight, careful methodology (controls, ablations, several models or datasets, theory backed by experiments), and concrete findings. Penalize incremental tweaks, benchmark-only or prompt-only work without insight, vague or overclaimed abstracts, tiny-scale evaluation, and position or survey papers with little substance.
- tldr: one sentence in Chinese saying what the paper does and finds. Keep technical terms (e.g. SAE, steering vector, RLVR) in English.
- reason: one short sentence in Chinese on why it is or is not worth reading for this researcher, naming any quality concern.

Return one review per paper, using its id exactly as given.

Papers:

{papers}
"""


JSON_INSTRUCTION = """
Output only a JSON object, with no code fences or other text, matching this JSON Schema:
{schema}
"""


def find_cli(name: str) -> str | None:
    # systemd user services do not have ~/.local/bin on PATH
    local = Path.home() / ".local/bin" / name
    return shutil.which(name) or (str(local) if local.exists() else None)


def format_interests(interests: dict[str, list[str]]) -> str:
    # Seed paper abstracts are long, so only keep their titles
    return "\n".join(
        f"- {name}: " + "; ".join(line.split(". ")[0] if len(line) > 200 else line for line in lines)
        for name, lines in interests.items()
    )


def format_paper(p: ArxivPaper) -> str:
    authors = ", ".join(p.authors[:10]) + (" et al." if len(p.authors) > 10 else "")
    return f"[id: {p.arxiv_id}]\nTitle: {p.title}\nAuthors: {authors}\nAbstract: {p.summary}\n"


def parse_json(text: str) -> dict:
    """Parse the JSON object in a model reply, tolerating code fences or surrounding text."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def run_cli(cmd: list[str], prompt: str, timeout: int) -> str:
    # Run outside the repo so no project settings, AGENTS.md or CLAUDE.md are picked up
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
        timeout=timeout, cwd=tempfile.gettempdir(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"exit code {result.returncode}: {result.stderr[-500:]}")
    return result.stdout


def call_claude(prompt: str, model: str, timeout: int) -> list[dict]:
    claude = find_cli("claude")
    if claude is None:
        raise FileNotFoundError("claude CLI not found")
    cmd = [
        claude, "-p",
        "--model", model,
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
        "--json-schema", json.dumps(REVIEW_SCHEMA),
    ]
    output = json.loads(run_cli(cmd, prompt, timeout))
    if output.get("is_error"):
        raise RuntimeError(output.get("result"))
    logger.info(f"Claude review cost ${output.get('total_cost_usd', 0):.3f}.")
    return output["structured_output"]["reviews"]


def call_pi(prompt: str, model: str, timeout: int) -> list[dict]:
    pi = find_cli("pi")
    if pi is None:
        raise FileNotFoundError("pi CLI not found")
    cmd = [
        pi, "-p",
        "--model", model,
        "--thinking", "medium",
        "--no-tools",
        "--no-session",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--offline",
    ]
    prompt += JSON_INSTRUCTION.format(schema=json.dumps(REVIEW_SCHEMA))
    return parse_json(run_cli(cmd, prompt, timeout))["reviews"]


BACKENDS = {"pi": call_pi, "claude": call_claude}


def review_papers(
    papers: list[ArxivPaper],
    interests: dict[str, list[str]],
    backend: str = "pi",
    model: str = "zai/glm-5.3",
    timeout: int = 900,
    retries: int = 2,
) -> bool:
    """
    Ask an LLM (through the local `pi` or `claude` CLI) to rate relevance and quality of the papers.
    Fills the review fields of the papers in place and returns whether the review succeeded.
    """
    prompt = REVIEW_PROMPT.format(
        interests=format_interests(interests),
        papers="\n".join(format_paper(p) for p in papers),
    )
    for attempt in range(1, retries + 1):
        try:
            reviews = BACKENDS[backend](prompt, model, timeout)
            break
        except FileNotFoundError as e:
            logger.warning(f"{e}, skipping the LLM review.")
            return False
        except Exception as e:
            logger.warning(f"LLM review attempt {attempt}/{retries} with {backend}/{model} failed: {e!r}")
    else:
        return False

    by_id = {p.arxiv_id: p for p in papers}
    for r in reviews:
        try:
            p = by_id.get(str(r["id"]).strip())
            if p is None:
                continue
            p.relevance, p.quality = float(r["relevance"]), float(r["quality"])
            p.tldr, p.reason = str(r["tldr"]), str(r["reason"])
            if r.get("interest") in interests:
                p.interest = r["interest"]
        except (KeyError, TypeError, ValueError):
            logger.debug(f"Skipping malformed review: {r!r}")
    reviewed = sum(p.quality is not None for p in papers)
    logger.info(f"{model} reviewed {reviewed}/{len(papers)} papers.")
    return reviewed > 0


def select_papers(
    papers: list[ArxivPaper], top_k: int = 10, min_quality: float = 5, min_relevance: float = 4
) -> list[ArxivPaper]:
    """Keep the reviewed papers that pass the quality and relevance bars, best first."""
    passed = [
        p for p in papers
        if p.quality is not None and p.quality >= min_quality and p.relevance >= min_relevance
    ]
    logger.info(f"{len(passed)}/{len(papers)} reviewed papers passed the quality/relevance bar.")
    return sorted(passed, key=lambda p: p.final_score, reverse=True)[:top_k]
