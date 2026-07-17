"""
ui/previous_jobs_dialog.py
Dialog to browse, select, and retrieve results from previous Gemini Batch API jobs.
Fetches jobs dynamically from the API using FetchJobsThread.
"""
import os
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
                              QAbstractItemView, QProgressBar, QTextEdit,
                              QFileDialog, QMessageBox, QGroupBox, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core.batch_processor import FetchJobsThread, FetchJobResultsThread, CancelJobThread


class PreviousJobsDialog(QDialog):
    """
    Shows all previous Gemini Batch API jobs fetched live from the API.
    User can select a job to:
      - Load its ID into the batch tab's Job ID field.
      - Download its results to a chosen JSON file.
    """

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.selected_job_id = None   # set when user clicks "Use This Job"
        self.result_json_path = None  # set when results are downloaded
        self._jobs = []
        self._fetch_thread = None
        self._result_thread = None
        self._cancel_thread = None

        self.setWindowTitle("📋 Previous Batch Jobs")
        self.setModal(True)
        self.setMinimumSize(900, 580)
        self._init_ui()
        self._fetch_jobs()

    # ── UI ────────────────────────────────────────────────────────────────
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title = QLabel("📋 Previous Gemini Batch API Jobs")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Select a job, then use the buttons below to load its ID or download its results.")
        hint.setFont(QFont("Segoe UI", 10))
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #546E7A;")
        layout.addWidget(hint)

        # Loading bar
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)   # indeterminate
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMaximumHeight(6)
        layout.addWidget(self.loading_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Job ID", "State", "Created At", "Model"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFont(QFont("Consolas", 9))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { border: 1px solid #B0BEC5; border-radius: 4px; }
            QTableWidget::item:selected { background-color: #1565C0; color: white; }
        """)
        layout.addWidget(self.table, 1)

        # Status label (row count / error)
        self.status_label = QLabel("Fetching jobs from API...")
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setStyleSheet("color: #37474F;")
        layout.addWidget(self.status_label)

        # ── Result download log ──────────────────────────────────────────
        result_group = QGroupBox("Result Download Log")
        result_group.setFont(QFont("Segoe UI", 10, QFont.Bold))
        rg_layout = QVBoxLayout()
        self.result_log = QTextEdit()
        self.result_log.setReadOnly(True)
        self.result_log.setFont(QFont("Consolas", 9))
        self.result_log.setMaximumHeight(110)
        self.result_progress = QProgressBar()
        self.result_progress.setValue(0)
        self.result_progress.setTextVisible(True)
        rg_layout.addWidget(self.result_log)
        rg_layout.addWidget(self.result_progress)
        result_group.setLayout(rg_layout)
        layout.addWidget(result_group)

        # ── Action buttons ───────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet(
            "padding: 9px 16px; font-size: 12px; font-weight: bold;"
            "background-color: #546E7A; color: white; border-radius: 5px;"
        )
        self.refresh_btn.clicked.connect(self._fetch_jobs)

        self.use_btn = QPushButton("✅ Use This Job ID")
        self.use_btn.setStyleSheet(
            "padding: 9px 16px; font-size: 12px; font-weight: bold;"
            "background-color: #1565C0; color: white; border-radius: 5px;"
        )
        self.use_btn.setEnabled(False)
        self.use_btn.clicked.connect(self._use_selected_job)

        self.get_results_btn = QPushButton("📥 Get Results of Selected Job")
        self.get_results_btn.setStyleSheet(
            "padding: 9px 16px; font-size: 12px; font-weight: bold;"
            "background-color: #2E7D32; color: white; border-radius: 5px;"
        )
        self.get_results_btn.setEnabled(False)
        self.get_results_btn.clicked.connect(self._get_results)

        self.cancel_btn = QPushButton("🚫 Cancel Job")
        self.cancel_btn.setStyleSheet(
            "padding: 9px 16px; font-size: 12px; font-weight: bold;"
            "background-color: #B71C1C; color: white; border-radius: 5px;"
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Cancel the selected job (only available for PENDING or RUNNING jobs)")
        self.cancel_btn.clicked.connect(self._cancel_selected_job)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "padding: 9px 16px; font-size: 12px; border-radius: 5px;"
        )
        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.use_btn)
        btn_row.addWidget(self.get_results_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    # ── API Fetch ─────────────────────────────────────────────────────────
    def _fetch_jobs(self):
        self.table.setRowCount(0)
        self.loading_bar.setRange(0, 0)
        self.status_label.setText("Fetching jobs from API...")
        self.refresh_btn.setEnabled(False)
        self.use_btn.setEnabled(False)
        self.get_results_btn.setEnabled(False)

        self._fetch_thread = FetchJobsThread(self.api_key)
        self._fetch_thread.finished.connect(self._on_jobs_fetched)
        self._fetch_thread.start()

    def _on_jobs_fetched(self, success: bool, jobs: list, error: str):
        self.loading_bar.setRange(0, 1)
        self.loading_bar.setValue(1)
        self.refresh_btn.setEnabled(True)

        if not success:
            self.status_label.setText(f"❌ Error fetching jobs: {error}")
            self.status_label.setStyleSheet("color: #C62828;")
            return

        self._jobs = jobs
        self.table.setRowCount(len(jobs))

        state_colors = {
            "SUCCEEDED": "#E8F5E9",
            "FAILED": "#FFEBEE",
            "CANCELLED": "#FFF8E1",
            "RUNNING": "#E3F2FD",
            "PENDING": "#F3E5F5",
        }

        for row, job in enumerate(jobs):
            job_id_item = QTableWidgetItem(job["name"])
            job_id_item.setToolTip(job["name"])

            state_str = job["state"].split(".")[-1]  # strip enum prefix
            state_item = QTableWidgetItem(state_str)
            state_item.setTextAlignment(Qt.AlignCenter)

            # Color-code state cell
            bg_color = next(
                (QColor(v) for k, v in state_colors.items() if k in state_str.upper()),
                QColor("#FFFFFF")
            )
            state_item.setBackground(bg_color)

            time_item = QTableWidgetItem(job["create_time"][:19] if job["create_time"] else "—")
            time_item.setTextAlignment(Qt.AlignCenter)

            model_item = QTableWidgetItem(job["model"].split("/")[-1] if job["model"] else "—")
            model_item.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row, 0, job_id_item)
            self.table.setItem(row, 1, state_item)
            self.table.setItem(row, 2, time_item)
            self.table.setItem(row, 3, model_item)

        self.status_label.setText(f"✓ {len(jobs)} job(s) found.")
        self.status_label.setStyleSheet("color: #2E7D32;")

    # ── Selection ─────────────────────────────────────────────────────────
    def _on_selection_changed(self):
        has_sel = bool(self.table.selectedItems())
        self.use_btn.setEnabled(has_sel)
        self.get_results_btn.setEnabled(has_sel)

        # Cancel is only valid for active (pending/running) jobs
        job = self._selected_job()
        if job:
            state_upper = job["state"].upper()
            is_active = "PENDING" in state_upper or "RUNNING" in state_upper
        else:
            is_active = False
        self.cancel_btn.setEnabled(is_active)

    def _selected_job(self) -> dict | None:
        rows = self.table.selectedItems()
        if not rows:
            return None
        row = self.table.currentRow()
        if 0 <= row < len(self._jobs):
            return self._jobs[row]
        return None

    # ── Actions ───────────────────────────────────────────────────────────
    def _use_selected_job(self):
        job = self._selected_job()
        if not job:
            return
        self.selected_job_id = job["name"]
        self.accept()   # closes dialog; caller reads self.selected_job_id

    def _cancel_selected_job(self):
        job = self._selected_job()
        if not job:
            return

        reply = QMessageBox.warning(
            self, "Cancel Job",
            f"Are you sure you want to cancel this job?\n\n{job['name']}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.cancel_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.use_btn.setEnabled(False)
        self.get_results_btn.setEnabled(False)
        self.status_label.setText("Cancelling job...")
        self.status_label.setStyleSheet("color: #B71C1C;")

        self._cancel_thread = CancelJobThread(self.api_key, job["name"])
        self._cancel_thread.finished.connect(self._on_cancel_done)
        self._cancel_thread.start()

    def _on_cancel_done(self, success: bool, message: str):
        self.refresh_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Job Cancelled", f"✓ {message}")
            self._fetch_jobs()   # refresh the list to show updated state
        else:
            self.status_label.setText(f"❌ Cancel failed: {message}")
            self.status_label.setStyleSheet("color: #C62828;")
            self.use_btn.setEnabled(True)
            self.get_results_btn.setEnabled(True)
            QMessageBox.critical(self, "Cancel Failed", f"Failed to cancel job:\n{message}")

    def _get_results(self):
        job = self._selected_job()
        if not job:
            return

        state_str = job["state"].upper()
        if "SUCCEEDED" not in state_str:
            reply = QMessageBox.question(
                self, "Job Not Complete",
                f"This job's state is: {state_str}\n\n"
                "It may not be finished yet. Try downloading anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Ask where to save — default to the exe's own folder (same as session.json)
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            _default_dir = os.path.dirname(_sys.executable)
        else:
            _default_dir = os.path.expanduser('~')

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Results JSON As",
            os.path.join(_default_dir, "Extracted_Data_Batch_API.json"),
            "JSON Files (*.json)"
        )
        if not out_path:
            return

        self.result_log.clear()
        self.result_progress.setValue(0)
        self.get_results_btn.setEnabled(False)
        self.use_btn.setEnabled(False)

        self._result_thread = FetchJobResultsThread(
            api_key=self.api_key,
            job_id=job["name"],
            output_json_path=out_path
        )
        self._result_thread.progress_update.connect(self._log_result)
        self._result_thread.progress_value.connect(self.result_progress.setValue)
        self._result_thread.finished.connect(
            lambda success, msg: self._on_result_done(success, msg, out_path)
        )
        self._result_thread.start()

    def _log_result(self, msg: str):
        self.result_log.append(msg)
        self.result_log.verticalScrollBar().setValue(
            self.result_log.verticalScrollBar().maximum()
        )

    def _on_result_done(self, success: bool, message: str, out_path: str):
        self.get_results_btn.setEnabled(True)
        self.use_btn.setEnabled(True)
        if success:
            self.result_json_path = out_path
            QMessageBox.information(
                self, "Results Downloaded",
                f"✓ Results saved to:\n{out_path}\n\n"
                "Close this dialog to load the results into the application."
            )
            self.selected_job_id = self._selected_job()["name"] if self._selected_job() else None
            self.accept()
        else:
            self._log_result(f"❌ Error: {message}")
            QMessageBox.critical(self, "Download Failed", f"Failed to download results:\n{message}")
