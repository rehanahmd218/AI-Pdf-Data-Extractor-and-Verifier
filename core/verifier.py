"""
core/verifier.py
Verification logic: checks extracted JSON values against PDF page content.
Extracted and modularised from verify_extraction.py.
"""
import json
import os
import re
import fitz  # PyMuPDF
from PyQt5.QtCore import QThread, pyqtSignal


def normalize_text(text):
    if not text:
        return ""
    return re.sub(r'[\s\-|]+', '', str(text)).lower()


def extract_first_number(text):
    if text is None:
        return ""
    match = re.search(r'\d+', str(text))
    return match.group() if match else str(text).strip().lower()


def get_actual_page_index(actual_pdf_page):
    """Parse actual_pdf_page to a 0-based index. Returns None on failure."""
    if isinstance(actual_pdf_page, int):
        return actual_pdf_page - 1
    actual_pdf_page = str(actual_pdf_page).lower()
    if 'cover' in actual_pdf_page:
        return 0
    match = re.search(r'\d+', actual_pdf_page)
    if match:
        return int(match.group()) - 1
    return None


def verify_extracted_data(json_file, pdf_folder, output_file, progress_callback=None):
    """
    Verifies extracted JSON data against PDF content.
    Writes problems to output_file.
    Returns problems dict.
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    problems = {}
    total = len(data)

    for i, (pdf_name, fields) in enumerate(data.items()):
        pdf_path = os.path.join(pdf_folder, pdf_name)
        if progress_callback:
            progress_callback(f"Verifying ({i+1}/{total}): {pdf_name}")

        pdf_problems = {}

        if not os.path.exists(pdf_path):
            problems[pdf_name] = {"_error": "PDF file not found in folder"}
            continue

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
        except Exception as e:
            problems[pdf_name] = {"_error": f"Failed to open PDF: {e}"}
            continue

        for field_name, attributes in fields.items():
            if field_name == 'av_date':
                continue

            # Some JSON entries store a plain string instead of a dict — skip them.
            if not isinstance(attributes, dict):
                continue

            value = str(attributes.get('value', '')).strip().lower()
            doc_page = str(attributes.get('document_page', '')).strip().lower()
            actual_page = str(attributes.get('actual_pdf_page', '')).strip().lower()

            if 'not sure' in value or 'not sure' in doc_page or 'not sure' in actual_page:
                pdf_problems[field_name] = {
                    "issue": "Value marked as 'not sure'",
                    "attributes": attributes
                }
                continue

            doc_page_num = extract_first_number(doc_page)
            actual_page_num = extract_first_number(actual_page)

            # if doc_page_num == actual_page_num and doc_page_num != "":
            #     pdf_problems[field_name] = {
            #         "issue": "Document page and actual page value match",
            #         "attributes": attributes
            #     }
            #     continue

            page_idx = get_actual_page_index(actual_page)
            if page_idx is None:
                pdf_problems[field_name] = {
                    "issue": "Could not parse actual_pdf_page",
                    "attributes": attributes
                }
                continue

            if page_idx < 0 or page_idx >= total_pages:
                pdf_problems[field_name] = {
                    "issue": f"Page index ({page_idx+1}) out of bounds. Total: {total_pages}",
                    "attributes": attributes
                }
                continue

            try:
                page_text = doc[page_idx].get_text()
                norm_page_text = normalize_text(page_text)
            except Exception as e:
                pdf_problems[field_name] = {
                    "issue": f"Failed to extract text from page {page_idx+1}: {e}",
                    "attributes": attributes
                }
                continue

            norm_value = normalize_text(value)
            orig_norm_doc_page = normalize_text(doc_page)

            norm_value_ns = re.sub(r'\s+', '', norm_value)
            clean_doc_page_ns = re.sub(r'\s+', '', orig_norm_doc_page)
            norm_page_text_ns = re.sub(r'\s+', '', norm_page_text)

            value_found = norm_value_ns in norm_page_text_ns

            if not value_found and '%' in norm_value_ns:
                norm_no_pct = norm_value_ns.replace('%', '')
                value_found = norm_no_pct in norm_page_text_ns
                if not value_found and '.' in norm_no_pct:
                    integer_part, decimal_part = norm_no_pct.split('.', 1)
                    if not decimal_part.replace('0', ''):
                        value_found = f"{integer_part}%" in norm_page_text_ns

            if not value_found and field_name == 'smoothing_years':
                num_to_word = {
                    '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
                    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten'
                }
                if norm_value_ns in num_to_word:
                    value_found = num_to_word[norm_value_ns] in norm_page_text_ns

            # --- Keyword-presence guards ---
            # Even if the number is found, require the relevant context keyword to
            # also appear on the same page, otherwise treat as not found.
            keyword_issue = None
            page_text_lower = page_text.lower()

            if value_found and field_name == 'actuarial_return_rate':
                if 'return' not in page_text_lower and "interest rate" not in page_text_lower :
                    value_found = False
                    keyword_issue = (
                        f"Value '{value}' found on page {page_idx+1} "
                        f"but keyword 'return' is absent"
                    )

            if value_found and field_name == 'smoothing_years':
                if 'smooth' not in page_text_lower:
                    value_found = False
                    keyword_issue = (
                        f"Value '{value}' found on page {page_idx+1} "
                        f"but keyword 'smooth' is absent"
                    )

            if value_found and field_name == 'actuarial_inflation_rate':
                if 'inflation' not in page_text_lower:
                    value_found = False
                    keyword_issue = (
                        f"Value '{value}' found on page {page_idx+1} "
                        f"but keyword 'inflation' is absent"
                    )

            doc_page_found = True
            if 'cover' not in orig_norm_doc_page:
                doc_page_found = clean_doc_page_ns in norm_page_text_ns

            if not value_found or not doc_page_found:
                issues = []
                if keyword_issue:
                    issues.append(keyword_issue)
                elif not value_found:
                    issues.append(f"Value '{value}' not found on page {page_idx+1}")
                if not doc_page_found:
                    issues.append(f"Doc page '{doc_page}' not found on page {page_idx+1}")
                pdf_problems[field_name] = {
                    "issue": " | ".join(issues),
                    "attributes": attributes
                }

        doc.close()
        if pdf_problems:
            problems[pdf_name] = pdf_problems

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(problems, f, indent=4, ensure_ascii=False)

    return problems


class VerificationThread(QThread):
    """Background QThread for running verification."""
    progress_update = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(bool, str, dict)   # success, message, problems_dict

    def __init__(self, json_file, pdf_folder, output_file):
        super().__init__()
        self.json_file = json_file
        self.pdf_folder = pdf_folder
        self.output_file = output_file

    def run(self):
        try:
            # Count total for progress
            with open(self.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            total = len(data)
            count = [0]

            def on_progress(msg):
                count[0] += 1
                self.progress_update.emit(msg)
                self.progress_value.emit(int(count[0] / max(total, 1) * 100))

            problems = verify_extracted_data(
                self.json_file, self.pdf_folder, self.output_file,
                progress_callback=on_progress
            )
            msg = f"✓ Verification complete. Issues found in {len(problems)} PDF(s). Saved to: {self.output_file}"
            self.progress_update.emit(msg)
            self.finished.emit(True, msg, problems)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e), {})

