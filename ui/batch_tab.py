"""
ui/batch_tab.py
The "Batch Processing" tab UI.
Handles: PDF folder selection, batch job submission/resumption,
         processing mode toggle, Excel merge, Previous Jobs browser,
         and cross-tab auto-fill of paths.
"""
import os
import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QLineEdit, QTextEdit, QProgressBar,
                             QFileDialog, QMessageBox, QGroupBox, QFrame,
                             QComboBox, QDialog, QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from core.batch_processor import ProcessingThread, MergeThread
from ui.dialogs import ProcessingModeDialog
from ui.previous_jobs_dialog import PreviousJobsDialog

# Default fallback values (used when session has no saved value)
_DEFAULT_API_KEY = ""

if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(sys.executable)
else:
    _base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_DEFAULT_PROMPT_PATH = os.path.join(_base_dir, "Extraction_Prompt Updated.txt")


class ApiSettingsDialog(QDialog):
    """Popup dialog for entering API key and selecting the extraction prompt file."""

    def __init__(self, api_key: str, prompt_path: str, api_model: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API & Extraction Settings")
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~
                            Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Title ─────────────────────────────────────────────────────────
        title = QLabel("API & Extraction Settings")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        # ── API Key field ──────────────────────────────────────────────────
        self.api_key_edit = QLineEdit(api_key)
        self.api_key_edit.setPlaceholderText("Paste your Gemini API key here…")
        self.api_key_edit.setFont(QFont("Consolas", 10))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMinimumWidth(340)

        show_btn = QPushButton("👁")
        show_btn.setFixedWidth(32)
        show_btn.setCheckable(True)
        show_btn.setToolTip("Show / hide key")
        show_btn.setStyleSheet(
            "padding: 2px; border: 1px solid #aaa; border-radius: 3px;")
        show_btn.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )

        api_row = QHBoxLayout()
        api_row.addWidget(self.api_key_edit)
        api_row.addWidget(show_btn)

        api_widget = QWidget()
        api_widget.setLayout(api_row)
        form.addRow("API Key:", api_widget)

        # ── Prompt file field ──────────────────────────────────────────────
        self.prompt_edit = QLineEdit(prompt_path)
        self.prompt_edit.setPlaceholderText(
            "Path to extraction prompt .txt file…")
        self.prompt_edit.setFont(QFont("Segoe UI", 9))
        self.prompt_edit.setReadOnly(True)
        self.prompt_edit.setMinimumWidth(300)

        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet(
            "padding: 5px 10px; background-color: #37474F; color: white; border-radius: 4px;"
        )
        browse_btn.clicked.connect(self._browse_prompt)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(self.prompt_edit)
        prompt_row.addWidget(browse_btn)

        prompt_widget = QWidget()
        prompt_widget.setLayout(prompt_row)
        form.addRow("Extraction Prompt:", prompt_widget)

        # ── Model selection field ──────────────────────────────────────────
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gemini-3.5-flash",
            "gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ])
        self.model_combo.setEditable(True)
        self.model_combo.setFont(QFont("Segoe UI", 9))
        self.model_combo.setMinimumWidth(300)

        idx = self.model_combo.findText(api_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(api_model)

        form.addRow("Model:", self.model_combo)

        layout.addLayout(form)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setStyleSheet(
            "padding: 7px 18px; background-color: #1565C0; color: white; border-radius: 4px; font-weight: bold;"
        )
        btn_box.button(QDialogButtonBox.Cancel).setStyleSheet(
            "padding: 7px 18px; border-radius: 4px;"
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _browse_prompt(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Extraction Prompt File",
            os.path.dirname(self.prompt_edit.text()) or os.getcwd(),
            "Text Files (*.txt);;All Files (*.*)"
        )
        if file:
            self.prompt_edit.setText(file)

    @property
    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    @property
    def prompt_path(self) -> str:
        return self.prompt_edit.text().strip()

    @property
    def api_model(self) -> str:
        return self.model_combo.currentText().strip()


class BatchTab(QWidget):
    """Tab widget for batch PDF processing and Excel merging."""

    # Signals forwarded to main window for cross-tab coordination
    json_produced = None   # set by MainWindow after construction

    def __init__(self, session: dict, on_session_change, parent=None):
        super().__init__(parent)
        self.session = session
        self.on_session_change = on_session_change
        self.processing_mode = session.get("processing_mode", "batch")
        # Ensure API key and prompt path are populated with defaults if absent
        if not self.session.get("api_key"):
            self.session["api_key"] = _DEFAULT_API_KEY
        if not self.session.get("extraction_prompt_path"):
            self.session["extraction_prompt_path"] = _DEFAULT_PROMPT_PATH
        if not self.session.get("api_model"):
            self.session["api_model"] = "gemini-3.5-flash"
        self._init_ui()
        self._restore_from_session()

    # ── UI construction ────────────────────────────────────────────────────
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Processing mode row ──────────────────────────────────────────
        mode_row = QHBoxLayout()
        mode_label = QLabel("Processing Mode:")
        mode_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.mode_display = QLabel(self._mode_text())
        self.mode_display.setFont(QFont("Segoe UI", 11))
        self.mode_display.setStyleSheet("color: #1565C0; font-weight: bold;")
        mode_change_btn = QPushButton("⚙ Change Mode")
        mode_change_btn.setStyleSheet(
            "padding: 6px 14px; font-size: 12px; background-color: #546E7A; color: white; border-radius: 4px;"
        )
        mode_change_btn.clicked.connect(self._change_mode)

        api_settings_btn = QPushButton("🔑 API Settings")
        api_settings_btn.setStyleSheet(
            "padding: 6px 14px; font-size: 12px; background-color: #1565C0; color: white; border-radius: 4px;"
        )
        api_settings_btn.setToolTip(
            "Configure API key and extraction prompt file")
        api_settings_btn.clicked.connect(self._open_api_settings)

        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_display)
        mode_row.addStretch()
        mode_row.addWidget(api_settings_btn)
        mode_row.addWidget(mode_change_btn)
        layout.addLayout(mode_row)

        layout.addWidget(self._separator())

        # ── Step 1: PDF Folder ────────────────────────────────────────────
        step1_group = QGroupBox("Step 1 — Select PDF Folder")
        step1_group.setFont(QFont("Segoe UI", 11, QFont.Bold))
        step1_layout = QHBoxLayout()
        self.pdf_label = QLabel("No folder selected")
        self.pdf_label.setFont(QFont("Segoe UI", 10))
        pdf_btn = QPushButton("Browse PDF Folder")
        pdf_btn.clicked.connect(self._browse_pdf_folder)
        pdf_btn.setStyleSheet(
            "padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        step1_layout.addWidget(self.pdf_label, 1)
        step1_layout.addWidget(pdf_btn)
        step1_group.setLayout(step1_layout)
        layout.addWidget(step1_group)

        # ── Step 2: JSON filename ─────────────────────────────────────────
        step2_group = QGroupBox("Step 2 — JSON Output Filename")
        step2_group.setFont(QFont("Segoe UI", 11, QFont.Bold))
        step2_layout = QHBoxLayout()
        step2_layout.addWidget(QLabel("Filename:"))
        self.json_input = QLineEdit("Extracted_Data_Batch_API.json")
        self.json_input.setFont(QFont("Segoe UI", 10))
        self.json_input.textChanged.connect(self._on_json_filename_changed)
        step2_layout.addWidget(self.json_input)
        step2_group.setLayout(step2_layout)
        layout.addWidget(step2_group)

        # ── Optional: Resume job ─────────────────────────────────────────
        resume_group = QGroupBox("Optional — Resume Existing Batch Job")
        resume_group.setFont(QFont("Segoe UI", 11, QFont.Bold))
        resume_layout = QHBoxLayout()
        resume_layout.addWidget(QLabel("Job ID:"))
        self.job_id_input = QLineEdit()
        self.job_id_input.setPlaceholderText(
            "e.g. batches/123456789  (leave empty for new job)")
        self.job_id_input.setFont(QFont("Segoe UI", 10))
        resume_layout.addWidget(self.job_id_input)

        prev_jobs_btn = QPushButton("📋 Previous Jobs")
        prev_jobs_btn.setStyleSheet(
            "padding: 7px 14px; font-size: 12px; font-weight: bold;"
            "background-color: #6A1B9A; color: white; border-radius: 4px;"
        )
        prev_jobs_btn.clicked.connect(self._open_previous_jobs)
        resume_layout.addWidget(prev_jobs_btn)

        resume_group.setLayout(resume_layout)
        layout.addWidget(resume_group)

        # ── Process button + progress ─────────────────────────────────────
        self.process_btn = QPushButton("🚀 Process PDFs & Extract Data")
        self.process_btn.setStyleSheet(
            "padding: 12px; font-size: 14px; font-weight: bold;"
            "background-color: #1565C0; color: white; border-radius: 6px;"
        )
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self._process_pdfs)
        layout.addWidget(self.process_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        log_label = QLabel("Processing Log:")
        log_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(log_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMinimumHeight(130)
        layout.addWidget(self.log_text)

        layout.addWidget(self._separator())

        # ── Step 3: Excel merge ────────────────────────────────────────────
        step3_group = QGroupBox("Step 3 — Merge Data to Excel")
        step3_group.setFont(QFont("Segoe UI", 11, QFont.Bold))
        step3_layout = QVBoxLayout()

        json_row = QHBoxLayout()
        self.json_file_label = QLabel("No JSON file selected")
        self.json_file_label.setFont(QFont("Segoe UI", 10))
        json_file_btn = QPushButton("Browse JSON File")
        json_file_btn.clicked.connect(self._browse_json_file)
        json_file_btn.setStyleSheet(
            "padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        json_row.addWidget(self.json_file_label, 1)
        json_row.addWidget(json_file_btn)
        step3_layout.addLayout(json_row)

        excel_row = QHBoxLayout()
        self.excel_label = QLabel("No Excel file selected")
        self.excel_label.setFont(QFont("Segoe UI", 10))
        excel_btn = QPushButton("Browse Excel File")
        excel_btn.clicked.connect(self._browse_excel_file)
        excel_btn.setStyleSheet(
            "padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        excel_row.addWidget(self.excel_label, 1)
        excel_row.addWidget(excel_btn)
        step3_layout.addLayout(excel_row)

        self.merge_btn = QPushButton("📊 Merge JSON Data to Excel")
        self.merge_btn.setStyleSheet(
            "padding: 12px; font-size: 14px; font-weight: bold;"
            "background-color: #2E7D32; color: white; border-radius: 6px;"
        )
        self.merge_btn.setEnabled(False)
        self.merge_btn.clicked.connect(self._merge_to_excel)
        step3_layout.addWidget(self.merge_btn)

        step3_group.setLayout(step3_layout)
        layout.addWidget(step3_group)

    # ── Helpers ────────────────────────────────────────────────────────────
    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    def _mode_text(self):
        if self.processing_mode == "batch":
            return "🚀  Batch Processing"
        return "📄  One-by-One Processing"

    def _derive_cleaned_folder(self, pdf_folder: str) -> str:
        """Compute the expected cleaned folder path from a raw PDF folder path."""
        folder_name = os.path.basename(pdf_folder)
        parent = os.path.dirname(pdf_folder)
        return os.path.join(parent, f"Cleaned {folder_name}")

    def _restore_from_session(self):
        pdf_folder = self.session.get("pdf_folder", "")
        if pdf_folder:
            self.pdf_folder = pdf_folder
            self.pdf_label.setText(os.path.basename(pdf_folder))
            self.process_btn.setEnabled(True)
        else:
            self.pdf_folder = ""

        json_fn = self.session.get("json_output_filename", "")
        if json_fn:
            self.json_input.setText(json_fn)

        job_id = self.session.get("batch_job_id", "")
        if job_id:
            self.job_id_input.setText(job_id)

        json_file = self.session.get("json_file", "")
        if json_file:
            self.json_file = json_file
            self.json_file_label.setText(os.path.basename(json_file))
        else:
            self.json_file = ""

        # Auto-populate merge JSON if we have a json_output_filename
        if not json_file and json_fn:
            computed = os.path.join(_base_dir, json_fn)
            if os.path.exists(computed):
                self._set_merge_json(computed)

        excel_file = self.session.get("excel_file", "")
        if excel_file:
            self.excel_file = excel_file
            self.excel_label.setText(os.path.basename(excel_file))
        else:
            self.excel_file = ""

        self._check_merge_btn()

    # ── Slots ───────────────────────────────────────────────────────────────
    def _change_mode(self):
        dlg = ProcessingModeDialog(
            current_mode=self.processing_mode, parent=self)
        if dlg.exec_():
            self.processing_mode = dlg.mode
            self.mode_display.setText(self._mode_text())
            self.session["processing_mode"] = self.processing_mode
            self.on_session_change()

    def _browse_pdf_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select PDF Folder")
        if folder:
            self._apply_pdf_folder(folder)

    def _apply_pdf_folder(self, folder: str):
        """Set the PDF folder and propagate derived paths to session for cross-tab sync."""
        self.pdf_folder = folder
        self.pdf_label.setText(os.path.basename(folder))
        self.process_btn.setEnabled(True)
        self.log_text.append(f"Selected PDF folder: {folder}\n")

        cleaned = self._derive_cleaned_folder(folder)
        self.session["pdf_folder"] = folder
        self.session["original_pdf_folder"] = folder
        self.session["cleaned_pdf_folder"] = cleaned
        self.on_session_change()

        # Also pre-populate the merge JSON if a filename is typed
        self._sync_merge_json_from_folder(folder)

    def _on_json_filename_changed(self, text: str):
        """When the user changes the output filename, update the merge JSON field."""
        if getattr(self, 'pdf_folder', ''):
            self._sync_merge_json_from_folder(self.pdf_folder)

    def _sync_merge_json_from_folder(self, folder: str):
        """Compute and auto-fill the merge JSON path from directory."""
        json_fn = self.json_input.text().strip() or "Extracted_Data_Batch_API.json"
        computed = os.path.join(_base_dir, json_fn)
        # Always set the expected output path so the merge section is pre-filled
        self._set_merge_json(computed)

    def _set_merge_json(self, path: str):
        """Set the merge section's JSON file to the given path."""
        self.json_file = path
        self.json_file_label.setText(os.path.basename(path))
        self.session["json_file"] = path
        self._check_merge_btn()

    def _browse_json_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)")
        if file:
            self._set_merge_json(file)
            self.log_text.append(f"Selected JSON file: {file}\n")
            self.on_session_change()

    def _browse_excel_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)")
        if file:
            self.excel_file = file
            self.excel_label.setText(os.path.basename(file))
            self._check_merge_btn()
            self.log_text.append(f"Selected Excel file: {file}\n")
            self.session["excel_file"] = file
            self.on_session_change()

    def _check_merge_btn(self):
        self.merge_btn.setEnabled(
            bool(getattr(self, 'json_file', '')) and bool(
                getattr(self, 'excel_file', ''))
        )

    def _open_api_settings(self):
        """Open the API & Extraction Settings popup."""
        dlg = ApiSettingsDialog(
            api_key=self.session.get("api_key", _DEFAULT_API_KEY),
            prompt_path=self.session.get(
                "extraction_prompt_path", _DEFAULT_PROMPT_PATH),
            api_model=self.session.get("api_model", "gemini-3.5-flash"),
            parent=self
        )
        if dlg.exec_():
            self.session["api_key"] = dlg.api_key
            self.session["extraction_prompt_path"] = dlg.prompt_path
            self.session["api_model"] = dlg.api_model
            self.on_session_change()
            self.log_text.append(
                f"✓ Settings saved — prompt: {os.path.basename(dlg.prompt_path)} | model: {dlg.api_model}\n"
            )

    def _open_previous_jobs(self):
        dlg = PreviousJobsDialog(api_key=self.session.get(
            "api_key", _DEFAULT_API_KEY), parent=self)
        if dlg.exec_() == PreviousJobsDialog.Accepted:
            if dlg.selected_job_id:
                self.job_id_input.setText(dlg.selected_job_id)
                self.session["batch_job_id"] = dlg.selected_job_id
                self.on_session_change()
                self.log_text.append(
                    f"Job ID loaded from Previous Jobs: {dlg.selected_job_id}\n")
            if dlg.result_json_path:
                self._set_merge_json(dlg.result_json_path)
                self.session["json_file"] = dlg.result_json_path
                self.on_session_change()
                self.log_text.append(
                    f"Results downloaded to: {dlg.result_json_path}\n")
                QMessageBox.information(
                    self, "Results Loaded",
                    f"Results have been loaded into the merge section:\n{dlg.result_json_path}"
                )

    def _process_pdfs(self):
        job_id = self.job_id_input.text().strip()
        api_key = self.session.get("api_key", _DEFAULT_API_KEY)
        prompt_path = self.session.get(
            "extraction_prompt_path", _DEFAULT_PROMPT_PATH)
        api_model = self.session.get("api_model", "gemini-3.5-flash")

        if not getattr(self, 'pdf_folder', '') and not job_id:
            QMessageBox.warning(
                self, "Warning", "Please select a PDF folder or enter a Batch Job ID.")
            return
        if not api_key:
            QMessageBox.warning(
                self, "Warning", "Please set your API key via the 🔑 API Settings button.")
            return
        if not job_id and not os.path.exists(prompt_path):
            QMessageBox.warning(self, "Warning",
                                f"Extraction prompt file not found:\n{prompt_path}\n\n"
                                "Please set the correct path via 🔑 API Settings.")
            return

        self.process_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        json_filename = self.json_input.text() or "Extracted_Data_Batch_API.json"
        save_dir = _base_dir

        # Pre-populate expected output path immediately so cross-tab sync has it
        expected_output = os.path.join(save_dir, json_filename)
        self._set_merge_json(expected_output)

        self.session["batch_job_id"] = job_id
        self.session["json_output_filename"] = json_filename
        self.on_session_change()

        self._thread = ProcessingThread(
            getattr(self, 'pdf_folder', ''), json_filename, api_key,
            prompt_path, job_id, save_dir, self.processing_mode, api_model
        )
        self._thread.progress_update.connect(self._update_log)
        self._thread.progress_value.connect(self.progress_bar.setValue)
        self._thread.batch_job_created.connect(self._on_batch_job_created)
        self._thread.finished.connect(self._processing_finished)
        self._thread.start()

    def _on_batch_job_created(self, job_id: str):
        """Called immediately when a new batch job is submitted — save ID before polling."""
        self.job_id_input.setText(job_id)
        self.session["batch_job_id"] = job_id
        self.on_session_change()
        self.log_text.append(f"✓ Job ID saved: {job_id}\n")

    def _processing_finished(self, success, message):
        self.process_btn.setEnabled(True)
        if success:
            self._set_merge_json(message)
            self.session["json_file"] = message
            self.on_session_change()
            QMessageBox.information(
                self, "Success", "Processing completed successfully!")
        else:
            QMessageBox.critical(
                self, "Error", f"Processing failed:\n{message}")

    def _merge_to_excel(self):
        if not getattr(self, 'json_file', '') or not getattr(self, 'excel_file', ''):
            QMessageBox.warning(
                self, "Warning", "Please select both a JSON file and an Excel file.")
            return
        self.merge_btn.setEnabled(False)
        self.log_text.append("\n" + "="*50 + "\n")
        self._merge_thread = MergeThread(self.excel_file, self.json_file)
        self._merge_thread.progress_update.connect(self._update_log)
        self._merge_thread.finished.connect(self._merge_finished)
        self._merge_thread.start()

    def _merge_finished(self, success, message):
        self.merge_btn.setEnabled(True)
        if success:
            QMessageBox.information(
                self, "Success", f"Merge completed!\n{message}")
        else:
            QMessageBox.critical(self, "Error", f"Merge failed:\n{message}")

    def _update_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())

    # ── Public API for cross-tab use ────────────────────────────────────────
    def get_json_file(self) -> str:
        return getattr(self, 'json_file', '')

    def set_json_file(self, path: str):
        """Called from other tabs to set the active JSON file."""
        self._set_merge_json(path)
