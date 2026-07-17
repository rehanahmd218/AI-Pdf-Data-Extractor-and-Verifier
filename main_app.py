"""
main_app.py
── Unified PDF Extraction & Verification System ──

Entry point. Manages:
  - Session dialog (continue / new session)
  - Main tabbed window with three tabs:
      Tab 0 - Batch Processing
      Tab 1 - Verify Results
      Tab 2 - Counter Check
  - Cross-tab coordination (passing JSON file between tabs)
  - Session persistence
"""
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget,
                              QStatusBar, QAction, QMessageBox)
from PyQt5.QtGui import QFont

from core.session import load_session, save_session, clear_session
from ui.dialogs import SessionDialog
from ui.batch_tab import BatchTab
from ui.verify_tab import VerifyTab
from ui.counter_check_tab import CounterCheckTab


class MainWindow(QMainWindow):
    """Main application window with three coordinated tabs."""

    def __init__(self, session: dict):
        super().__init__()
        self.session = session
        self._init_ui()
        self._connect_cross_tab_signals()

    def _init_ui(self):
        self.setWindowTitle("PDF Extraction & Verification System")
        self.setMinimumSize(1200, 800)

        # ── Tab widget ────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 11))
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)

        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #BDBDBD;
                border-radius: 4px;
                background: #FAFAFA;
            }
            QTabBar::tab {
                background: #ECEFF1;
                border: 1px solid #B0BEC5;
                padding: 10px 22px;
                font-size: 13px;
                font-weight: bold;
                min-width: 180px;
            }
            QTabBar::tab:selected {
                background: #1565C0;
                color: white;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #CFD8DC;
            }
        """)

        # Build tabs
        self.batch_tab = BatchTab(
            session=self.session,
            on_session_change=self._save_session
        )
        self.verify_tab = VerifyTab(
            session=self.session,
            on_session_change=self._save_session,
            on_open_counter_check=self._open_counter_check_from_verify
        )
        self.counter_tab = CounterCheckTab(
            session=self.session,
            on_session_change=self._save_session,
            on_json_browsed=self._on_counter_tab_json_browsed
        )

        self.tabs.addTab(self.batch_tab,    "🚀  Batch Processing")
        self.tabs.addTab(self.verify_tab,  "🔍  Verify Results")
        self.tabs.addTab(self.counter_tab, "✅  Counter Check")

        # Restore last active tab
        last_tab = self.session.get("last_tab", 0)
        self.tabs.setCurrentIndex(last_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tabs)

        # ── Status bar ────────────────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready  |  Session loaded.")

        # ── Menu bar ──────────────────────────────────────────────────────
        menu_bar = self.menuBar()
        session_menu = menu_bar.addMenu("Session")

        new_action = QAction("🆕  Start New Session", self)
        new_action.triggered.connect(self._new_session)
        session_menu.addAction(new_action)

        save_action = QAction("💾  Save Session Now", self)
        save_action.triggered.connect(lambda: (self._save_session(), self.status_bar.showMessage("Session saved.")))
        session_menu.addAction(save_action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    def _connect_cross_tab_signals(self):
        """Wire up cross-tab data sharing."""
        # When batch tab produces a JSON, propagate to verify + counter tabs
        # We poll via a simple mechanism: batch_tab calls on_session_change,
        # which triggers _sync_json_across_tabs
        pass  # handled in _save_session

    def _on_tab_changed(self, index: int):
        self.session["last_tab"] = index
        self._save_session()
        # Sync JSON file when switching to verify or counter-check
        self._sync_json_across_tabs()

    def _sync_json_across_tabs(self):
        """Ensure JSON file and folder paths are consistent across all tabs from session."""
        json_file = self.session.get("json_file", "")
        cleaned_folder = self.session.get("cleaned_pdf_folder", "")
        original_folder = self.session.get("original_pdf_folder", "")

        if json_file:
            # Sync verify tab
            if hasattr(self.verify_tab, 'json_file') and self.verify_tab.json_file != json_file:
                self.verify_tab.set_json_file(json_file)
            # Sync counter tab (without disturbing the filter state)
            if hasattr(self.counter_tab, 'json_file_path') and \
               self.counter_tab.json_file_path != json_file:
                pass  # counter tab loads independently; only force-load if no data

        # Sync PDF folder paths into verify tab and counter tab
        if cleaned_folder:
            if hasattr(self.verify_tab, 'set_pdf_folder'):
                self.verify_tab.set_pdf_folder(cleaned_folder)
            if hasattr(self.counter_tab, 'set_modified_folder'):
                self.counter_tab.set_modified_folder(cleaned_folder)

        if original_folder:
            if hasattr(self.counter_tab, 'set_original_folder'):
                self.counter_tab.set_original_folder(original_folder)

    def _open_counter_check_from_verify(self, json_file: str, problems: dict):
        """Called by VerifyTab 'Counter Check Selected' button."""
        self.counter_tab.load_json_and_filter(json_file, problems)
        self.tabs.setCurrentIndex(2)
        self.status_bar.showMessage(
            f"Counter Check loaded with {len(problems)} problem PDFs filtered."
        )

    def _on_counter_tab_json_browsed(self):
        """Called when the Counter Check tab browses a new JSON file manually.
        Resets the Verify tab results so stale data doesn't conflict."""
        self.verify_tab.reset_results()
        self.status_bar.showMessage(
            "New JSON loaded in Counter Check — Verify Results have been reset."
        )

    def _save_session(self):
        save_session(self.session)
        self._sync_json_across_tabs()

    def _new_session(self):
        reply = QMessageBox.question(
            self, "New Session",
            "This will clear the current session state.\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            clear_session()
            QMessageBox.information(self, "Session Cleared",
                                    "Session cleared. Please restart the application.")

    def _about(self):
        QMessageBox.about(
            self, "About",
            "<b>PDF Extraction & Verification System</b><br><br>"
            "Unified application combining:<br>"
            "• Batch PDF Processing & Extraction<br>"
            "• Automated Verification of Extracted Data<br>"
            "• Counter-Check with PDF Viewer (Original & Modified)<br><br>"
            "Modular architecture · Session persistence · Content-based page mapping"
        )

    def closeEvent(self, event):
        self._save_session()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Extraction & Verification System")
    app.setFont(QFont("Segoe UI", 10))

    # Apply a clean global stylesheet
    app.setStyleSheet("""
        QMainWindow {
            background-color: #F5F5F5;
        }
        QGroupBox {
            border: 1px solid #B0BEC5;
            border-radius: 6px;
            margin-top: 8px;
            padding: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            color: #1565C0;
        }
        QPushButton {
            border-radius: 4px;
        }
        QPushButton:disabled {
            background-color: #BDBDBD !important;
            color: #757575 !important;
        }
        QProgressBar {
            border: 1px solid #B0BEC5;
            border-radius: 4px;
            text-align: center;
            background: #E0E0E0;
        }
        QProgressBar::chunk {
            background-color: #1565C0;
            border-radius: 3px;
        }
        QTextEdit, QLineEdit {
            border: 1px solid #B0BEC5;
            border-radius: 4px;
            background: white;
        }
        QTreeWidget {
            border: 1px solid #B0BEC5;
            border-radius: 4px;
            background: white;
            alternate-background-color: #F5F5F5;
        }
    """)

    # ── Session handling ─────────────────────────────────────────────────
    session = load_session()
    has_previous = any([
        session.get("pdf_folder"),
        session.get("json_file"),
        session.get("excel_file"),
        session.get("cleaned_pdf_folder"),
    ])

    dlg = SessionDialog(has_previous=has_previous)
    dlg.exec_()   # Always show so user can choose

    if dlg.choice == "new":
        clear_session()
        session = load_session()   # fresh defaults

    window = MainWindow(session)
    window.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
