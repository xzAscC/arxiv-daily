import datetime
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from html import escape

from loguru import logger

from paper import ArxivPaper

# Most styling is inline and table-based since email clients drop modern CSS. The only
# <style> rule stacks the two columns on narrow screens (supported by Gmail, Apple Mail, iOS).
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif"
INTEREST_COLORS = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#db2777"]
GAP = 14

framework = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @media only screen and (max-width: 760px) {
    .col { display: block !important; width: 100% !important; box-sizing: border-box; }
    .gap { display: block !important; width: 100% !important; height: __GAP__px !important; }
  }
</style>
</head>
<body style="margin:0; padding:0; background-color:#f3f4f6;">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f3f4f6;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:1120px; font-family:__FONT__;">
  <tr><td style="padding:0 4px 16px 4px;">
    <div style="font-size:22px; font-weight:700; color:#111827;">arXiv Daily · __DATE__</div>
    <div style="font-size:13px; color:#6b7280; padding-top:4px;">__STATS__</div>
  </td></tr>
  __CONTENT__
  <tr><td style="padding:16px 4px; font-size:12px; color:#9ca3af;">
    Ranked by Qwen3-Embedding against interests.txt, then reviewed by an LLM for relevance (R) and quality (Q).
    Code / model links come from the arXiv abstract page and Hugging Face.
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def get_empty_html() -> str:
    return """
  <tr><td style="background-color:#ffffff; border-radius:10px; padding:24px; font-size:16px; color:#374151;">
    No papers today. Take a rest!
  </td></tr>"""


def format_authors(authors: list[str], limit: int = 4) -> str:
    if len(authors) > limit:
        return ", ".join(authors[:limit]) + f" et al. ({len(authors)})"
    return ", ".join(authors)


def badge(text: str, color: str, fill: bool = False) -> str:
    colors = f"color:#ffffff; background-color:{color};" if fill else f"color:{color};"
    return (
        f'<span style="display:inline-block; font-size:11px; font-weight:600; {colors} '
        f'border:1px solid {color}; border-radius:10px; padding:1px 8px; margin:0 4px 4px 0;">{escape(text)}</span>'
    )


def link_button(text: str, url: str, color: str | None = None) -> str:
    style = (
        f"color:#ffffff; background-color:{color}; border:1px solid {color};"
        if color
        else "color:#374151; background-color:#ffffff; border:1px solid #d1d5db;"
    )
    return (
        f'<a href="{escape(url)}" style="display:inline-block; text-decoration:none; font-size:12px; font-weight:600; '
        f'{style} padding:4px 11px; border-radius:6px; margin:0 4px 4px 0;">{escape(text)}</a>'
    )


def short_name(url: str) -> str:
    """owner/repo for GitHub or Hugging Face links."""
    parts = url.split("://", 1)[-1].split("/")[1:]
    parts = parts[1:] if parts and parts[0] == "datasets" else parts
    return "/".join(parts[:2]).removesuffix(".git") or url


def get_resource_parts(p: ArxivPaper) -> tuple[str, str, str]:
    """Return (status badge, resource buttons, comment line) for a paper."""
    res = p.resources
    if res is None:
        return "", "", ""
    if res.code:
        stars = f" ★{res.code_stars}" if res.code_stars else ""
        status = badge(f"Code{stars}", "#15803d", fill=True)
    elif res.code_promised:
        status = badge("Code soon", "#b45309")
    else:
        status = badge("No code", "#9ca3af")
    if res.models:
        status += badge("Model", "#ca8a04", fill=True)

    buttons = "".join(link_button(f"Code: {short_name(u)}", u, "#15803d") for u in res.code[:2])
    buttons += "".join(link_button(f"🤗 {short_name(u)}", u, "#ca8a04") for u in res.models[:2])
    buttons += "".join(link_button(f"Data: {short_name(u)}", u) for u in res.datasets[:1])
    if res.project:
        buttons += link_button("Project", res.project)

    comment = ""
    if res.comment:
        text = res.comment if len(res.comment) <= 140 else res.comment[:140].rsplit(" ", 1)[0] + " …"
        comment = f'<div style="font-size:12px; color:#6b7280; font-style:italic; padding-top:6px;">{escape(text)}</div>'
    return status, buttons, comment


