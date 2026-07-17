"""
ui/dialogs.py
Shared dialogs used across the application:
  - SessionDialog : ask user to continue or start a new session
  - PDFViewChoiceDialog : ask user whether to view modified or original PDF
  - ProcessingModeDialog : ask user to choose batch vs one-by-one
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QButtonGroup, QRadioButton, QGroupBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


# ─────────────────────────────────────────────────────────────────────────────
class SessionDialog(QDialog):
    """
    Shown on startup.
    Result: dialog.choice == "continue" or "new"
    """
    def __init__(self, parent=None, has_previous=False):
        super().__init__(parent)
        self.choice = "new"
        self.setWindowTitle("Session Manager")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.setSpacing(16)

        title = QLabel("📂 Session Manager")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        if has_previous:
            desc = QLabel(
                "A previous session was found.\n"
                "Would you like to continue where you left off\n"
                "or start a fresh session?"
            )
        else:
            desc = QLabel("No previous session found.\nStarting a new session.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setFont(QFont("Segoe UI", 11))
        layout.addWidget(desc)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        if has_previous:
            continue_btn = QPushButton("▶  Continue Previous Session")
            continue_btn.setStyleSheet(
                "padding: 12px 20px; font-size: 13px; font-weight: bold;"
                "background-color: #1976D2; color: white; border-radius: 6px;"
            )
            continue_btn.clicked.connect(self._continue)
            btn_layout.addWidget(continue_btn)

        new_btn = QPushButton("✦  Start New Session")
        new_btn.setStyleSheet(
            "padding: 12px 20px; font-size: 13px; font-weight: bold;"
            "background-color: #388E3C; color: white; border-radius: 6px;"
        )
        new_btn.clicked.connect(self._new)
        btn_layout.addWidget(new_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        if not has_previous:
            self.choice = "new"

    def _continue(self):
        self.choice = "continue"
        self.accept()

    def _new(self):
        self.choice = "new"
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
class PDFViewChoiceDialog(QDialog):
    """
    Shown when user clicks "View PDF" in the counter-check tab.
    Result: dialog.choice == "modified" or "original"
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = "modified"
        self.setWindowTitle("Select PDF Version")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout()
        layout.setSpacing(14)

        title = QLabel("📄 Which PDF version would you like to view?")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        mod_btn = QPushButton("🔹  View Modified (Cleaned) PDF")
        mod_btn.setStyleSheet(
            "padding: 12px 20px; font-size: 13px; font-weight: bold;"
            "background-color: #0288D1; color: white; border-radius: 6px;"
        )
        mod_btn.clicked.connect(self._modified)

        orig_btn = QPushButton("🔸  View Original (Unmodified) PDF")
        orig_btn.setStyleSheet(
            "padding: 12px 20px; font-size: 13px; font-weight: bold;"
            "background-color: #F57C00; color: white; border-radius: 6px;"
        )
        orig_btn.clicked.connect(self._original)

        layout.addWidget(mod_btn)
        layout.addWidget(orig_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 8px; font-size: 12px; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        self.setLayout(layout)

    def _modified(self):
        self.choice = "modified"
        self.accept()

    def _original(self):
        self.choice = "original"
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
class ProcessingModeDialog(QDialog):
    """
    Lets the user choose between Batch Processing and One-by-One Processing.
    Result: dialog.mode == "batch" or "one_by_one"
    """
    def __init__(self, current_mode="batch", parent=None):
        super().__init__(parent)
        self.mode = current_mode
        self.setWindowTitle("Processing Mode")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.setSpacing(14)

        title = QLabel("⚙  Select Processing Mode")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        group_box = QGroupBox("Mode")
        group_layout = QVBoxLayout()

        self.batch_radio = QRadioButton(
            "🚀  Batch Processing  (Recommended — submit all PDFs at once via API)"
        )
        self.batch_radio.setFont(QFont("Segoe UI", 11))
        self.one_by_one_radio = QRadioButton(
            "📄  One-by-One Processing  (Process each PDF individually)"
        )
        self.one_by_one_radio.setFont(QFont("Segoe UI", 11))

        if current_mode == "batch":
            self.batch_radio.setChecked(True)
        else:
            self.one_by_one_radio.setChecked(True)

        group_layout.addWidget(self.batch_radio)
        group_layout.addWidget(self.one_by_one_radio)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

        ok_btn = QPushButton("Confirm")
        ok_btn.setStyleSheet(
            "padding: 10px 24px; font-size: 13px; font-weight: bold;"
            "background-color: #1565C0; color: white; border-radius: 6px;"
        )
        ok_btn.clicked.connect(self._confirm)
        layout.addWidget(ok_btn, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def _confirm(self):
        self.mode = "batch" if self.batch_radio.isChecked() else "one_by_one"
        self.accept()
