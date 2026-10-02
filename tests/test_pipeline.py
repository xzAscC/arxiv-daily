import pytest
from feedparser import FeedParserDict

from construct_email import render_email, render_error
from paper import ArxivPaper, load_interests
from resources import CODE_PROMISE_RE, Resources, classify_link
from review import parse_json, select_papers


def make_paper(arxiv_id="2609.00001", **kwargs) -> ArxivPaper:
    return ArxivPaper(title="A <b>title</b>", summary="An abstract.", authors=["A", "B"], arxiv_id=arxiv_id, **kwargs)


def test_parse_json_tolerates_fences():
    assert parse_json('```json\n{"reviews": [{"id": "1"}]}\n```') == {"reviews": [{"id": "1"}]}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_load_interests_groups_free_text(tmp_path):
    f = tmp_path / "interests.txt"
    f.write_text("# comment\nloose line\n## Steering\nactivation steering\n\n## SAE\nsparse autoencoders\n")
    assert load_interests(f) == {
        "General": ["loose line"],
        "Steering": ["activation steering"],
        "SAE": ["sparse autoencoders"],
    }


def test_load_interests_missing_file(tmp_path):
    assert load_interests(tmp_path / "nope.txt") == {}


def test_from_feed_entry_splits_authors_and_abstract():
    entry = FeedParserDict({
        "id": "oai:arXiv.org:2609.12345v2",
        "title": "Some\n  Title",
        "summary": "arXiv:2609.12345v2 Announce Type: new \nAbstract: Hello\nworld.",
        "authors": [FeedParserDict(name="Alice A, Bob B, Carol C")],
        "tags": [FeedParserDict(term="cs.CL"), FeedParserDict(term="cs.LG")],
    })
    p = ArxivPaper.from_feed_entry(entry)
    assert (p.arxiv_id, p.title, p.summary) == ("2609.12345", "Some Title", "Hello world.")
    assert p.authors == ["Alice A", "Bob B", "Carol C"]


@pytest.mark.parametrize(
    "url, attr",
    [
        ("https://github.com/owner/repo", "code"),
        ("https://huggingface.co/owner/model", "models"),
        ("https://huggingface.co/datasets/owner/data", "datasets"),
        ("https://owner.github.io/project", "project"),
    ],
)
def test_classify_link(url, attr):
    res = Resources()
    classify_link(url, res)
    assert getattr(res, attr) in ([url], url)


def test_code_promise():
    assert CODE_PROMISE_RE.search("Code and pretrained model checkpoints will be released shortly")
    assert not CODE_PROMISE_RE.search("We release a model that will be useful.")


def test_select_papers_filters_and_sorts():
    good = make_paper("1", relevance=9, quality=8)
    ok = make_paper("2", relevance=7, quality=6)
    weak = make_paper("3", relevance=9, quality=3)
    unreviewed = make_paper("4")
    assert select_papers([ok, weak, good, unreviewed], top_k=10) == [good, ok]


def test_render_email_escapes_and_pairs_columns():
    papers = [make_paper(str(i), interest="Steering", resources=Resources(code=["https://github.com/o/r"])) for i in range(3)]
    html = render_email(papers, ["Steering"], "3 papers")
    assert "<b>title</b>" not in html and "&lt;b&gt;title&lt;/b&gt;" in html
    assert html.count('class="col"') == 4  # two rows, the odd card gets an empty partner
    assert "Code: o/r" in html


def test_render_error_escapes_trace():
    assert "&lt;module&gt;" in render_error('File "x", line 1, in <module>')
