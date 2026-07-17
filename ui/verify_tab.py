"""
ui/verify_tab.py
The "Verify Results" tab UI.
Runs the verification engine against a JSON + PDF folder, shows results,
and lets users navigate verification problems in the counter-check tab.
"""
import os
import sys
import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QLineEdit, QTextEdit, QProgressBar,
                              QFileDialog, QMessageBox, QGroupBox, QFrame,
                              QTreeWidget, QTreeWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core.verifier import VerificationThread

if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(sys.executable)
else:
    _base_dir = os.getcwd()

_DEFAULT_OUTPUT_FILE = os.path.join(_base_dir, "verification_problems.json")



class VerifyTab(QWidget):
    """Tab widget for running verification of extracted data against PDFs."""

    def __init__(self, session: dict, on_session_change,
                 on_open_counter_check=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.on_session_change = on_session_change
        self.on_open_counter_check = on_open_counter_check   # callback(json_file, filter_keys)
        self._init_ui()
        self._restore_from_session()

    # ── UI construction ────────────────────────────────────────────────────
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Input group ───────────────────────────────────────────────────
        input_group = QGroupBox("Verification Inputs")
        input_group.setFont(QFont("Segoe UI", 11, QFont.Bold))
        ig_layout = QVBoxLayout()

        # JSON file
        json_row = QHBoxLayout()
        self.json_label = QLabel("No JSON file selected")
        self.json_label.setFont(QFont("Segoe UI", 10))
        json_btn = QPushButton("Browse JSON File")
        json_btn.clicked.connect(self._browse_json)
        json_btn.setStyleSheet("padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        json_row.addWidget(QLabel("JSON:"))
        json_row.addWidget(self.json_label, 1)
        json_row.addWidget(json_btn)
        ig_layout.addLayout(json_row)

        # PDF folder (cleaned)
        pdf_row = QHBoxLayout()
        self.pdf_label = QLabel("No folder selected")
        self.pdf_label.setFont(QFont("Segoe UI", 10))
        pdf_btn = QPushButton("Browse PDF Folder")
        pdf_btn.clicked.connect(self._browse_pdf)
        pdf_btn.setStyleSheet("padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        pdf_row.addWidget(QLabel("PDFs:"))
        pdf_row.addWidget(self.pdf_label, 1)
        pdf_row.addWidget(pdf_btn)
        ig_layout.addLayout(pdf_row)

        # Output file
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.output_input = QLineEdit(_DEFAULT_OUTPUT_FILE)
        self.output_input.setFont(QFont("Segoe UI", 10))
        out_browse_btn = QPushButton("Browse")
        out_browse_btn.clicked.connect(self._browse_output)
        out_browse_btn.setStyleSheet("padding: 7px 14px; background-color: #37474F; color: white; border-radius: 4px;")
        out_row.addWidget(self.output_input, 1)
        out_row.addWidget(out_browse_btn)
        ig_layout.addLayout(out_row)

        input_group.setLayout(ig_layout)
        layout.addWidget(input_group)

        # ── Verify button + progress ──────────────────────────────────────
        self.verify_btn = QPushButton("🔍 Run Verification")
        self.verify_btn.setStyleSheet(
            "padding: 12px; font-size: 14px; font-weight: bold;"
            "background-color: #1565C0; color: white; border-radius: 6px;"
        )
        self.verify_btn.setEnabled(False)
        self.verify_btn.clicked.connect(self._run_verification)
        layout.addWidget(self.verify_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        log_lbl = QLabel("Verification Log:")
        log_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(log_lbl)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumHeight(120)
        layout.addWidget(self.log_text)

        layout.addWidget(self._separator())

        # ── Results panel ─────────────────────────────────────────────────
        results_header = QHBoxLayout()
        results_lbl = QLabel("Verification Problems:")
        results_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.problem_count_lbl = QLabel("")
        self.problem_count_lbl.setFont(QFont("Segoe UI", 10))
        self.problem_count_lbl.setStyleSheet("color: #C62828; font-weight: bold;")

        self.counter_check_btn = QPushButton("🔁 Counter Check Selected")
        self.counter_check_btn.setStyleSheet(
            "padding: 8px 16px; font-size: 12px; font-weight: bold;"
            "background-color: #AD1457; color: white; border-radius: 5px;"
        )
        self.counter_check_btn.setEnabled(False)
        self.counter_check_btn.clicked.connect(self._open_counter_check)

        results_header.addWidget(results_lbl)
        results_header.addWidget(self.problem_count_lbl)
        results_header.addStretch()
        results_header.addWidget(self.counter_check_btn)
        layout.addLayout(results_header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["PDF / Field", "Issue"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setFont(QFont("Segoe UI", 10))
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

    # ── Helpers ────────────────────────────────────────────────────────────
    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    def _restore_from_session(self):
        json_file = self.session.get("json_file", "")
        if json_file:
            self.json_file = json_file
            self.json_label.setText(os.path.basename(json_file))
        else:
            self.json_file = ""

        pdf_folder = self.session.get("cleaned_pdf_folder") or self.session.get("pdf_folder", "")
        if pdf_folder:
            self.pdf_folder = pdf_folder
            self.pdf_label.setText(os.path.basename(pdf_folder))
        else:
            self.pdf_folder = ""

        out = self.session.get("verification_output_file", _DEFAULT_OUTPUT_FILE)
        self.output_input.setText(out)

        self._check_verify_btn()

        # Load existing problems if output file exists
        if os.path.exists(out):
            try:
                with open(out, 'r', encoding='utf-8') as f:
                    self._display_problems(json.load(f))
            except Exception:
                pass

    def _check_verify_btn(self):
        self.verify_btn.setEnabled(
            bool(getattr(self, 'json_file', '')) and bool(getattr(self, 'pdf_folder', ''))
        )

    # ── Slots ───────────────────────────────────────────────────────────────
    def _browse_json(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select JSON File", "", "JSON Files (*.json)")
        if file:
            self.json_file = file
            self.json_label.setText(os.path.basename(file))
            self.session["json_file"] = file
            self.on_session_change()
            self._check_verify_btn()

    def _browse_pdf(self):
        folder = QFileDialog.getExistingDirectory(self, "Select PDF Folder (Cleaned)")
        if folder:
            self.pdf_folder = folder
            self.pdf_label.setText(os.path.basename(folder))
            self.session["cleaned_pdf_folder"] = folder
            self.on_session_change()
            self._check_verify_btn()

    def _browse_output(self):
        file, _ = QFileDialog.getSaveFileName(self, "Output File", "verification_problems.json", "JSON Files (*.json)")
        if file:
            self.output_input.setText(file)
            self.session["verification_output_file"] = file
            self.on_session_change()

    def _run_verification(self):
        if not getattr(self, 'json_file', '') or not getattr(self, 'pdf_folder', ''):
            QMessageBox.warning(self, "Warning", "Please select a JSON file and a PDF folder.")
            return

        output_file = self.output_input.text().strip() or _DEFAULT_OUTPUT_FILE
        self.session["verification_output_file"] = output_file
        self.on_session_change()

        self.verify_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.tree.clear()
        self.counter_check_btn.setEnabled(False)

        self._vthread = VerificationThread(self.json_file, self.pdf_folder, output_file)
        self._vthread.progress_update.connect(self._update_log)
        self._vthread.progress_value.connect(self.progress_bar.setValue)
        self._vthread.finished.connect(self._verification_done)
        self._vthread.start()

    def _verification_done(self, success, message, problems):
        self.verify_btn.setEnabled(True)
        self._update_log(message)
        if success:
            self._display_problems(problems)
            if problems:
                self.counter_check_btn.setEnabled(True)
            QMessageBox.information(self, "Verification Complete", message)
        else:
            QMessageBox.critical(self, "Error", f"Verification failed:\n{message}")

    def _display_problems(self, problems: dict):
        self.tree.clear()
        self._problems = problems
        total_issues = 0
        for pdf_name, fields in problems.items():
            pdf_item = QTreeWidgetItem(self.tree, [pdf_name, ""])
            pdf_item.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
            pdf_item.setBackground(0, QColor("#FFECB3"))
            for field_name, info in fields.items():
                issue = info.get("issue", "") if isinstance(info, dict) else str(info)
                child = QTreeWidgetItem(pdf_item, [f"  {field_name}", issue])
                child.setForeground(1, QColor("#C62828"))
                total_issues += 1
            pdf_item.setExpanded(True)

        self.problem_count_lbl.setText(f"({total_issues} issues in {len(problems)} PDFs)")
        if problems:
            self.counter_check_btn.setEnabled(True)

    def _open_counter_check(self):
        if self.on_open_counter_check and hasattr(self, '_problems'):
            self.on_open_counter_check(
                self.session.get("json_file", ""),
                self._problems
            )

    def _update_log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    # ── Public API ──────────────────────────────────────────────────────────
    def set_json_file(self, path: str):
        self.json_file = path
        self.json_label.setText(os.path.basename(path))
        self._check_verify_btn()

    def set_pdf_folder(self, path: str):
        """Push a PDF folder (cleaned) into this tab without overriding user selection."""
        if path and path != getattr(self, 'pdf_folder', ''):
            self.pdf_folder = path
            self.pdf_label.setText(os.path.basename(path))
            self._check_verify_btn()

    def reset_results(self):
        """Clear all verification results (called when counter-check tab browses a new JSON)."""
        self.tree.clear()
        self._problems = {}
        self.problem_count_lbl.setText("")
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.counter_check_btn.setEnabled(False)
