from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from ..config import settings

PDF_MAGIC = b"%PDF-"
SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table", "section"}


class FetchError(Exception):
    """The document could not be retrieved. Distinct from failing to parse one."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass
class TermsDocument:
    """Either a PDF we hand to Gemini whole, or text we extracted ourselves."""

    kind: str
    locator: str
    text: str | None = None
    data: bytes | None = None
    mime_type: str | None = None
    content_type: str | None = None

    @property
    def is_pdf(self) -> bool:
        return self.kind == "pdf"


class _TextExtractor(HTMLParser):
    """Strips an issuer's page to readable text without pulling in a dependency."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        # A malformed page still yields whatever was parsed before the fault.
        pass
    return parser.text()


def fetch_terms(url: str) -> TermsDocument:
    """Retrieve a terms document, deciding PDF-vs-text from what actually arrived.

    Content type is checked before the file extension because issuers routinely
    serve PDFs from extension-less URLs and HTML from paths ending in .pdf.
    """
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=settings.terms_fetch_timeout,
            headers={"User-Agent": settings.terms_user_agent},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            body = response.content
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        reason = "rate_limited" if status in (403, 429) else "fetch_failed"
        raise FetchError(reason, f"The source returned HTTP {status}.") from exc
    except httpx.TimeoutException as exc:
        raise FetchError("fetch_failed", "The source did not respond in time.") from exc
    except httpx.HTTPError as exc:
        raise FetchError("fetch_failed", f"The source could not be reached: {exc}.") from exc

    if len(body) > settings.terms_max_bytes:
        raise FetchError("unsupported_content", "The document is too large to read.")

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()

    if body.startswith(PDF_MAGIC) or content_type == "application/pdf":
        return TermsDocument(
            kind="pdf", locator=str(response.url), data=body,
            mime_type="application/pdf", content_type=content_type,
        )

    if content_type and not (content_type.startswith("text/") or "html" in content_type or "xml" in content_type):
        raise FetchError("unsupported_content", f"The source returned {content_type}, which is not a terms document.")

    text = html_to_text(response.text)
    if len(text) < settings.terms_min_chars:
        raise FetchError(
            "unsupported_content",
            "The page carried almost no readable text, which usually means the rates are rendered by scripts.",
        )

    return TermsDocument(
        kind="text", locator=str(response.url),
        text=text[: settings.terms_max_chars], content_type=content_type,
    )


def document_from_text(text: str, locator: str = "pasted text") -> TermsDocument:
    return TermsDocument(kind="text", locator=locator, text=text[: settings.terms_max_chars])


def document_from_upload(data: bytes, filename: str) -> TermsDocument:
    """A file the user uploaded rather than one we fetched."""
    if data.startswith(PDF_MAGIC):
        return TermsDocument(kind="pdf", locator=filename, data=data, mime_type="application/pdf")
    decoded = data.decode("utf-8", errors="replace")
    text = html_to_text(decoded) if "<" in decoded[:2000] else decoded
    return TermsDocument(kind="text", locator=filename, text=text[: settings.terms_max_chars])
