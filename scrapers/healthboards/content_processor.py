from __future__ import annotations
import re

from bs4 import BeautifulSoup

from scrapers.healthboards.logger import get_logger

logger = get_logger("hb_processor")


def extract_text_from_vbulletin_html(html: str) -> str:
    """Convert vBulletin post HTML to clean plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove quoted reply blocks (vBulletin uses bbcode_container / bbcode_quote)
    for quote in soup.find_all("div", class_=re.compile(r"bbcode_container|bbcode_quote")):
        quote.decompose()

    # Remove user signatures
    for sig in soup.find_all("div", class_="signaturecontainer"):
        sig.decompose()

    # Remove images (smilies, avatars, attachments)
    for img in soup.find_all("img"):
        img.decompose()

    # Remove "Last edited by ..." footers
    for em in soup.find_all("em"):
        if em.get_text(strip=True).startswith("Last edited by"):
            em.decompose()
    for div in soup.find_all("div", class_="lastedit"):
        div.decompose()

    text = soup.get_text(separator="\n")

    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = text.strip()

    return text
