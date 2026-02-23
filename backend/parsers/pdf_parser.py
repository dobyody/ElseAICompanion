"""
pdf parser. pulls text out of pdf files using pypdf2.
works fine for regular pdfs, scanned ones (images) will return empty — no ocr, not worth implementing
"""
import logging
from pathlib import Path

import PyPDF2

logger = logging.getLogger(__name__)


def extract_text_from_pdf(path: Path) -> str:
    """
    extracts all text from a pdf, page by page.
    returns empty string if something breaks
    """
    text_parts: list[str] = []
    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text_parts.append(f"[Pagina {page_num + 1}]\n{page_text}")
                except Exception as e:
                    logger.warning(f"page {page_num + 1} in {path.name} broke: {e}")
    except Exception as e:
        logger.error(f"couldn't read pdf {path.name}: {e}")
        return ""

    full_text = "\n\n".join(text_parts)
    logger.debug(f"pdf done: {path.name} → {len(full_text)} chars")
    return full_text
