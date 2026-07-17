"""
core/pdf_cleaner.py
Handles PDF cleaning: removes irrelevant pages, keeps only relevant ones.
"""
import os
import pypdf
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_KEYWORDS = [
    "inflation", "return rate", "rate of return", "rate return",
    "returning rate", "rate of returning", "smoothing", "smooth",
    "investment return", "return on investment", "return of investment"
]


class PDFCleaner:
    """Cleans PDFs by keeping only relevant pages based on keywords."""

    def __init__(self, keywords=None):
        self.keywords = keywords or DEFAULT_KEYWORDS

    def extract_text_from_page(self, page):
        try:
            return page.extract_text().lower()
        except Exception:
            return ""

    def page_contains_keywords(self, page):
        text = self.extract_text_from_page(page)
        return any(keyword.lower() in text for keyword in self.keywords)

    def clean_pdf(self, input_path, output_path):
        """
        Clean a single PDF by extracting relevant pages.
        Returns (pages_extracted, total_pages).
        """
        try:
            with open(input_path, 'rb') as file:
                reader = pypdf.PdfReader(file)
                if reader.is_encrypted:
                    reader.decrypt('')

                writer = pypdf.PdfWriter()
                total_pages = len(reader.pages)
                pages_to_extract = set()

                # Always include first page
                for i in range(min(1, total_pages)):
                    pages_to_extract.add(i)

                # Check all pages for keywords
                for page_num in range(total_pages):
                    page = reader.pages[page_num]
                    if self.page_contains_keywords(page):
                        pages_to_extract.add(page_num)

                for page_num in sorted(pages_to_extract):
                    writer.add_page(reader.pages[page_num])

                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)

                return len(pages_to_extract), total_pages

        except Exception as e:
            raise Exception(f"Error cleaning PDF '{os.path.basename(input_path)}': {str(e)}")

    def clean_folder(self, input_folder, output_folder, progress_callback=None, progress_value_callback=None):
        """
        Clean all PDFs in input_folder and save to output_folder.
        Calls progress_callback(message: str) and progress_value_callback(percent: int).
        Returns list of pdf filenames that were cleaned.
        """
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]

        if not pdf_files:
            raise Exception("No PDF files found in selected folder.")

        def clean_single(pdf_file):
            inp = os.path.join(input_folder, pdf_file)
            out = os.path.join(output_folder, pdf_file)
            if os.path.exists(out):
                return pdf_file, True, "already cleaned", None, None
            try:
                new_pages, old_pages = self.clean_pdf(inp, out)
                return pdf_file, True, "cleaned", old_pages, new_pages
            except Exception as e:
                return pdf_file, False, str(e), None, None

        if progress_callback:
            progress_callback(f"Cleaning {len(pdf_files)} PDFs using multiple threads...")

        cleaned_files = []
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 6) as executor:
            futures = {executor.submit(clean_single, pdf): pdf for pdf in pdf_files}
            completed = 0
            for future in as_completed(futures):
                pdf_file, success, status, old_pages, new_pages = future.result()
                completed += 1
                if not success:
                    if progress_callback:
                        progress_callback(f"  ✗ Error cleaning {pdf_file}: {status}")
                elif status == "already cleaned":
                    if progress_callback:
                        progress_callback(f"Skipping ({completed}/{len(pdf_files)}): {pdf_file} (already cleaned)")
                    cleaned_files.append(pdf_file)
                else:
                    if progress_callback:
                        progress_callback(f"  ✓ Cleaned ({completed}/{len(pdf_files)}): {pdf_file} ({old_pages} → {new_pages} pages)")
                    cleaned_files.append(pdf_file)

                if progress_value_callback:
                    progress_value_callback(int(completed / len(pdf_files) * 20))

        return cleaned_files
