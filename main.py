import sys
import os
import subprocess
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit, QFileDialog, QTabWidget, QCheckBox
)
from PyQt6.QtCore import Qt


class YTDlpGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-dlp GUI")
        self.setGeometry(100, 100, 800, 600)

        # Main layout
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Tabs
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Beginner Tab
        self.beginner_tab = QWidget()
        self.tabs.addTab(self.beginner_tab, "Beginner")
        self.setup_beginner_tab()

        # Advanced Tab
        self.advanced_tab = QWidget()
        self.tabs.addTab(self.advanced_tab, "Advanced")
        self.setup_advanced_tab()

        # Status log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.main_layout.addWidget(self.log_area)

    def setup_beginner_tab(self):
        layout = QVBoxLayout(self.beginner_tab)

        # URL input
        url_label = QLabel("Video/Playlist/Channel URL:")
        self.url_input = QLineEdit()
        layout.addWidget(url_label)
        layout.addWidget(self.url_input)

        # Format selection
        format_label = QLabel("Select Format:")
        self.format_combo = QLineEdit()
        self.format_combo.setPlaceholderText("e.g., Best Video + Best Audio")
        layout.addWidget(format_label)
        layout.addWidget(self.format_combo)

        # Download location
        download_label = QLabel("Download Location:")
        self.download_path = QLineEdit()
        download_browse = QPushButton("Browse")
        download_browse.clicked.connect(self.browse_download_location)
        download_layout = QHBoxLayout()
        download_layout.addWidget(self.download_path)
        download_layout.addWidget(download_browse)
        layout.addWidget(download_label)
        layout.addLayout(download_layout)

        # Download button
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        layout.addWidget(self.download_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

    def setup_advanced_tab(self):
        layout = QVBoxLayout(self.advanced_tab)

        # Custom arguments
        custom_args_label = QLabel("Custom yt-dlp Arguments:")
        self.custom_args_input = QLineEdit()
        layout.addWidget(custom_args_label)
        layout.addWidget(self.custom_args_input)

        # Common advanced options
        self.embed_thumbnail_check = QCheckBox("Embed Thumbnail")
        self.add_metadata_check = QCheckBox("Add Metadata")
        self.use_sponsorblock_check = QCheckBox("Use SponsorBlock")
        self.embed_subs_check = QCheckBox("Embed Subtitles")
        layout.addWidget(self.embed_thumbnail_check)
        layout.addWidget(self.add_metadata_check)
        layout.addWidget(self.use_sponsorblock_check)
        layout.addWidget(self.embed_subs_check)

    def browse_download_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Location")
        if directory:
            self.download_path.setText(directory)

    def start_download(self):
        url = self.url_input.text()
        download_path = self.download_path.text()
        format_option = self.format_combo.text()

        if not url or not download_path:
            self.log_area.append("Error: URL or download location is missing.")
            return

        # Construct yt-dlp command
        command = ["yt-dlp", url, "-o", os.path.join(download_path, "%(title)s.%(ext)s")]

        # Add format option
        if format_option:
            command += ["-f", format_option]

        # Advanced options
        if self.embed_thumbnail_check.isChecked():
            command.append("--embed-thumbnail")
        if self.add_metadata_check.isChecked():
            command.append("--add-metadata")
        if self.use_sponsorblock_check.isChecked():
            command.append("--sponsorblock-remove")
        if self.embed_subs_check.isChecked():
            command.append("--write-subs")
            command.append("--embed-subs")

        # Run in a thread
        threading.Thread(target=self.run_command, args=(command,)).start()

    def run_command(self, command):
        self.log_area.append(f"Running command: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        for line in process.stdout:
            self.log_area.append(line.strip())
        process.wait()
        if process.returncode == 0:
            self.log_area.append("Download completed successfully!")
        else:
            self.log_area.append("Error occurred during download.")

        self.progress_bar.setValue(100)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YTDlpGUI()
    window.show()
    sys.exit(app.exec())
