import sys
import time
import os
import configparser
import requests
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QProgressBar, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor

# -------- Configuration (from config.ini with fallback) --------
# Default values (exactly your original hard-coded defaults)
DEFAULT_APP_TITLE = "MediaCMS Video Details Editor"
DEFAULT_API_URL = "https://demo.mediacms.io/api/v1/media/"
DEFAULT_USERNAME = "MediaCMSTest"
DEFAULT_PASSWORD = "Pn@32jGufq9@^HT^A$sG"

config = configparser.ConfigParser()
_config_path = os.path.join(os.path.dirname(__file__), "config.ini") if "__file__" in globals() else "config.ini"

config_found = False
try:
    if os.path.exists(_config_path):
        config.read(_config_path)
        config_found = True
except Exception:
    config_found = False

if config_found and config.has_section("prefs"):
    APP_TITLE = config.get("prefs", "app_title", fallback=DEFAULT_APP_TITLE)
else:
    APP_TITLE = DEFAULT_APP_TITLE

if config_found and config.has_section("auth"):
    API_URL = config.get("auth", "api_url", fallback=DEFAULT_API_URL)
    USERNAME = config.get("auth", "username", fallback=DEFAULT_USERNAME)
    PASSWORD = config.get("auth", "password", fallback=DEFAULT_PASSWORD)
else:
    API_URL = DEFAULT_API_URL
    USERNAME = DEFAULT_USERNAME
    PASSWORD = DEFAULT_PASSWORD
# ----------------------------------------------------------------

video_data = {}  # token -> {title, description, staged_title, staged_description, api_url}


# -------- Robust Request Helper --------
def robust_request(method, url, retries=3, backoff=1, **kwargs):
    """
    Wrapper for requests with retries on DNS/connection errors.
    method: 'get' or 'put'
    retries: total attempts (default 3)
    backoff: base seconds for exponential backoff (1 => 1s,2s,4s)
    """
    last_err = None
    m = method.lower()
    for attempt in range(1, retries + 1):
        try:
            if m == "get":
                return requests.get(url, **kwargs)
            elif m == "put":
                return requests.put(url, **kwargs)
            else:
                raise ValueError("Unsupported method")
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < retries:
                # exponential backoff: backoff * 2^(attempt-1)
                time.sleep(backoff * (2 ** (attempt - 1)))
    # out of retries -> raise last error to be handled by caller
    raise last_err
# ---------------------------------------


# =============== Worker Threads ===============

class FetchThread(QThread):
    fetched = Signal(list)
    error = Signal(str)

    def run(self):
        all_items = []
        url = API_URL
        try:
            while url:
                # use robust_request to handle transient DNS/connection issues
                resp = robust_request("get", url, auth=(USERNAME, PASSWORD))
                if resp.status_code != 200:
                    self.error.emit(f"Failed to fetch media: {resp.status_code}")
                    return
                data = resp.json()
                for item in data.get("results", []):
                    token = item["friendly_token"]
                    video_data[token] = {
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "staged_title": None,
                        "staged_description": None,
                        # store api_url if provided by the API (older working version uses this)
                        "api_url": item.get("api_url")
                    }
                    all_items.append((token, item.get("title", ""), item.get("description", "")))
                url = data.get("next")
            self.fetched.emit(all_items)
        except Exception as e:
            self.error.emit(str(e))


