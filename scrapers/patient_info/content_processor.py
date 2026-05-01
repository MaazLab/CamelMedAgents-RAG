from __future__ import annotations
import re

from bs4 import BeautifulSoup

from scrapers.patient_info.logger import get_logger

logger = get_logger("processor")


def extract_text_from_html(html: str) -> str:
    """Convert Discourse post HTML to clean plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove quoted reply blocks
    for quote in soup.find_all("aside", class_="quote"):
        quote.decompose()

    # Remove images and emoji
    for tag in soup.find_all(["img", "svg"]):
        tag.decompose()

    # Remove Discourse lightbox wrappers
    for tag in soup.find_all("div", class_="lightbox-wrapper"):
        tag.decompose()

    # Remove onebox (link preview) blocks
    for tag in soup.find_all("aside", class_="onebox"):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = text.strip()

    return text
