"""
ui/counter_check_tab.py
Counter-Check tab — fixed layout:
  - Top bar row 1: file/folder pickers + PDF selector
  - Top bar row 2: action buttons + zoom + page jump + layout toggle
  - Body: data grid (fixed height scroll area) above PDF viewer (expands)
  - Side-by-side toggle: left=PDF viewer, right=data grid
"""
import os
import json
import re
import platform
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QScrollArea, QGridLayout, QFrame,
    QFileDialog, QMessageBox, QSlider, QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QImage

try:
    import fitz
except ImportError:
    import pymupdf as fitz

from ui.dialogs import PDFViewChoiceDialog


class CounterCheckTab(QWidget):

    def __init__(self, session: dict, on_session_change, on_json_browsed=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.on_session_change = on_session_change
        self.on_json_browsed = on_json_browsed   # optional: () -> None

        # State
        self.json_file_path = ""
        self.pdf_directory = ""
        self.original_pdf_directory = ""
        self.pdf_data = {}
        self.zoom_level = 100
        self.current_pages = []
        self.highlight_terms = []
        self.highlight_values = []          # extracted values to highlight in PDF
        self.value_editors = {}
        self.doc_page_editors = {}
        self.actual_page_editors = {}
        self._last_viewed_pdf = None
        self._last_extra_label = ""
        self._side_by_side = False
        self._filter_pdf_keys = None
        self._problems_dict = {}            # {pdf_name: {field_name: {...}}}
        self._problems_for_pdf = set()      # field names with problems for current PDF

        self._init_ui()
        self._restore_from_session()

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _btn(text, color, size=11):
        b = QPushButton(text)
        b.setStyleSheet(
            f"padding: 6px 10px; font-size: {size}px; font-weight: bold;"
            f"background-color: {color}; color: white; border-radius: 4px;"
        )
        return b

    @staticmethod
    def _hsep():
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setFrameShadow(QFrame.Sunken)
        return f

    @staticmethod
    def _vsep():
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setFrameShadow(QFrame.Sunken)
        f.setFixedWidth(2)
        return f

    # ─────────────────────────────────────────────────────────────────────
    # UI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── ROW 1: file/folder pickers + PDF selector ─────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        json_btn = self._btn("Browse JSON", "#607D8B")
        json_btn.clicked.connect(self._browse_json)
        self.json_path_label = QLabel("No JSON loaded")
        self.json_path_label.setFont(QFont("Segoe UI", 10))
        self.json_path_label.setMaximumWidth(200)
        self.json_path_label.setToolTip("")

        mod_btn = self._btn("Modified PDF Folder", "#455A64")
        mod_btn.clicked.connect(self._browse_modified_folder)
        self.mod_folder_label = QLabel("Not set")
        self.mod_folder_label.setFont(QFont("Segoe UI", 10))
        self.mod_folder_label.setMaximumWidth(140)

        orig_btn = self._btn("Original PDF Folder", "#37474F")
        orig_btn.clicked.connect(self._browse_original_folder)
        self.orig_folder_label = QLabel("Not set")
        self.orig_folder_label.setFont(QFont("Segoe UI", 10))
        self.orig_folder_label.setMaximumWidth(140)

        pdf_lbl = QLabel("PDF:")
        pdf_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.pdf_dropdown = QComboBox()
        self.pdf_dropdown.setFont(QFont("Segoe UI", 11))
        self.pdf_dropdown.setMinimumWidth(260)
        self.pdf_dropdown.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pdf_dropdown.currentTextChanged.connect(self._update_data_display)

        # Filter box — narrows the dropdown list as you type
        self.pdf_filter_input = QLineEdit()
        self.pdf_filter_input.setPlaceholderText("Filter PDFs…")
        self.pdf_filter_input.setFixedWidth(150)
        self.pdf_filter_input.setFont(QFont("Segoe UI", 10))
        self.pdf_filter_input.setStyleSheet(
            "padding: 4px 6px; border: 1px solid #90A4AE; border-radius: 4px;")
        self.pdf_filter_input.textChanged.connect(self._apply_pdf_filter)
        filter_clear_btn = QPushButton("✕")
        filter_clear_btn.setFixedSize(24, 24)
        filter_clear_btn.setToolTip("Clear filter")
        filter_clear_btn.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #666; "
            "border: 1px solid #ccc; border-radius: 4px; padding: 0;")
        filter_clear_btn.clicked.connect(self.pdf_filter_input.clear)

        self.pdf_counter_label = QLabel("(0 of 0)")
        self.pdf_counter_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.pdf_counter_label.setStyleSheet("color: #1565C0;")

        prev_btn = self._btn("← Prev", "#7B1FA2")
        prev_btn.clicked.connect(self._prev_pdf)
        next_btn = self._btn("Next →", "#E65100")
        next_btn.clicked.connect(self._next_pdf)

        for w in [json_btn, self.json_path_label, self._vsep(),
                  mod_btn, self.mod_folder_label, self._vsep(),
                  orig_btn, self.orig_folder_label, self._vsep(),
                  pdf_lbl, self.pdf_filter_input, filter_clear_btn,
                  self.pdf_dropdown,
                  self.pdf_counter_label, prev_btn, next_btn]:
            row1.addWidget(w)
        root.addLayout(row1)
        root.addWidget(self._hsep())

        # ── ROW 2: actions + zoom + page jump + layout toggle ─────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        open_ext_btn = self._btn("📂 Open External", "#2E7D32", 12)
        open_ext_btn.clicked.connect(self._open_pdf_external)

        view_all_btn = self._btn("🖼 View All Pages", "#1565C0", 12)
        view_all_btn.clicked.connect(self._view_all_pages)

        row2.addWidget(open_ext_btn)
        row2.addWidget(view_all_btn)
        row2.addWidget(self._vsep())

        # Zoom
        zoom_lbl = QLabel("Zoom:")
        zoom_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setStyleSheet("padding: 5px 11px; font-size: 16px; font-weight: bold;")
        self.zoom_out_btn.setFixedWidth(36)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(50)
        self.zoom_slider.setMaximum(300)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.setTickInterval(25)
        self.zoom_slider.setTickPosition(QSlider.TicksBelow)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setStyleSheet("padding: 5px 11px; font-size: 16px; font-weight: bold;")
        self.zoom_in_btn.setFixedWidth(36)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_label = QLabel(f"{self.zoom_level}%")
        self.zoom_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.zoom_label.setFixedWidth(46)
        zoom_reset = QPushButton("Reset")
        zoom_reset.setStyleSheet("padding: 5px 8px; font-size: 11px;")
        zoom_reset.clicked.connect(self._reset_zoom)

        for w in [zoom_lbl, self.zoom_out_btn, self.zoom_slider,
                  self.zoom_in_btn, self.zoom_label, zoom_reset]:
            row2.addWidget(w)
        row2.addWidget(self._vsep())

        # Page jump
        jump_lbl = QLabel("Go to page:")
        jump_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.jump_input = QLineEdit()
        self.jump_input.setPlaceholderText("e.g. 5")
        self.jump_input.setFixedWidth(62)
        self.jump_input.setFont(QFont("Segoe UI", 11))
        self.jump_input.setStyleSheet(
            "padding: 4px; border: 2px solid #1565C0; border-radius: 4px;")
        self.jump_input.returnPressed.connect(self._jump_to_page)
        jump_btn = self._btn("↵ Go", "#1565C0", 11)
        jump_btn.setFixedWidth(52)
        jump_btn.clicked.connect(self._jump_to_page)
        self.jump_total_lbl = QLabel("/ —")
        self.jump_total_lbl.setFont(QFont("Segoe UI", 11))
        self.jump_total_lbl.setStyleSheet("color: #555;")

        for w in [jump_lbl, self.jump_input, self.jump_total_lbl, jump_btn]:
            row2.addWidget(w)
        row2.addWidget(self._vsep())

        # Layout toggle
        self.layout_toggle_btn = self._btn("⧉ Side-by-Side", "#6A1B9A", 12)
        self.layout_toggle_btn.clicked.connect(self._toggle_layout)
        row2.addWidget(self.layout_toggle_btn)

        row2.addStretch()
        root.addLayout(row2)
        root.addWidget(self._hsep())

        # ── BODY ────────────────────────────────────────────────────────
        # We use a QSplitter that is VERTICAL by default (stacked)
        # and switches to HORIZONTAL for side-by-side.
        # Top/Left pane  = data grid (in a scroll area, fixed max height in stacked)
        # Bottom/Right   = PDF viewer scroll area

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        # ── Data pane ─────────────────────────────────────────────────
        self._data_scroll = QScrollArea()
        self._data_scroll.setWidgetResizable(True)
        self._data_scroll.setFrameShape(QFrame.NoFrame)

        self._data_widget = QWidget()
        self._data_layout = QGridLayout(self._data_widget)
        self._data_layout.setColumnStretch(0, 2)
        self._data_layout.setColumnStretch(1, 3)
        self._data_layout.setColumnStretch(2, 1)
        self._data_layout.setColumnStretch(3, 1)
        self._data_layout.setColumnStretch(4, 2)
        self._data_layout.setVerticalSpacing(4)
        self._data_layout.setHorizontalSpacing(8)
        self._data_layout.setAlignment(Qt.AlignTop)
        self._data_scroll.setWidget(self._data_widget)
        # Give the data pane a sensible max height in stacked mode
        self._data_scroll.setMaximumHeight(280)
        self._data_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        # ── PDF viewer pane ────────────────────────────────────────────
        self._pdf_scroll = QScrollArea()
        self._pdf_scroll.setWidgetResizable(True)
        self._pdf_scroll.setFrameShape(QFrame.StyledPanel)
        self._pdf_content = QWidget()
        self._pdf_layout = QVBoxLayout(self._pdf_content)
        self._pdf_layout.setAlignment(Qt.AlignTop)
        self._pdf_layout.setSpacing(4)
        self._pdf_scroll.setWidget(self._pdf_content)
        self._pdf_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._splitter.addWidget(self._data_scroll)
        self._splitter.addWidget(self._pdf_scroll)
        self._splitter.setSizes([240, 600])

        root.addWidget(self._splitter, 1)

    # ─────────────────────────────────────────────────────────────────────
    # LAYOUT TOGGLE
    # ─────────────────────────────────────────────────────────────────────
    def _toggle_layout(self):
        self._side_by_side = not self._side_by_side

        if self._side_by_side:
            self._splitter.setOrientation(Qt.Horizontal)
            # In side-by-side, remove the max height so data can grow vertically
            self._data_scroll.setMaximumHeight(16777215)
            self._splitter.setSizes([700, 380])
            self.layout_toggle_btn.setText("☰ Stacked (Revert)")
            self.layout_toggle_btn.setStyleSheet(
                "padding: 6px 10px; font-size: 12px; font-weight: bold;"
                "background-color: #4E342E; color: white; border-radius: 4px;")
        else:
            self._splitter.setOrientation(Qt.Vertical)
            self._data_scroll.setMaximumHeight(280)
            self._splitter.setSizes([240, 600])
            self.layout_toggle_btn.setText("⧉ Side-by-Side")
            self.layout_toggle_btn.setStyleSheet(
                "padding: 6px 10px; font-size: 12px; font-weight: bold;"
                "background-color: #6A1B9A; color: white; border-radius: 4px;")

    # ─────────────────────────────────────────────────────────────────────
    # SESSION
    # ─────────────────────────────────────────────────────────────────────
    def _restore_from_session(self):
        json_file = self.session.get("json_file", "")
        if json_file:
            self._load_json(json_file)
        mod = self.session.get("cleaned_pdf_folder", "")
        if mod:
            self.pdf_directory = mod
            self.mod_folder_label.setText(os.path.basename(mod))
            self.mod_folder_label.setToolTip(mod)
        orig = self.session.get("original_pdf_folder", "")
        if orig:
            self.original_pdf_directory = orig
            self.orig_folder_label.setText(os.path.basename(orig))
            self.orig_folder_label.setToolTip(orig)

    # ─────────────────────────────────────────────────────────────────────
    # JSON LOADING
    # ─────────────────────────────────────────────────────────────────────
    def _load_json(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.pdf_data = json.load(f)
            self.json_file_path = path
            self.json_path_label.setText(os.path.basename(path))
            self.json_path_label.setToolTip(path)
            self._refresh_dropdown()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load JSON:\n{e}")

    def _refresh_dropdown(self):
        self.pdf_dropdown.blockSignals(True)
        self.pdf_dropdown.clear()
        keys = list(self.pdf_data.keys())
        if self._filter_pdf_keys is not None:
            keys = [k for k in keys if k in self._filter_pdf_keys]
        self.pdf_dropdown.addItems(keys)
        self.pdf_dropdown.blockSignals(False)
        self._update_pdf_counter()
        self._update_data_display()

    def _update_pdf_counter(self):
        idx = self.pdf_dropdown.currentIndex()
        total = self.pdf_dropdown.count()
        self.pdf_counter_label.setText(
            f"({idx+1} of {total})" if total > 0 else "(0 of 0)")

    # ─────────────────────────────────────────────────────────────────────
    # PDF PATH HELPERS
    # ─────────────────────────────────────────────────────────────────────
    def _get_modified_pdf_path(self):
        sel = self.pdf_dropdown.currentText()
        if not sel:
            return None
        if not self.pdf_directory:
            QMessageBox.warning(self, "Folder Not Set",
                                "Please set the Modified PDF folder first.")
            return None
        p = os.path.join(self.pdf_directory, sel)
        if not os.path.exists(p):
            QMessageBox.warning(self, "File Not Found",
                                f"Modified PDF not found:\n{p}")
            return None
        return p

    def _get_original_pdf_path(self):
        sel = self.pdf_dropdown.currentText()
        if not sel:
            return None
        if not self.original_pdf_directory:
            QMessageBox.warning(self, "Folder Not Set",
                                "Please set the Original PDF folder first.")
            return None
        p = os.path.join(self.original_pdf_directory, sel)
        if not os.path.exists(p):
            QMessageBox.warning(self, "File Not Found",
                                f"Original PDF not found:\n{p}")
            return None
        return p

    def _extract_search_terms(self, field_name: str):
        keywords = {
            'return_rate': ['return'], 'inflation': ['inflation'],
            'smoothing': ['smooth', 'smoothing'], 'discount_rate': ['discount'],
            'mortality': ['mortality'], 'salary': ['salary'],
            'withdrawal': ['withdrawal'], 'contribution': ['contribution'],
            'interest': ['interest'], 'benefit': ['benefit'],
            'pension': ['pension'], 'actuarial': ['actuarial'],
            'assumption': ['assumption'],
        }
        fl = field_name.lower()
        for key, terms in keywords.items():
            if key in fl:
                return terms
        return [w.lower() for w in field_name.replace('_', ' ').split() if len(w) > 3]

    # ─────────────────────────────────────────────────────────────────────
    # SLOTS: NAVIGATION
    # ─────────────────────────────────────────────────────────────────────
    def _browse_json(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select JSON File", "", "JSON Files (*.json)")
        if f:
            # Reset any filter/problems state carried over from the Verify tab
            self._filter_pdf_keys = None
            self._problems_dict   = {}
            self._problems_for_pdf = set()
            self._load_json(f)
            self.session["json_file"] = f
            self.on_session_change()
            # Notify main app so it can reset the Verify tab's results
            if self.on_json_browsed:
                self.on_json_browsed()

    def _browse_modified_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Modified PDF Folder")
        if d:
            self.pdf_directory = d
            self.mod_folder_label.setText(os.path.basename(d))
            self.mod_folder_label.setToolTip(d)
            self.session["cleaned_pdf_folder"] = d
            self.on_session_change()

    def _browse_original_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Original PDF Folder")
        if d:
            self.original_pdf_directory = d
            self.orig_folder_label.setText(os.path.basename(d))
            self.orig_folder_label.setToolTip(d)
            self.session["original_pdf_folder"] = d
            self.on_session_change()

    def _prev_pdf(self):
        i = self.pdf_dropdown.currentIndex()
        if i > 0:
            self.pdf_dropdown.setCurrentIndex(i - 1)

    def _next_pdf(self):
        i = self.pdf_dropdown.currentIndex()
        if i < self.pdf_dropdown.count() - 1:
            self.pdf_dropdown.setCurrentIndex(i + 1)

    # ─────────────────────────────────────────────────────────────────────
    # DATA GRID
    # ─────────────────────────────────────────────────────────────────────
    def _update_data_display(self):
        self._update_pdf_counter()
        # Clear data grid
        while self._data_layout.count():
            item = self._data_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Clear PDF viewer
        self._clear_pdf_viewer()

        self.current_pages = []
        self.highlight_terms = []
        self.highlight_values = []
        self.value_editors = {}
        self.doc_page_editors = {}
        self.actual_page_editors = {}

        selected = self.pdf_dropdown.currentText()
        if not selected or not self.pdf_data:
            return

        # Collect problem fields for this PDF
        self._problems_for_pdf = set(
            self._problems_dict.get(selected, {}).keys()
        )

        data = self.pdf_data.get(selected, {})

        # Header row
        h_style = ("font-weight: bold; font-size: 12px; "
                   "background-color: #CFD8DC; padding: 4px 6px;")
        header_labels = ["Field", "Value", "Doc Page", "PDF Page", "Actions"]
        for col, txt in enumerate(header_labels):
            lbl = QLabel(txt)
            lbl.setStyleSheet(h_style)
            lbl.setFixedHeight(28)
            self._data_layout.addWidget(lbl, 0, col)

        row = 1
        alt_colors = ["#FFFFFF", "#F5F5F5"]
        for field_name, field_data in data.items():
            is_problem = field_name in self._problems_for_pdf

            # Problem rows get a vivid amber background; normal rows alternate
            if is_problem:
                bg = "#FFF3E0"
                row_border = "border-left: 4px solid #E65100;"
            else:
                bg = alt_colors[row % 2]
                row_border = ""

            # ── Column 0: Field label (with ⚠ badge for problems) ──────────
            field_container = QWidget()
            field_container.setStyleSheet(
                f"background:{bg}; {row_border} padding: 1px;"
            )
            field_h = QHBoxLayout(field_container)
            field_h.setContentsMargins(2, 0, 2, 0)
            field_h.setSpacing(4)

            fl = QLabel(field_name.replace('_', ' ').title() + ":")
            fl.setFont(QFont("Segoe UI", 10, QFont.Bold))
            fl.setStyleSheet(
                f"color: {'#BF360C' if is_problem else '#212121'}; background: transparent;"
            )
            field_h.addWidget(fl)

            if is_problem:
                problem_info = self._problems_dict.get(selected, {}).get(field_name, {})
                issue_text = problem_info.get('issue', 'Problem') if isinstance(problem_info, dict) else str(problem_info)

                warn_btn = QPushButton("⚠")
                warn_btn.setFixedSize(22, 22)
                warn_btn.setToolTip(f"⚠ Problem: {issue_text}")
                warn_btn.setStyleSheet(
                    "background-color: #E65100; color: white; "
                    "font-size: 12px; font-weight: bold; border-radius: 3px; "
                    "padding: 0px;"
                )
                ap_val = field_data.get('actual_pdf_page', '') if isinstance(field_data, dict) else ''
                if ap_val and str(ap_val).lower() != 'not sure':
                    warn_btn.clicked.connect(
                        lambda _, p=ap_val, fn=field_name: self._view_single_page(p, fn)
                    )
                else:
                    warn_btn.setEnabled(False)
                    warn_btn.setToolTip(f"⚠ {issue_text}\n(Page unknown — cannot navigate)")
                field_h.addWidget(warn_btn)

            field_h.addStretch()
            self._data_layout.addWidget(field_container, row, 0)

            # ── Column 1: Value editor ──────────────────────────────────────
            val = field_data.get('value', '') if isinstance(field_data, dict) else str(field_data)
            ve = QLineEdit(str(val))
            ve.setFont(QFont("Segoe UI", 10))
            border_style = "border: 2px solid #E65100;" if is_problem else ""
            ve.setStyleSheet(f"background:{bg}; {border_style}")
            self.value_editors[field_name] = ve
            self._data_layout.addWidget(ve, row, 1)

            # ── Column 2: Document page editor ─────────────────────────────
            dp = field_data.get('document_page', '') if isinstance(field_data, dict) else ''
            de = QLineEdit(str(dp))
            de.setFont(QFont("Segoe UI", 10))
            de.setStyleSheet(f"background:{bg};")
            self.doc_page_editors[field_name] = de
            self._data_layout.addWidget(de, row, 2)

            # ── Column 3: Actual PDF page editor ───────────────────────────
            ap = field_data.get('actual_pdf_page', '') if isinstance(field_data, dict) else ''
            ae = QLineEdit(str(ap))
            ae.setFont(QFont("Segoe UI", 10))
            ae.setStyleSheet(f"background:{bg};")
            self.actual_page_editors[field_name] = ae
            self._data_layout.addWidget(ae, row, 3)

            # ── Column 4: Action buttons ────────────────────────────────────
            act_w = QWidget()
            act_w.setStyleSheet(f"background:{bg};")
            act_h = QHBoxLayout(act_w)
            act_h.setSpacing(4)
            act_h.setContentsMargins(2, 1, 2, 1)

            upd = QPushButton("Update")
            upd.setStyleSheet("padding: 4px 8px; font-size: 11px; font-weight: bold; "
                              "background-color: #2E7D32; color: white; border-radius: 3px;")
            upd.clicked.connect(lambda _, fn=field_name: self._update_field_value(fn))
            act_h.addWidget(upd)

            view = QPushButton("View")
            view.setStyleSheet("padding: 4px 8px; font-size: 11px; font-weight: bold; "
                               "background-color: #1565C0; color: white; border-radius: 3px;")
            if isinstance(field_data, dict) and ap and ap != 'not sure':
                view.clicked.connect(
                    lambda _, p=ap, fn=field_name: self._view_single_page(p, fn))
            else:
                view.setEnabled(False)
            act_h.addWidget(view)

            self._data_layout.addWidget(act_w, row, 4)
            row += 1

    # ─────────────────────────────────────────────────────────────────────
    # FIELD SAVE
    # ─────────────────────────────────────────────────────────────────────
    def _update_field_value(self, field_name: str):
        sel = self.pdf_dropdown.currentText()
        if not sel:
            return
        ve = self.value_editors.get(field_name)
        if not ve:
            return
        de = self.doc_page_editors.get(field_name)
        ae = self.actual_page_editors.get(field_name)

        entry = self.pdf_data.get(sel, {}).get(field_name)
        if entry is None:
            return

        if not isinstance(entry, dict):
            self.pdf_data[sel][field_name] = {"value": ve.text().strip()}
        else:
            entry['value'] = ve.text().strip()
            if de and de.text().strip():
                entry['document_page'] = de.text().strip()
            if ae and ae.text().strip():
                entry['actual_pdf_page'] = ae.text().strip()

        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.pdf_data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Saved", f"✓ Updated '{field_name}'")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    # ─────────────────────────────────────────────────────────────────────
    # PDF VIEWING
    # ─────────────────────────────────────────────────────────────────────
    def _clear_pdf_viewer(self):
        while self._pdf_layout.count():
            item = self._pdf_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _view_single_page(self, page_num, field_name: str):
        pdf_path = self._get_modified_pdf_path()
        if not pdf_path:
            return
        try:
            idx = int(str(page_num).strip()) - 1
        except ValueError:
            QMessageBox.warning(self, "Error", f"Bad page number: {page_num}")
            return
        self.highlight_terms = self._extract_search_terms(field_name)

        # Also highlight the actual extracted value for this field
        selected = self.pdf_dropdown.currentText()
        field_data = self.pdf_data.get(selected, {}).get(field_name, {})
        val = field_data.get('value', '') if isinstance(field_data, dict) else ''
        self.highlight_values = [str(val).strip()] if val and str(val).lower() not in ('', 'not sure') else []

        self._clear_pdf_viewer()
        self._last_viewed_pdf = pdf_path
        self._last_extra_label = "Modified"
        self.current_pages = [idx + 1]
        self._update_jump_total(pdf_path)
        self._render_page(pdf_path, idx, extra_label="Modified")

    def _view_all_pages(self):
        sel = self.pdf_dropdown.currentText()
        if not sel or not self.pdf_data:
            return
        data = self.pdf_data.get(sel, {})
        pages, all_terms, all_values = set(), set(), set()
        for fn, fd in data.items():
            if not isinstance(fd, dict):
                continue
            pg = fd.get('actual_pdf_page')
            if pg and pg != 'not sure':
                try:
                    pages.add(int(pg))
                    all_terms.update(self._extract_search_terms(fn))
                    val = fd.get('value', '')
                    if val and str(val).lower() not in ('', 'not sure'):
                        all_values.add(str(val).strip())
                except ValueError:
                    pass

        if not pages:
            QMessageBox.information(self, "No Pages",
                                    "No valid page numbers found for this entry.")
            return

        dlg = PDFViewChoiceDialog(parent=self)
        if not dlg.exec_():
            return

        self._clear_pdf_viewer()
        self.highlight_terms = list(all_terms)
        self.highlight_values = list(all_values)

        if dlg.choice == "modified":
            pdf_path = self._get_modified_pdf_path()
            if not pdf_path:
                return
            self._last_viewed_pdf = pdf_path
            self._last_extra_label = "Modified"
            self.current_pages = sorted(pages)
            self._update_jump_total(pdf_path)
            for p in self.current_pages:
                self._render_page(pdf_path, p - 1, extra_label="Modified")
        else:
            pdf_path = self._get_original_pdf_path()
            if not pdf_path:
                return
            try:
                doc = fitz.open(str(pdf_path))
                total = len(doc)
                doc.close()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cannot open original PDF:\n{e}")
                return
            self._last_viewed_pdf = pdf_path
            self._last_extra_label = "Original"
            self.current_pages = list(range(1, total + 1))
            self._update_jump_total(pdf_path)
            for p in self.current_pages:
                self._render_page(pdf_path, p - 1, extra_label="Original")

    def _open_pdf_external(self):
        dlg = PDFViewChoiceDialog(parent=self)
        if not dlg.exec_():
            return
        pdf_path = (self._get_modified_pdf_path() if dlg.choice == "modified"
                    else self._get_original_pdf_path())
        if not pdf_path:
            return
        try:
            if platform.system() == 'Windows':
                subprocess.Popen(['start', '', str(pdf_path)], shell=True)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(pdf_path)])
            else:
                subprocess.Popen(['xdg-open', str(pdf_path)])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open PDF:\n{e}")

    # ─────────────────────────────────────────────────────────────────────
    # PAGE JUMP
    # ─────────────────────────────────────────────────────────────────────
    def _update_jump_total(self, pdf_path: str):
        try:
            doc = fitz.open(str(pdf_path))
            total = len(doc)
            doc.close()
            self.jump_total_lbl.setText(f"/ {total}")
        except Exception:
            self.jump_total_lbl.setText("/ —")

    def _jump_to_page(self):
        text = self.jump_input.text().strip()
        if not text:
            return
        try:
            target = int(text)
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Please enter a valid page number.")
            return

        # Search for the title label with that page number
        for i in range(self._pdf_layout.count()):
            w = self._pdf_layout.itemAt(i).widget()
            if isinstance(w, QLabel):
                m = re.search(r'Page\s+(\d+)', w.text())
                if m and int(m.group(1)) == target:
                    QTimer.singleShot(30, lambda widget=w:
                                      self._pdf_scroll.ensureWidgetVisible(widget))
                    return

        QMessageBox.information(self, "Not Rendered",
                                f"Page {target} is not currently loaded.\n"
                                "Click 'View All Pages' first.")

    # ─────────────────────────────────────────────────────────────────────
    # RENDERING
    # ─────────────────────────────────────────────────────────────────────
    def _render_page(self, pdf_path: str, page_index: int, extra_label: str = ""):
        try:
            doc = fitz.open(str(pdf_path))
            if page_index < 0 or page_index >= len(doc):
                raise ValueError(f"Page {page_index+1} out of range ({len(doc)} pages).")

            page = doc[page_index]

            # ── Yellow highlights: field keywords ─────────────────────────
            terms = [t for t in self.highlight_terms if 'date' not in t]
            for term in terms:
                hits = page.search_for(
                    term,
                    flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
                for r in hits:
                    h = page.add_highlight_annot(r)
                    h.set_colors(stroke=(1, 1, 0))   # yellow
                    h.update()

            # ── Orange highlights: extracted values ────────────────────────
            for val_str in self.highlight_values:
                if not val_str or val_str.lower() == 'not sure':
                    continue
                hits = page.search_for(
                    val_str,
                    flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
                for r in hits:
                    h = page.add_highlight_annot(r)
                    h.set_colors(stroke=(1, 0.5, 0))   # orange
                    h.update()

            zoom = 2 * (self.zoom_level / 100)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height,
                         pix.stride, QImage.Format_RGB888)
            doc.close()

            title_parts = [f"Page {page_index+1}"]
            if extra_label:
                title_parts.insert(0, f"[{extra_label}]")
            if terms:
                title_parts.append(f"(Keywords: {', '.join(terms)})")
            if self.highlight_values:
                title_parts.append(f"(Values: {', '.join(self.highlight_values)})")
            title_text = "  ".join(title_parts)

            lbl_title = QLabel(title_text)
            lbl_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet(
                "margin-top: 6px; padding: 3px 8px; color: #1565C0; "
                "background:#E3F2FD; border-radius: 3px;")
            self._pdf_layout.addWidget(lbl_title)

            lbl_img = QLabel()
            pixmap = QPixmap.fromImage(img)
            max_w = int(780 * (self.zoom_level / 100))
            scaled = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)
            lbl_img.setPixmap(scaled)
            lbl_img.setAlignment(Qt.AlignCenter)
            self._pdf_layout.addWidget(lbl_img)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
            self._pdf_layout.addWidget(sep)

        except Exception as e:
            err = QLabel(f"❌ Error on page {page_index+1}: {e}")
            err.setStyleSheet("color: red; font-size: 12px; padding: 4px;")
            self._pdf_layout.addWidget(err)

    # ─────────────────────────────────────────────────────────────────────
    # PDF DROPDOWN FILTER
    # ─────────────────────────────────────────────────────────────────────
    def _apply_pdf_filter(self, text: str):
        """Filter the PDF dropdown to only show entries matching `text`."""
        query = text.strip().lower()
        all_keys = list(self.pdf_data.keys())
        if self._filter_pdf_keys is not None:
            all_keys = [k for k in all_keys if k in self._filter_pdf_keys]
        matches = [k for k in all_keys if query in k.lower()] if query else all_keys
        self.pdf_dropdown.blockSignals(True)
        self.pdf_dropdown.clear()
        self.pdf_dropdown.addItems(matches)
        self.pdf_dropdown.blockSignals(False)
        self._update_pdf_counter()
        self._update_data_display()

    # ─────────────────────────────────────────────────────────────────────
    # ZOOM
    # ─────────────────────────────────────────────────────────────────────
    def _zoom_in(self):
        self.zoom_slider.setValue(min(self.zoom_slider.value() + 10, 300))

    def _zoom_out(self):
        self.zoom_slider.setValue(max(self.zoom_slider.value() - 10, 50))

    def _reset_zoom(self):
        self.zoom_slider.setValue(100)

    def _on_zoom_changed(self, value):
        self.zoom_level = value
        self.zoom_label.setText(f"{value}%")
        if self.current_pages and self._last_viewed_pdf:
            self._clear_pdf_viewer()
            for p in self.current_pages:
                self._render_page(self._last_viewed_pdf, p - 1,
                                  extra_label=self._last_extra_label)

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────
    def load_json_and_filter(self, json_file: str, filter_keys: dict | None = None):
        """Called from the Verify tab's Counter Check button.
        filter_keys is the problems dict: {pdf_name: {field_name: {...}}}
        """
        if filter_keys is not None:
            self._filter_pdf_keys = set(filter_keys.keys())
            self._problems_dict   = filter_keys          # remember per-field problems
        else:
            self._filter_pdf_keys = None
            self._problems_dict   = {}
        self._problems_for_pdf = set()
        if json_file:
            self._load_json(json_file)

    def set_json_file(self, path: str):
        self._filter_pdf_keys = None
        self._problems_dict   = {}
        self._problems_for_pdf = set()
        self._load_json(path)
        self.session["json_file"] = path
        self.on_session_change()

    def set_modified_folder(self, path: str):
        """Push the cleaned/modified PDF folder into this tab without overriding user selection."""
        if path and path != self.pdf_directory:
            self.pdf_directory = path
            self.mod_folder_label.setText(os.path.basename(path))
            self.mod_folder_label.setToolTip(path)

    def set_original_folder(self, path: str):
        """Push the original PDF folder into this tab without overriding user selection."""
        if path and path != self.original_pdf_directory:
            self.original_pdf_directory = path
            self.orig_folder_label.setText(os.path.basename(path))
            self.orig_folder_label.setToolTip(path)

