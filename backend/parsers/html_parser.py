"""
html parser. strips all the moodle ui garbage and returns readable text.
bs4 removes the noisy tags first, then html2text converts to plain text.
"""
import logging
import re

import html2text
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# html2text config — ignore links since they're just noise in embeddings
_h2t = html2text.HTML2Text()
_h2t.ignore_links     = True    # nu includea URL-uri în text (zgomot)
_h2t.ignore_images    = True    # nu ne interesează imaginile
_h2t.body_width       = 0       # nu fa wrap la linii
_h2t.protect_links    = False
_h2t.unicode_snob     = True
_h2t.ignore_tables    = False
_h2t.bypass_tables    = False

# tags that are pure ui noise in moodle pages
_NOISE_TAG_NAMES = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "input", "button", "select", "option", "textarea",
    "iframe", "noscript", "svg", "canvas", "video", "audio",
    "figure", "figcaption",
]

_MOODLE_NOISE_CLASS_RE = re.compile(
    r"navbar|breadcrumb|usermenu|logininfo|editmode|activity-navigation"
    r"|block_|region-|header-|page-header|page-footer",
    re.I,
)
_MOODLE_NOISE_ID_RE = re.compile(
    r"^(nav|footer|header|page-footer|page-header|dock|yui)",
    re.I,
)


def _remove_noise_tags(soup: BeautifulSoup) -> None:
    """nukes all the ui junk from the bs4 tree before converting"""
    for tag_name in _NOISE_TAG_NAMES:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # moodle-specific blocks with class/id patterns we don't want
    for tag in soup.find_all(True):
        tag_class = " ".join(tag.get("class", []))
        tag_id = tag.get("id", "")
        if _MOODLE_NOISE_CLASS_RE.search(tag_class) or _MOODLE_NOISE_ID_RE.search(tag_id):
            tag.decompose()


def _strip_residual_html(text: str) -> str:
    """removes html tags and entities that survived html2text somehow"""
    # Elimină taguri HTML reziduale
    text = re.sub(r"<[^>]{0,300}>", "", text)
    # Elimină entitățile HTML comune
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);", " ", text)
    # Elimină atribute CSS inline rămase (style="...")
    text = re.sub(r'style\s*=\s*["\'][^"\']*["\']', "", text)
    # Elimină linii care sunt exclusiv cod JS/CSS ({, }, ;)
    text = re.sub(r"^\s*[{}();,]{1,5}\s*$", "", text, flags=re.MULTILINE)
    return text


def _clean_markdown_noise(text: str) -> str:
    """gets rid of markdown junk html2text adds from moodle nav elements"""
    # Elimină link-urile rămase [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Elimină liniile cu doar caractere speciale Markdown (separator lines)
    text = re.sub(r"^[\s*\-_=|>]{3,}$", "", text, flags=re.MULTILINE)
    # Elimină liniile de 1-2 caractere (artefacte)
    text = re.sub(r"^.{0,2}$", "", text, flags=re.MULTILINE)
    return text


def extract_text_from_html(html: str, base_url: str = "") -> str:
    """
    pulls clean text from an html string.
    bs4 strips noise first, html2text converts to readable text,
    then we clean up whatever's left over.
    returns empty string if input is empty or something breaks
    """
    if not html or not html.strip():
        return ""

    try:
        # step 1: aggressive cleanup with bs4
        soup = BeautifulSoup(html, "lxml")
        _remove_noise_tags(soup)
        clean_html = str(soup)

        # step 2: html -> text
        if base_url:
            _h2t.baseurl = base_url
        text = _h2t.handle(clean_html)

        # step 3: strip leftover html fragments and markdown noise
        text = _strip_residual_html(text)
        text = _clean_markdown_noise(text)

        # step 4: normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        logger.debug(f"html parsed → {len(text)} chars")
        return text

    except Exception as e:
        logger.error(f"html parsing failed: {e}")
        # fallback: just get text with bs4
        try:
            return BeautifulSoup(html, "lxml").get_text(separator="\n").strip()
        except Exception:
            return ""
