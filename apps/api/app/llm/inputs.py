"""What each provider can read, and PDF pages as images for those that can't (F10 AC5)."""

import io
from collections.abc import Sequence
from dataclasses import dataclass

import pypdfium2 as pdfium

from app.llm.types import FilePart, PermanentLlmError, TextPart

MAX_PAGES = 3
DPI = 150


@dataclass(frozen=True)
class Capabilities:
    reads_pdf: bool
    max_images: int


def pdf_to_images(data: bytes, *, max_pages: int = MAX_PAGES, dpi: int = DPI) -> list[FilePart]:
    """The first `max_pages` pages as PNGs, rendered one at a time to keep memory low."""
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PermanentLlmError("the PDF couldn't be opened to render page images") from exc
    try:
        images = []
        for index in range(min(len(document), max_pages)):
            page = document[index]
            try:
                bitmap = page.render(scale=dpi / 72)
                buffer = io.BytesIO()
                bitmap.to_pil().save(buffer, format="PNG", optimize=True)
                images.append(FilePart(mime_type="image/png", data=buffer.getvalue()))
            finally:
                page.close()
        return images
    finally:
        document.close()


def adapt_parts(
    parts: Sequence[TextPart | FilePart], capabilities: Capabilities
) -> tuple[list[TextPart | FilePart], str]:
    """Parts this provider can read, and how the file was sent: pdf | images | image."""
    adapted: list[TextPart | FilePart] = []
    mode = "text"
    for part in parts:
        if isinstance(part, FilePart) and part.mime_type == "application/pdf":
            if capabilities.reads_pdf:
                adapted.append(part)
                mode = "pdf"
            else:
                adapted.extend(
                    pdf_to_images(part.data, max_pages=min(MAX_PAGES, capabilities.max_images))
                )
                mode = "images"
        else:
            if isinstance(part, FilePart):
                mode = "image"
            adapted.append(part)
    return adapted, mode
