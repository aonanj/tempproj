import hashlib
import fitz
from PIL import Image
import pytesseract
import io
import re
from typing import List
from docx import Document

def _ocr_page(page: fitz.Page, zoom: float = 2.0) -> str:
    mat = fitz.Matrix(zoom, zoom)

    pix = page.get_pixmap(matrix=mat, alpha=False)  # type: ignore
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img)

def _blocks_text(tp: fitz.TextPage) -> str:
    blocks = tp.extractBLOCKS() 
    blocks.sort(key=lambda b: (round(b[1], 2), round(b[0], 2)))
    parts = [(b[4] or "").strip() for b in blocks if (b[4] or "").strip()]
    return "\n\n".join(parts)

def _normalize(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)     # de-hyphenate soft wraps
    s = re.sub(r"\n{3,}", "\n\n", s)           # collapse excess breaks
    return s

def sha256_file(file) -> str:
    file.seek(0)
    return sha256_bytes(file.read())

def sha256_bytes(bytes: bytes) -> str:
    return hashlib.sha256(bytes).hexdigest()

def sha256_text(text: str) -> str:
    """Compute the SHA-256 hash of a text string."""
    return sha256_bytes(text.encode('utf-8'))

def extract_pdf_text(file_path):
    doc = fitz.open(file_path)
    out_parts: List[str] = []
    for page in doc:
        tp = page.get_textpage()
        txt = _blocks_text(tp).strip()
        if not txt:
            txt = _ocr_page(page).strip()
        out_parts.append(txt)
        tp = None
    doc.close()
    raw = "\n\n\f\n\n".join(out_parts).strip()
    return _normalize(raw)

def extract_docx_text(file_path):
    doc = Document(file_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    return _normalize(text)