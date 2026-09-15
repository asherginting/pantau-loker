import io
import os
from pathlib import Path
from urllib.parse import urlparse

from http_utils import polite_get

CV_DIR = Path(__file__).resolve().parent.parent / "cv"
SUPPORTED_EXTENSIONS = (".pdf", ".docx")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract(data: bytes, hint: str) -> str:
    hint = hint.lower()
    if hint.endswith(".pdf") or data[:4] == b"%PDF":
        return _extract_pdf(data)
    if hint.endswith(".docx") or data[:2] == b"PK":
        return _extract_docx(data)
    return data.decode("utf-8", errors="ignore")


def _find_uploaded_file() -> Path | None:
    if not CV_DIR.exists():
        return None
    for path in sorted(CV_DIR.iterdir()):
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return path
    return None


def load_cv() -> str:
    cv_url = os.environ.get("CV_URL")
    if cv_url:
        response = polite_get(cv_url)
        response.raise_for_status()
        hint = urlparse(cv_url).path + "|" + response.headers.get("Content-Type", "")
        text = _extract(response.content, hint)
        if not text.strip():
            raise RuntimeError(f"CV_URL resolved but contained no extractable text: {cv_url}")
        return text

    uploaded = _find_uploaded_file()
    if uploaded:
        return _extract(uploaded.read_bytes(), uploaded.name)

    raise RuntimeError(
        "No resume found. Set CV_URL to a hosted PDF/DOCX, or place a .pdf/.docx file in cv/."
    )
