"""
core/batch_processor.py
Background QThread workers for batch PDF processing and Excel merging.
"""
import os
import json
import time
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from google import genai

from core.pdf_cleaner import PDFCleaner
from core.excel_merger import ExcelMerger


class ProcessingThread(QThread):
    """
    Background thread: cleans PDFs, uploads to Google File API,
    submits/resumes a Gemini batch job, and downloads results.
    """
    progress_update = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(bool, str)   # success, message/output_json_path
    batch_job_created = pyqtSignal(str)  # emits job.name immediately after creation

    def __init__(self, pdf_folder, json_filename, api_key,
                 extraction_prompt_path, batch_job_id="", save_dir="",
                 processing_mode="batch"):
        """
        processing_mode: "batch" or "one_by_one"
        """
        super().__init__()
        self.pdf_folder = pdf_folder
        self.json_filename = json_filename
        self.api_key = api_key
        self.extraction_prompt_path = extraction_prompt_path
        self.batch_job_id = batch_job_id
        self.save_dir = save_dir
        self.processing_mode = processing_mode

    def _output_path(self):
        if self.save_dir:
            return os.path.join(self.save_dir, self.json_filename)
        if self.pdf_folder:
            return os.path.join(os.path.dirname(self.pdf_folder), self.json_filename)
        return self.json_filename

    def run(self):
        try:
            client = genai.Client(api_key=self.api_key)
            output_json_path = self._output_path()

            # ── Resume existing job ──────────────────────────────────────────
            if self.batch_job_id:
                self.progress_update.emit(f"Resuming Batch Job: {self.batch_job_id}")
                job = client.batches.get(name=self.batch_job_id)
                self._download_job(job, client, output_json_path)
                return

            # ── Step 1: Clean PDFs ───────────────────────────────────────────
            self.progress_update.emit("Step 1/4: Cleaning PDFs...")
            folder_name = os.path.basename(self.pdf_folder)
            cleaned_folder = os.path.join(os.path.dirname(self.pdf_folder), f"Cleaned {folder_name}")

            cleaner = PDFCleaner()
            cleaner.clean_folder(
                self.pdf_folder, cleaned_folder,
                progress_callback=self.progress_update.emit,
                progress_value_callback=self.progress_value.emit
            )

            # ── Step 2: Upload & build JSONL ──────────────────────────────────
            self.progress_update.emit("\nStep 2/4: Uploading cleaned PDFs to Google File API...")

            with open(self.extraction_prompt_path, "r", encoding="utf-8") as f:
                extraction_prompt = f.read()

            cleaned_pdf_files = [f for f in os.listdir(cleaned_folder) if f.lower().endswith('.pdf')]
            
            jsonl_dir = self.save_dir if self.save_dir else os.path.dirname(self.pdf_folder)
            jsonl_path = os.path.join(jsonl_dir, "batch_requests.jsonl")

            # Load existing upload cache
            existing_requests = {}
            if os.path.exists(jsonl_path):
                try:
                    with open(jsonl_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                req = json.loads(line)
                                if "custom_id" in req:
                                    existing_requests[req["custom_id"]] = req
                    self.progress_update.emit(f"Found {len(existing_requests)} previously uploaded files in cache.")
                except Exception as e:
                    self.progress_update.emit(f"Warning: Could not read existing cache: {e}")

            requests_data = []
            for i, pdf_file in enumerate(cleaned_pdf_files):
                pdf_path = os.path.join(cleaned_folder, pdf_file)
                if pdf_file in existing_requests:
                    self.progress_update.emit(f"Skipping Upload ({i+1}/{len(cleaned_pdf_files)}): {pdf_file} (Already uploaded)")
                    requests_data.append(existing_requests[pdf_file])
                    self.progress_value.emit(20 + int((i + 1) / len(cleaned_pdf_files) * 30))
                    continue

                self.progress_update.emit(f"Uploading File API ({i+1}/{len(cleaned_pdf_files)}): {pdf_file}")
                try:
                    pdf_info = client.files.upload(
                        file=pdf_path,
                        config={"mime_type": "application/pdf", "display_name": pdf_file}
                    )
                    req = {
                        "custom_id": pdf_file,
                        "request": {
                            "contents": [
                                {"role": "user", "parts": [
                                    {"file_data": {"file_uri": pdf_info.uri, "mime_type": "application/pdf"}},
                                    {"text": extraction_prompt}
                                ]}
                            ]
                        }
                    }
                    requests_data.append(req)
                    existing_requests[pdf_file] = req
                    with open(jsonl_path, "w", encoding="utf-8") as f:
                        for r in requests_data:
                            f.write(json.dumps(r) + "\n")
                except Exception as e:
                    self.progress_update.emit(f"  ✗ File Upload Error: {str(e)}")

                self.progress_value.emit(20 + int((i + 1) / len(cleaned_pdf_files) * 30))
                time.sleep(1)

            # ── Step 3: Submit batch ─────────────────────────────────────────
            self.progress_update.emit("\nStep 3/4: Submitting Batch Generation Job...")
            jsonl_info = client.files.upload(
                file=jsonl_path,
                config={"mime_type": "application/jsonlines"}
            )
            job = client.batches.create(
                model="gemini-3-flash-preview",
                src=jsonl_info.name
            )
            self.progress_update.emit(f"✓ Batch Job Submitted! ID: {job.name}")
            # Immediately emit job ID so UI can save it before polling begins
            self.batch_job_created.emit(job.name)
            self._download_job(job, client, output_json_path)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))

    def _download_job(self, job, client, output_json_path):
        import requests as req_lib
        self.progress_update.emit("\nStep 4/4: Waiting for completion (typically 5–20 min)...")

        poll_count = 0
        while True:
            job_status = client.batches.get(name=job.name)
            state = str(job_status.state)
            if "SUCCEEDED" in state:
                self.progress_update.emit("\n✓ Batch processing done! Downloading output...")
                break
            elif "FAILED" in state or "CANCELLED" in state:
                raise Exception(f"Batch Job failed with state: {state}")
            else:
                poll_count += 30
                self.progress_update.emit(
                    f"Still polling... ({poll_count/60:.1f} min elapsed) | State: {state}"
                )
                self.progress_value.emit(50 + min(40, int(poll_count / 10)))
                time.sleep(180)

        self.progress_update.emit("Parsing and saving results...")
        headers = {"x-goog-api-key": self.api_key}
        api_res = req_lib.get(
            f"https://generativelanguage.googleapis.com/v1beta/{job.name}",
            headers=headers
        ).json()

        responses_file = api_res.get("response", {}).get("responsesFile")
        if not responses_file:
            raise Exception(f"Could not find responsesFile. Response: {str(api_res)}")

        output_jsonl_bytes = client.files.download(file=responses_file)
        output_jsonl = output_jsonl_bytes.decode('utf-8')

        results = {}
        for line in output_jsonl.splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            custom_id = data.get("custom_id")
            try:
                text = data["response"]["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip()
                for prefix in ("```json", "```"):
                    if text.startswith(prefix):
                        text = text[len(prefix):]
                if text.endswith("```"):
                    text = text[:-3]
                results[custom_id] = json.loads(text.strip())
            except Exception as e:
                results[custom_id] = {
                    "error": f"Failed to parse: {str(e)}",
                    "av_date": {"value": "not sure", "document_page": "not sure"},
                    "actuarial_return_rate": {"value": "not sure", "document_page": "not sure"},
                    "smoothing_years": {"value": "not sure", "document_page": "not sure"},
                    "actuarial_inflation_rate": {"value": "not sure", "document_page": "not sure"}
                }

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        self.progress_value.emit(100)
        self.progress_update.emit(f"\n✓ Processing complete! Results saved to: {output_json_path}")
        self.finished.emit(True, output_json_path)


class MergeThread(QThread):
    """Background thread for merging JSON data into Excel."""
    progress_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, excel_path, json_path):
        super().__init__()
        self.excel_path = excel_path
        self.json_path = json_path

    def run(self):
        try:
            self.progress_update.emit("Merging JSON data into Excel file...")
            merger = ExcelMerger(self.excel_path, self.json_path)
            updates_count, unmatched_count = merger.merge_data()
            msg = f"✓ Updated {updates_count} rows | {unmatched_count} unmatched entries"
            self.progress_update.emit(msg)
            self.finished.emit(True, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class FetchJobsThread(QThread):
    """
    Background thread: fetches all batch jobs from the Gemini API
    and emits them as a list of dicts.
    """
    finished = pyqtSignal(bool, list, str)  # success, jobs_list, error_msg

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            client = genai.Client(api_key=self.api_key)
            jobs = []
            for job in client.batches.list():
                jobs.append({
                    "name": job.name,
                    "state": str(job.state),
                    "create_time": str(getattr(job, 'create_time', '')),
                    "model": str(getattr(job, 'model', '')),
                })
            self.finished.emit(True, jobs, "")
        except Exception as e:
            self.finished.emit(False, [], str(e))


class CancelJobThread(QThread):
    """
    Background thread: cancels a running or pending batch job via the Gemini API.
    """
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, api_key: str, job_id: str):
        super().__init__()
        self.api_key = api_key
        self.job_id = job_id

    def run(self):
        try:
            client = genai.Client(api_key=self.api_key)
            client.batches.cancel(name=self.job_id)
            self.finished.emit(True, f"Job '{self.job_id}' cancelled successfully.")
        except Exception as e:
            self.finished.emit(False, str(e))


