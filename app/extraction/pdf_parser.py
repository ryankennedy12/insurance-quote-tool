import logging
import os
import tempfile

import fitz  # pymupdf — used for page count
import pymupdf4llm

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, bool]:
    """Extract markdown text from PDF bytes and determine if the PDF is digital.

    Returns:
        (markdown_text, is_digital) where is_digital is True if average
        chars per page > 100 (indicating machine-generated text, not a scan).
        On any error, returns ("", False).
    """
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        markdown_text: str = pymupdf4llm.to_markdown(tmp_path)

        doc = fitz.open(tmp_path)
        num_pages = len(doc)
        doc.close()

        if num_pages > 0:
            is_digital = (len(markdown_text) / num_pages) > 100
        else:
            is_digital = False

        logger.info(
            "PDF parsed: %d pages, %d chars, is_digital=%s",
            num_pages, len(markdown_text), is_digital,
        )
        return markdown_text, is_digital

    except Exception:
        logger.error("Failed to extract text from PDF", exc_info=True)
        return "", False

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
