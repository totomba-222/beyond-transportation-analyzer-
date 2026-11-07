"""PDF -> list of (sheet_name, DataFrame) using table extraction first, OCR second."""
import io
import re

import pandas as pd


def _tables_to_frames(pdf):
    frames = []
    for pno, page in enumerate(pdf.pages, 1):
        for tno, tbl in enumerate(page.extract_tables() or [], 1):
            if tbl and len(tbl) > 1:
                frames.append((f"p{pno}t{tno}", pd.DataFrame(tbl, dtype=object)))
    return frames


def _ocr_frames(pdf):
    import pytesseract
    frames = []
    for pno, page in enumerate(pdf.pages, 1):
        img = page.to_image(resolution=200).original
        text = pytesseract.image_to_string(img, config="--psm 6")
        rows = [re.split(r"\s{2,}|\t", ln.strip()) for ln in text.splitlines() if ln.strip()]
        if len(rows) > 1:
            w = max(len(r) for r in rows)
            frames.append((f"p{pno}ocr", pd.DataFrame([r + [None] * (w - len(r)) for r in rows], dtype=object)))
    return frames


def pdf_to_sheets(data: bytes):
    import pdfplumber
    warns = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        frames = _tables_to_frames(pdf)
        if not frames:
            try:
                frames = _ocr_frames(pdf)
                warns.append("PDF has no extractable tables - OCR fallback used; every OCR row is flagged for verification.")
            except Exception as e:  # tesseract missing, etc.
                warns.append(f"PDF has no extractable tables and OCR failed ({e}).")
    return frames, warns