class FetchJobResultsThread(QThread):
    """
    Background thread: downloads results for a specific completed batch job.
    Reuses the same _download_job logic from ProcessingThread.
    """
    progress_update = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(bool, str)  # success, output_json_path or error

    def __init__(self, api_key: str, job_id: str, output_json_path: str):
        super().__init__()
        self.api_key = api_key
        self.job_id = job_id
        self.output_json_path = output_json_path

    def run(self):
        try:
            client = genai.Client(api_key=self.api_key)
            self.progress_update.emit(f"Fetching job: {self.job_id}")
            job = client.batches.get(name=self.job_id)
            self._download_job(job, client, self.output_json_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))

    def _download_job(self, job, client, output_json_path):
        import requests as req_lib
        self.progress_update.emit("Waiting for job completion (polling)...")

        poll_count = 0
        while True:
            job_status = client.batches.get(name=job.name)
            state = str(job_status.state)
            if "SUCCEEDED" in state:
                self.progress_update.emit("✓ Job complete! Downloading output...")
                break
            elif "FAILED" in state or "CANCELLED" in state:
                raise Exception(f"Batch Job failed with state: {state}")
            else:
                poll_count += 30
                self.progress_update.emit(
                    f"Still polling... ({poll_count/60:.1f} min elapsed) | State: {state}"
                )
                self.progress_value.emit(min(80, int(poll_count / 10)))
                time.sleep(180)

        self.progress_update.emit("Parsing and saving results...")
        headers = {"x-goog-api-key": self.api_key}
        api_res = req_lib.get(
            f"https://generativelanguage.googleapis.com/v1beta/{job.name}",
            headers=headers
        ).json()

        responses_file = api_res.get("response", {}).get("responsesFile")
        if not responses_file:
            raise Exception(f"Could not find responsesFile. Response: {str(api_res)}")

        output_jsonl_bytes = client.files.download(file=responses_file)
        output_jsonl = output_jsonl_bytes.decode('utf-8')

        results = {}
        for line in output_jsonl.splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            custom_id = data.get("custom_id")
            try:
                text = data["response"]["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip()
                for prefix in ("```json", "```"):
                    if text.startswith(prefix):
                        text = text[len(prefix):]
                if text.endswith("```"):
                    text = text[:-3]
                results[custom_id] = json.loads(text.strip())
            except Exception as e:
                results[custom_id] = {
                    "error": f"Failed to parse: {str(e)}",
                    "av_date": {"value": "not sure", "document_page": "not sure"},
                    "actuarial_return_rate": {"value": "not sure", "document_page": "not sure"},
                    "smoothing_years": {"value": "not sure", "document_page": "not sure"},
                    "actuarial_inflation_rate": {"value": "not sure", "document_page": "not sure"}
                }

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        self.progress_value.emit(100)
        self.progress_update.emit(f"✓ Results saved to: {output_json_path}")
        self.finished.emit(True, output_json_path)