class PushThread(QThread):
    done = Signal()
    error = Signal(str)

    def __init__(self, tokens):
        super().__init__()
        self.tokens = tokens

    def run(self):
        try:
            for token in self.tokens:
                d = video_data.get(token)
                if not d:
                    # defensive: token disappeared
                    self.error.emit(f"No data for token {token}")
                    continue

                # Determine which URL to PUT to:
                # Prefer the api_url returned by the API (older working code used this).
                url = d.get("api_url")
                if not url:
                    # fallback: try a sensible REST-style URL (no /update/ suffix).
                    url = f"{API_URL}{token}/"

                if not url:
                    self.error.emit(f"No API URL available for {token}")
                    continue

                payload = {
                    "title": d["staged_title"] if d["staged_title"] is not None else d["title"],
                    "description": d["staged_description"] if d["staged_description"] is not None else d["description"]
                }

                try:
                    # use robust_request for PUT as well
                    resp = robust_request("put", url, auth=(USERNAME, PASSWORD), data=payload)
                except Exception as e:
                    self.error.emit(f"Network error for {token}: {e}")
                    continue

                # Accept 200 or 201 as success (same as your older working code)
                if resp.status_code in (200, 201):
                    d["title"] = payload["title"]
                    d["description"] = payload["description"]
                    d["staged_title"] = None
                    d["staged_description"] = None
                else:
                    # Report the error and continue with next token (do not abort whole batch)
                    # Provide status code and (short) response text for debugging
                    text_snippet = ""
                    try:
                        text_snippet = resp.text[:300]
                    except Exception:
                        pass
                    self.error.emit(f"Failed to push {token}: {resp.status_code} {text_snippet}")
                    # continue to next token
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


# =============== Main GUI ===============

class MediaEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 550)

        self.current_token = None

        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Title", "Description", "Token"])
        self.table.setColumnWidth(0, 300)  # Title
        self.table.setColumnWidth(1, 550)  # Description
        #self.table.setColumnWidth(2, 200)  # Token
        self.table.horizontalHeader().setStretchLastSection(True)
        # Use QAbstractItemView enum for selection behavior
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        self.table.itemSelectionChanged.connect(self.on_selection)

        # Status + progress
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        # Editor panel
        editor = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title")
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Description")
        editor.addWidget(self.title_edit)
        editor.addWidget(self.desc_edit)
        layout.addLayout(editor)
        # Connect text changes
        self.title_edit.textChanged.connect(self.on_text_change)
        self.desc_edit.textChanged.connect(self.on_text_change)

        # Buttons
        btns = QHBoxLayout()
        self.push_btn = QPushButton("Push All Changes")
        self.revert_btn = QPushButton("Revert Current")
        self.refresh_btn = QPushButton("Refresh List")
        btns.addWidget(self.push_btn)
        btns.addWidget(self.revert_btn)
        btns.addWidget(self.refresh_btn)
        layout.addLayout(btns)

        self.push_btn.clicked.connect(self.push_changes)
        self.revert_btn.clicked.connect(self.revert_current)
        self.refresh_btn.clicked.connect(self.load_media)

        # initial load
        self.load_media()

    def load_media(self):
        self.status_label.setText("Loading...")
        self.progress.setRange(0, 0)
        self.table.setRowCount(0)
        self.fetch_thread = FetchThread()
        self.fetch_thread.fetched.connect(self.populate_table)
        self.fetch_thread.error.connect(self.show_error)
        self.fetch_thread.start()

    def populate_table(self, items):
        self.progress.setRange(0, 1)
        self.status_label.setText("")
        self.table.setRowCount(len(items))
        for i, (token, title, desc) in enumerate(items):
            title_item = QTableWidgetItem(title)
            desc_item = QTableWidgetItem(desc)
            item_token = QTableWidgetItem(token)
            # token should not be editable
            title_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            desc_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item_token.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(i, 0, title_item)
            self.table.setItem(i, 1, desc_item)
            self.table.setItem(i, 2, item_token)
            self.update_row_color(i, token)

    def update_row_color(self, row, token):
        # Defensive: ensure the row's items exist
        for c in range(3):
            if self.table.item(row, c) is None:
                self.table.setItem(row, c, QTableWidgetItem(""))

        staged = video_data.get(token, {}).get("staged_title") is not None or \
                 video_data.get(token, {}).get("staged_description") is not None
        color = QColor("purple") if staged else QColor("black")
        for c in range(3):
            it = self.table.item(row, c)
            if it:
                it.setBackground(color)

    def on_selection(self):
        selected = self.table.currentRow()
        if selected < 0:
            return

        token_item = self.table.item(selected, 2)
        if token_item is None:
            return
        token = token_item.text()

        # Auto-stage previous (if any)
        if self.current_token and self.current_token != token:
            self.auto_stage(self.current_token)

        # Switch to new current token
        self.current_token = token
        d = video_data.get(token, {"title": "", "description": "", "staged_title": None, "staged_description": None})
        # Show staged if present, otherwise show saved
        self.title_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)
        try:
            self.title_edit.setText(d["staged_title"] if d["staged_title"] is not None else d["title"])
            self.desc_edit.setText(d["staged_description"] if d["staged_description"] is not None else d["description"])
        finally:
            self.title_edit.blockSignals(False)
            self.desc_edit.blockSignals(False)

    def on_text_change(self, *_):
        # Stage changes for the currently selected token as the user types.
        if not self.current_token:
            return
        self.auto_stage(self.current_token)

    def auto_stage(self, token):
        # Ensure token exists in video_data
        if token not in video_data:
            return
        d = video_data[token]
        t = self.title_edit.text()
        desc = self.desc_edit.text()
        if t != d["title"] or desc != d["description"]:
            d["staged_title"] = t
            d["staged_description"] = desc
        else:
            d["staged_title"] = None
            d["staged_description"] = None

        # Update table cells for the token's row
        for row in range(self.table.rowCount()):
            tok_item = self.table.item(row, 2)
            if tok_item and tok_item.text() == token:
                # Update display (these will be the visible text in the table)
                title_item = self.table.item(row, 0)
                desc_item = self.table.item(row, 1)
                if title_item:
                    title_item.setText(t)
                if desc_item:
                    desc_item.setText(desc)
                self.update_row_color(row, token)
                break

    def push_changes(self):
        staged = [t for t, d in video_data.items() if d["staged_title"] is not None or d["staged_description"] is not None]
        if not staged:
            QMessageBox.information(self, "Nothing to push", "No changes staged.")
            return

        self.status_label.setText("Pushing changes...")
        self.progress.setRange(0, 0)
        # disable push button while pushing
        self.push_btn.setEnabled(False)
        self.push_thread = PushThread(staged)
        self.push_thread.done.connect(self.push_done)
        self.push_thread.error.connect(self.show_error_and_enable_push)
        self.push_thread.start()

    def push_done(self):
        self.progress.setRange(0, 1)
        self.status_label.setText("")
        self.push_btn.setEnabled(True)
        # Refresh table colors (and visible titles/descriptions)
        for row in range(self.table.rowCount()):
            token_item = self.table.item(row, 2)
            if not token_item:
                continue
            token = token_item.text()
            # ensure table shows canonical (saved) title/description
            d = video_data.get(token)
            if d:
                if self.table.item(row, 0):
                    self.table.item(row, 0).setText(d["title"])
                if self.table.item(row, 1):
                    self.table.item(row, 1).setText(d["description"])
            self.update_row_color(row, token)

    def revert_current(self):
        if not self.current_token:
            QMessageBox.warning(self, "No selection", "Select a video first.")
            return
        d = video_data.get(self.current_token)
        if not d:
            return
        d["staged_title"] = None
        d["staged_description"] = None
        # Update editor fields and table row
        self.title_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)
        try:
            self.title_edit.setText(d["title"])
            self.desc_edit.setText(d["description"])
        finally:
            self.title_edit.blockSignals(False)
            self.desc_edit.blockSignals(False)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 2) and self.table.item(row, 2).text() == self.current_token:
                if self.table.item(row, 0):
                    self.table.item(row, 0).setText(d["title"])
                if self.table.item(row, 1):
                    self.table.item(row, 1).setText(d["description"])
                self.update_row_color(row, self.current_token)
                break

    def show_error(self, msg):
        # generic error handler used by fetch thread
        self.progress.setRange(0, 1)
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", msg)

    def show_error_and_enable_push(self, msg):
        # used by push thread so we also re-enable the push button on error
        self.push_btn.setEnabled(True)
        self.show_error(msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # If config.ini was not found, warn once (but continue using defaults)
    if not config_found:
        QMessageBox.warning(None, "Config file not found",
                            f"config.ini not found at {_config_path}. Using built-in defaults.")

    win = MediaEditor()
    win.show()
    sys.exit(app.exec())
