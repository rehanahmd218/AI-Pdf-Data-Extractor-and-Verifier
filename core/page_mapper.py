"""
core/page_mapper.py
Content-based page mapping between original and modified (cleaned) PDFs.

When a modified PDF has pages removed, the page numbers shift.
This module finds the corresponding original page for a given modified-PDF page
by matching the text fingerprints of the stripped page.
"""
import os
import re
try:
    import fitz
except ImportError:
    import pymupdf as fitz


def _fingerprint(text: str) -> str:
    """Create a short, normalised fingerprint from page text for comparison."""
    if not text:
        return ""
    # Collapse whitespace, lowercase, take first 300 chars
    cleaned = re.sub(r'\s+', ' ', text.strip()).lower()
    return cleaned[:300]


def build_original_fingerprints(original_pdf_path: str) -> list[tuple[int, str]]:
    """
    Build a list of (0-based-page-index, fingerprint) for every page
    in the original PDF.
    """
    doc = fitz.open(original_pdf_path)
    fingerprints = []
    for i, page in enumerate(doc):
        text = page.get_text()
        fingerprints.append((i, _fingerprint(text)))
    doc.close()
    return fingerprints


def find_original_page(modified_pdf_path: str, modified_page_index: int,
                        original_fingerprints: list[tuple[int, str]]) -> int | None:
    """
    Given a 0-based page index in the modified PDF, find the matching
    0-based page index in the original PDF by text fingerprint.

    Returns the original 0-based page index, or None if no match found.
    """
    doc = fitz.open(modified_pdf_path)
    if modified_page_index < 0 or modified_page_index >= len(doc):
        doc.close()
        return None

    mod_text = doc[modified_page_index].get_text()
    doc.close()

    mod_fp = _fingerprint(mod_text)
    if not mod_fp:
        return None

    best_idx = None
    best_score = 0

    for orig_idx, orig_fp in original_fingerprints:
        if not orig_fp:
            continue
        # Simple overlap score: proportion of shared characters
        score = _similarity(mod_fp, orig_fp)
        if score > best_score:
            best_score = score
            best_idx = orig_idx

    # Only return if similarity is meaningful (> 30%)
    if best_score > 0.30:
        return best_idx
    return None


def _similarity(a: str, b: str) -> float:
    """
    Jaccard-like token similarity between two strings.
    Fast and good enough for our fingerprint length.
    """
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


class PageMapper:
    """
    High-level helper that caches the original PDF fingerprints
    so repeated lookups for the same original file are fast.
    """

    def __init__(self):
        self._cache: dict[str, list[tuple[int, str]]] = {}

    def _get_fingerprints(self, original_pdf_path: str) -> list[tuple[int, str]]:
        if original_pdf_path not in self._cache:
            self._cache[original_pdf_path] = build_original_fingerprints(original_pdf_path)
        return self._cache[original_pdf_path]

    def map_to_original(self, modified_pdf_path: str, modified_page_index: int,
                         original_pdf_path: str) -> int | None:
        """
        Map a 0-based page index in the modified PDF to the corresponding
        0-based page index in the original PDF.
        Returns None if no confident match is found.
        """
        fps = self._get_fingerprints(original_pdf_path)
        return find_original_page(modified_pdf_path, modified_page_index, fps)

    def clear_cache(self):
        self._cache.clear()