def get_block_html(rank: int, p: ArxivPaper, interest_color: str) -> str:
    status, resource_buttons, comment = get_resource_parts(p)
    badges = badge(p.interest, interest_color) if p.interest else ""
    if p.quality is not None:
        badges += badge(f"R {p.relevance:.0f}", "#4b5563") + badge(f"Q {p.quality:.0f}", "#4b5563")
    badges += status

    if p.tldr:
        body = f"""
      <div style="font-size:14px; line-height:1.6; color:#111827; padding-top:10px;"><b>TL;DR</b>&nbsp; {escape(p.tldr)}</div>
      <div style="font-size:13px; line-height:1.6; color:#374151; padding-top:4px;"><b>推荐理由</b>&nbsp; {escape(p.reason)}</div>"""
    else:
        body = ""
    # Without an LLM summary show the full abstract, otherwise a short preview
    limit = 280
    abstract = p.summary if not p.tldr or len(p.summary) <= limit else p.summary[:limit].rsplit(" ", 1)[0] + " …"

    return f"""
    <td class="col" width="50%" valign="top" style="width:50%; background-color:#ffffff; border-radius:10px; padding:16px 18px; border-left:4px solid {interest_color};">
      <div style="padding-bottom:6px;">{badges}</div>
      <div style="font-size:16px; font-weight:700; line-height:1.35;">
        <span style="color:#9ca3af;">{rank}.</span>
        <a href="{p.abs_url}" style="color:#111827; text-decoration:none;">{escape(p.title)}</a>
      </div>
      <div style="font-size:12px; color:#6b7280; padding-top:5px;">{escape(format_authors(p.authors))}</div>{comment}{body}
      <div style="font-size:12px; line-height:1.55; color:#6b7280; padding-top:8px;">{escape(abstract)}</div>
      <div style="padding-top:10px;">
        {link_button("PDF", p.pdf_url, "#b91c1c")}{resource_buttons}{link_button("arXiv", p.abs_url)}{link_button("alphaXiv", f"https://www.alphaxiv.org/abs/{p.arxiv_id}")}
      </div>
    </td>"""


def render_email(papers: list[ArxivPaper], interests: list[str], stats: str) -> str:
    colors = {name: INTEREST_COLORS[i % len(INTEREST_COLORS)] for i, name in enumerate(interests)}
    blocks = [get_block_html(i + 1, p, colors.get(p.interest, "#6b7280")) for i, p in enumerate(papers)]
    gap = f'<td class="gap" width="{GAP}" style="width:{GAP}px; font-size:0; line-height:0;">&nbsp;</td>'
    rows = []
    for i in range(0, len(blocks), 2):
        right = blocks[i + 1] if i + 1 < len(blocks) else '<td class="col" width="50%" style="width:50%;"></td>'
        rows.append(f"""
  <tr><td>
    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout:fixed;">
    <tr>{blocks[i]}{gap}{right}</tr>
    </table>
  </td></tr>
  <tr><td style="height:{GAP}px; line-height:{GAP}px; font-size:0;">&nbsp;</td></tr>""")
    content = "".join(rows) if papers else get_empty_html()
    return (
        framework.replace("__FONT__", FONT)
        .replace("__GAP__", str(GAP))
        .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d"))
        .replace("__STATS__", escape(stats))
        .replace("__CONTENT__", content)
    )


def render_error(trace: str) -> str:
    content = f"""
  <tr><td style="background-color:#ffffff; border-radius:10px; padding:20px; border-left:4px solid #b91c1c;">
    <div style="font-size:16px; font-weight:700; color:#b91c1c;">Today's run failed</div>
    <div style="font-size:13px; color:#374151; padding-top:6px;">Check <code>journalctl --user -u arxiv-daily</code> or logs/app.log for details.</div>
    <pre style="font-size:12px; color:#374151; background-color:#f9fafb; padding:12px; border-radius:6px; white-space:pre-wrap; word-break:break-all;">{escape(trace[-3000:])}</pre>
  </td></tr>"""
    return (
        framework.replace("__FONT__", FONT)
        .replace("__GAP__", str(GAP))
        .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d"))
        .replace("__STATS__", "")
        .replace("__CONTENT__", content)
    )


def send_email(
    sender: str,
    receiver: str,
    password: str,
    smtp_server: str,
    smtp_port: int,
    html: str,
    subject: str,
):
    def _format_addr(s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, "utf-8").encode(), addr))

    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = _format_addr("arXiv Daily <%s>" % sender)
    msg["To"] = _format_addr("You <%s>" % receiver)
    msg["Subject"] = Header(subject, "utf-8").encode()

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=60)
        server.starttls()
    except Exception as e:
        logger.warning(f"Failed to use TLS. {e}")
        logger.warning("Try to use SSL.")
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=60)

    server.login(sender, password)
    server.sendmail(sender, [receiver], msg.as_string())
    server.quit()
