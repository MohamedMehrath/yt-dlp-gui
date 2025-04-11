import sys
import os
import subprocess
import threading
import json
import re
import requests
import platform
import shlex # Added for safer argument splitting

# --- Dependency Check ---
# Attempt imports and track missing ones
missing_deps = []
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLineEdit, QPushButton, QFileDialog, QPlainTextEdit, QProgressBar,
        QTabWidget, QGroupBox, QCheckBox, QFormLayout, QLabel, QMessageBox,
        QComboBox
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QSettings
    from PyQt6.QtGui import QAction, QIcon, QPixmap # Added for icon
except ImportError:
    missing_deps.append("PyQt6")

try:
    import requests
except ImportError:
    missing_deps.append("requests")

try:
    # pyshortcuts is recommended for cross-platform,
    # winshell is Windows-specific but sometimes more reliable there.
    import pyshortcuts
except ImportError:
    missing_deps.append("pyshortcuts")
    # Alternatively, try winshell if pyshortcuts fails
    # try:
    #     import winshell
    # except ImportError:
    #     missing_deps.append("winshell") # Add winshell if pyshortcuts is also missing

# --- Constants ---
APP_NAME = "YTDLP-GUI"
VERSION = "1.0.0"
SETTINGS_ORG = "YourOrgName" # Optional: For QSettings
SETTINGS_APP = APP_NAME
YTDLP_GITHUB_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_EXE_FILENAME = "yt-dlp.exe" if platform.system() == "Windows" else "yt-dlp" # Adjust for non-windows if needed


# --- Helper: Find yt-dlp ---
def find_yt_dlp_path():
    """Tries to find yt-dlp executable in common locations."""
    # 1. Check alongside the script/executable
    # Use sys.executable if frozen (PyInstaller), otherwise sys.argv[0]
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__)) # Use __file__ for script location

    local_path = os.path.join(script_dir, YTDLP_EXE_FILENAME)
    if os.path.exists(local_path):
        print(f"Found yt-dlp at: {local_path}")
        return local_path

    # 2. Check in a subdirectory 'bin' (optional good practice)
    bin_path = os.path.join(script_dir, "bin", YTDLP_EXE_FILENAME)
    if os.path.exists(bin_path):
        print(f"Found yt-dlp at: {bin_path}")
        return bin_path

    # 3. Check PATH environment variable (using shutil.which is more robust)
    import shutil
    system_path = shutil.which(YTDLP_EXE_FILENAME)
    if system_path:
        print(f"Found yt-dlp in PATH: {system_path}")
        return system_path

    print("yt-dlp executable not found.")
    return None # Not found

# --- Worker Threads ---

class DownloadWorker(QObject):
    """Runs yt-dlp download in a separate thread."""
    progress = pyqtSignal(int, str)  # percentage, line
    finished = pyqtSignal(bool, str) # success, message
    process_created = pyqtSignal(object) # Pass the process object back

    def __init__(self, command_list):
        super().__init__()
        self.command_list = command_list
        self._is_running = True
        self.process = None

    def run(self):
        try:
            # CREATE_NO_WINDOW prevents console popup on Windows
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NO_WINDOW

            print(f"Executing command: {self.command_list}") # Log the command being run

            self.process = subprocess.Popen(
                self.command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Redirect stderr to stdout
                text=True,
                encoding='utf-8',
                errors='replace', # Handle potential decoding errors
                bufsize=1, # Line buffered
                universal_newlines=True, # Recommended for text mode
                creationflags=creationflags
            )
            self.process_created.emit(self.process) # Send process back to main thread

            percentage = 0
            while self._is_running:
                line = self.process.stdout.readline()
                if not line:
                    break # Process finished

                line = line.strip()
                if not line: continue # Skip empty lines

                # Try to extract percentage (adapt regex if yt-dlp output changes)
                # This regex handles integer and float percentages
                match = re.search(r"\[download\]\s+([0-9]+(?:\.[0-9]+)?)\%", line)
                if match:
                    try:
                        # Use int(float(...)) to handle both cases like "100%" and "15.2%"
                        percentage = int(float(match.group(1)))
                    except ValueError:
                        pass # Keep last known percentage if parse fails
                elif "[download] 100%" in line: # Catch final 100% which might lack decimals
                    percentage = 100

                self.progress.emit(percentage, line)

            # Read remaining output after loop breaks (process might finish quickly)
            # for remaining_line in self.process.stdout:
            #     self.progress.emit(percentage, remaining_line.strip())

            self.process.wait() # Ensure process is finished before checking return code

            if not self._is_running: # Check if cancelled
                 self.finished.emit(False, "Download cancelled by user.")
                 return

            if self.process.returncode == 0:
                # Ensure final progress update reaches 100% on success
                self.progress.emit(100, "[download] Finished")
                self.finished.emit(True, "Download finished successfully.")
            else:
                 self.finished.emit(False, f"Download failed (yt-dlp exited with code {self.process.returncode}). Check status log for details.")

        except FileNotFoundError:
             # Provide a more informative error if the executable itself isn't found
             self.finished.emit(False, f"Error: '{self.command_list[0]}' not found. Ensure yt-dlp is installed and accessible (check PATH or place it near the script).")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred during download: {e}")
            import traceback
            print("Download Error Traceback:")
            traceback.print_exc() # Print detailed traceback to console
        finally:
            self.process = None # Clear process ref

    def stop(self):
        self._is_running = False
        if self.process and self.process.poll() is None: # Check if running
            try:
                # Attempt graceful termination first, then force kill
                print("Terminating yt-dlp process...")
                self.process.terminate()
                try:
                    self.process.wait(timeout=2) # Wait a bit for termination
                    print("Process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    print("Process did not terminate gracefully, killing...")
                    self.process.kill()
                    self.process.wait() # Ensure killed process is reaped
                    print("Process killed.")
            except Exception as e:
                print(f"Error stopping subprocess: {e}") # Log error


class SetupWorker(QObject):
    """Handles setup tasks (yt-dlp download, dep install) in a thread."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str, object) # success, message, result_data (optional)

    def __init__(self, task, data=None):
        super().__init__()
        self.task = task # 'download_ytdlp', 'install_deps'
        self.data = data # e.g., list of missing deps
        self._is_running = True

    def run(self):
        if not self._is_running: return
        if self.task == 'download_ytdlp':
            self._download_ytdlp()
        elif self.task == 'install_deps':
            self._install_deps()

    def _download_ytdlp(self):
        """Downloads the latest yt-dlp executable."""
        self.progress.emit("Fetching latest release information from GitHub...")
        try:
            response = requests.get(YTDLP_GITHUB_API, timeout=20) # Increased timeout
            response.raise_for_status() # Raise exception for bad status codes
            release_info = response.json()
            assets = release_info.get("assets", [])
            download_url = None

            # Determine the correct asset name based on OS
            target_asset_name = YTDLP_EXE_FILENAME
            # Add checks for other OS if needed (e.g., 'yt-dlp' for Linux/macOS)
            # if platform.system() == "Linux": target_asset_name = "yt-dlp_linux" # Example, check actual asset names
            # elif platform.system() == "Darwin": target_asset_name = "yt-dlp_macos" # Example

            for asset in assets:
                if asset.get("name") == target_asset_name:
                    download_url = asset.get("browser_download_url")
                    break

            if not download_url:
                self.finished.emit(False, f"Could not find '{target_asset_name}' in the latest GitHub release assets.", None)
                return

            self.progress.emit(f"Found download URL: {download_url}")
            self.progress.emit(f"Downloading {target_asset_name}...")

            # Determine download location (next to script/frozen exe)
            if getattr(sys, 'frozen', False):
                script_dir = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            download_path = os.path.join(script_dir, target_asset_name)

            with requests.get(download_url, stream=True, timeout=120) as r: # Increased timeout
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                bytes_downloaded = 0
                with open(download_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if not self._is_running:
                            self.finished.emit(False, "Download cancelled.", None)
                            # Clean up potentially incomplete file
                            try: os.remove(download_path)
                            except OSError: pass
                            return
                        f.write(chunk)
                        bytes_downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(100 * bytes_downloaded / total_size)
                            self.progress.emit(f"Downloading {target_asset_name}: {percent}%")
                        else:
                            self.progress.emit(f"Downloading {target_asset_name}: {bytes_downloaded // 1024} KB")


            # Make executable (important on Linux/macOS)
            if platform.system() != "Windows":
                try:
                    os.chmod(download_path, 0o755) # Add execute permissions
                    self.progress.emit("Set executable permissions.")
                except OSError as e:
                     self.progress.emit(f"Warning: Could not set executable permissions: {e}")


            self.progress.emit(f"{target_asset_name} downloaded successfully to:\n{download_path}")
            self.finished.emit(True, f"{target_asset_name} downloaded.", download_path) # Pass path back

        except requests.exceptions.Timeout:
             self.finished.emit(False, "Network Timeout: Could not connect to GitHub or download timed out.", None)
        except requests.exceptions.RequestException as e:
            self.finished.emit(False, f"Network error downloading yt-dlp: {e}", None)
        except Exception as e:
            self.finished.emit(False, f"Error downloading yt-dlp: {e}", None)
            import traceback
            traceback.print_exc()

    def _install_deps(self):
        """Attempts to install missing dependencies using pip."""
        if not self.data:
            self.finished.emit(True, "No missing dependencies specified.", None)
            return

        missing_str = " ".join(self.data)
        self.progress.emit(f"Attempting to install missing packages: {missing_str}...")
        self.progress.emit("This may require administrator privileges.")

        # Use sys.executable to ensure pip is called from the correct Python env
        command = [sys.executable, '-m', 'pip', 'install'] + self.data

        try:
            # Using subprocess.run as it's a one-off command
            self.progress.emit(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                command,
                capture_output=True, text=True, check=False, # Don't check=True, handle errors manually
                encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            # Log output regardless of success/failure for debugging
            self.progress.emit("--- pip output ---")
            if result.stdout:
                 self.progress.emit(result.stdout)
            if result.stderr:
                 self.progress.emit(result.stderr)
            self.progress.emit("--- end pip output ---")


            if result.returncode == 0:
                self.progress.emit("Dependencies installed successfully.")
                # Clear the missing list globally (or handle this state better)
                global missing_deps
                missing_deps = [dep for dep in missing_deps if dep not in self.data]
                self.finished.emit(True, "Dependencies installed.", None)
            else:
                error_msg = f"Failed to install dependencies (pip exited with code {result.returncode}).\n"
                error_msg += "Try running pip install manually in a terminal (possibly with admin rights):\n"
                error_msg += f"'{sys.executable}' -m pip install {missing_str}\n"
                self.progress.emit(error_msg)
                self.finished.emit(False, "Dependency installation failed. See log.", None)

        except FileNotFoundError:
             self.finished.emit(False, "Error: Python executable or pip was not found. Is Python installed correctly and in PATH?", None)
        except Exception as e:
            self.finished.emit(False, f"An error occurred during dependency installation: {e}", None)
            import traceback
            traceback.print_exc()


    def stop(self):
        self._is_running = False # Signal download loop to stop


# --- Main Application Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- Handle Critical Dependencies Early ---
        if "PyQt6" in missing_deps:
             # Use a fallback message box if possible
             self._show_critical_dependency_error_fallback("PyQt6")
             sys.exit(1) # Exit if GUI framework is missing

        self.ytdlp_path = None # Will be set by check or download
        self.current_process = None # To hold the running yt-dlp process
        self.download_thread = None
        self.download_worker = None
        self.setup_thread = None
        self.setup_worker = None

        # Load settings (Download dir, etc.)
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setGeometry(100, 100, 750, 600) # x, y, width, height

        # --- Icon ---
        # You should create a small .png icon and load it like this:
        # icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_icon.png')
        # if os.path.exists(icon_path):
        #     self.setWindowIcon(QIcon(icon_path))
        # else: # Fallback placeholder icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.darkCyan)
        self.setWindowIcon(QIcon(pixmap))

        # --- Widgets ---
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Video/Playlist/Channel URL here")

        self.dir_label = QLineEdit()
        self.dir_label.setReadOnly(True)
        # Default to User's Downloads folder, handle potential non-existence gracefully
        default_download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(default_download_dir): default_download_dir = os.path.expanduser("~") # Fallback to home dir
        self.dir_label.setText(self.settings.value("downloadDir", default_download_dir))
        self.browse_button = QPushButton("Browse...")

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "Best Video + Audio (Default MP4/MKV)", # yt-dlp default is usually webm/mkv
            "Best Video + Audio (Force MP4)",
            "Best Audio Only (MP3)",
            "Best Audio Only (M4A/AAC)",
            "Best Audio Only (Opus)",
            "Best Video Only (No Audio)",
        ])
        self.format_combo.setToolTip(
            "Select desired format.\n"
            "'Best Audio Only' options require ffmpeg to be installed and in PATH.\n"
            "'Force MP4' may involve re-encoding if native MP4 isn't available."
            )

        self.download_button = QPushButton("Download")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - Ready") # Initial text

        self.status_area = QPlainTextEdit()
        self.status_area.setReadOnly(True)
        self.status_area.setPlaceholderText("yt-dlp output and status messages will appear here...")
        font = self.status_area.font()
        font.setPointSize(9) # Make log text slightly smaller
        self.status_area.setFont(font)


        # --- Advanced Options Widgets ---
        self.advanced_group = QGroupBox("Advanced Options")
        self.advanced_group.setCheckable(True) # Allow hiding/showing
        self.advanced_group.setChecked(self.settings.value("advancedVisible", False, type=bool))

        self.raw_args_input = QLineEdit()
        self.raw_args_input.setPlaceholderText("e.g., --max-downloads 5 --dateafter 20230101")
        self.format_code_input = QLineEdit()
        self.format_code_input.setPlaceholderText("e.g., bestvideo[height<=?1080]+bestaudio/best")
        self.output_template_input = QLineEdit()
        self.output_template_input.setPlaceholderText("%(title)s [%(id)s].%(ext)s")
        self.rate_limit_input = QLineEdit()
        self.rate_limit_input.setPlaceholderText("e.g., 1.5M (Bytes/sec)")
        self.cookies_input = QLineEdit()
        self.cookies_input.setPlaceholderText("Path to cookies.txt (optional)")
        self.browse_cookies_button = QPushButton("...") # Smaller browse button
        self.browse_cookies_button.setMaximumWidth(30)

        self.embed_thumb_check = QCheckBox("Embed Thumbnail")
        self.embed_thumb_check.setToolTip("Requires ffmpeg/ffprobe.")
        self.add_meta_check = QCheckBox("Add Metadata")
        self.add_meta_check.setToolTip("Requires ffmpeg/ffprobe.")
        self.sponsorblock_combo = QComboBox()
        self.sponsorblock_combo.addItems([
            "SponsorBlock: Off",
            "SponsorBlock: Remove All (--sponsorblock-remove all)",
            "SponsorBlock: Remove Sponsor (--sponsorblock-remove sponsor)",
            "SponsorBlock: Remove Selfpromo (--sponsorblock-remove selfpromo)",
            # Add more specific categories if desired
        ])
        self.sponsorblock_combo.setToolTip("Requires network connection during download.")
        self.embed_subs_check = QCheckBox("Embed Subtitles (if available)")
        self.embed_subs_check.setToolTip("Requires ffmpeg. Selects best available subtitle.")
        self.write_auto_subs_check = QCheckBox("Write Auto-Subtitles (if no others)")
        self.write_auto_subs_check.setToolTip("Downloads automatic captions if no manual subs exist.")
        self.keep_video_check = QCheckBox("Keep Unprocessed Files (--keep-video)")
        self.keep_video_check.setToolTip("Keep intermediate video files (e.g., before merging audio).")


        # --- Layouts ---
        main_layout = QVBoxLayout()
        url_layout = QHBoxLayout()
        dir_layout = QHBoxLayout()
        control_layout = QHBoxLayout()
        advanced_layout = QFormLayout() # Use QFormLayout for label/widget pairs
        advanced_checkbox_layout1 = QHBoxLayout()
        advanced_checkbox_layout2 = QHBoxLayout()

        # Basic Section
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.url_input)

        dir_layout.addWidget(QLabel("Save To:"))
        dir_layout.addWidget(self.dir_label, 1) # Allow label to stretch
        dir_layout.addWidget(self.browse_button)

        basic_group = QGroupBox("Basic Options")
        basic_layout = QVBoxLayout()
        basic_layout.addLayout(url_layout)
        basic_layout.addLayout(dir_layout)
        form_basic = QFormLayout()
        form_basic.addRow("Format:", self.format_combo)
        basic_layout.addLayout(form_basic)
        basic_group.setLayout(basic_layout)


        # Advanced Section Setup
        advanced_layout.addRow("Custom Arguments:", self.raw_args_input)
        advanced_layout.addRow("Format Code (-f):", self.format_code_input)
        advanced_layout.addRow("Output Template (-o):", self.output_template_input)
        advanced_layout.addRow("Rate Limit (--limit-rate):", self.rate_limit_input)
        cookies_layout = QHBoxLayout()
        cookies_layout.addWidget(self.cookies_input, 1) # Stretch input
        cookies_layout.addWidget(self.browse_cookies_button)
        advanced_layout.addRow("Cookies (--cookies):", cookies_layout)
        advanced_layout.addRow("SponsorBlock:", self.sponsorblock_combo)

        advanced_checkbox_layout1.addWidget(self.embed_thumb_check)
        advanced_checkbox_layout1.addWidget(self.add_meta_check)
        advanced_checkbox_layout1.addWidget(self.embed_subs_check)
        advanced_checkbox_layout1.addStretch() # Push checkboxes left
        advanced_layout.addRow(advanced_checkbox_layout1)

        advanced_checkbox_layout2.addWidget(self.write_auto_subs_check)
        advanced_checkbox_layout2.addWidget(self.keep_video_check)
        advanced_checkbox_layout2.addStretch() # Push checkboxes left
        advanced_layout.addRow(advanced_checkbox_layout2)


        self.advanced_group.setLayout(advanced_layout)


        # Bottom Controls
        control_layout.addStretch() # Push buttons right
        control_layout.addWidget(self.download_button)
        control_layout.addWidget(self.cancel_button)

        main_layout.addWidget(basic_group)
        main_layout.addWidget(self.advanced_group)
        main_layout.addLayout(control_layout)
        main_layout.addWidget(QLabel("Status:"))
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_area)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- Menu Bar ---
        self._create_menus()

        # --- Connections ---
        self.browse_button.clicked.connect(self.browse_directory)
        self.browse_cookies_button.clicked.connect(self.browse_cookies_file)
        self.download_button.clicked.connect(self.start_download)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.advanced_group.toggled.connect(self.save_advanced_visibility)

        # --- Initial Setup Check ---
        self._check_ytdlp_on_startup()

    def _create_menus(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        exit_action = QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools Menu
        tools_menu = menu_bar.addMenu("&Tools")
        check_setup_action = QAction("Check yt-dlp & Dependencies", self)
        check_setup_action.triggered.connect(self.run_full_check)
        tools_menu.addAction(check_setup_action)

        update_ytdlp_action = QAction("Download/Update yt-dlp", self)
        update_ytdlp_action.triggered.connect(self.trigger_ytdlp_download)
        tools_menu.addAction(update_ytdlp_action)

        self.install_deps_action = QAction("Install Missing Python Dependencies", self)
        self.install_deps_action.triggered.connect(lambda: self.trigger_dep_install(missing_deps))
        tools_menu.addAction(self.install_deps_action)
        self.install_deps_action.setEnabled(bool(missing_deps)) # Enable only if needed

        tools_menu.addSeparator()

        create_shortcut_action = QAction("Create Desktop Shortcut", self)
        create_shortcut_action.triggered.connect(self.create_desktop_shortcut)
        tools_menu.addAction(create_shortcut_action)

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    # --- Action Methods ---

    def browse_directory(self):
        start_dir = self.dir_label.text()
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~") # Fallback if saved dir is invalid

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Download Directory",
            start_dir # Start in the current/default directory
        )
        if directory:
            self.dir_label.setText(directory)
            self.settings.setValue("downloadDir", directory) # Save preference

    def browse_cookies_file(self):
        start_dir = os.path.dirname(self.cookies_input.text()) if self.cookies_input.text() else self.dir_label.text()
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cookies File",
             start_dir,
             "Text files (*.txt);;All files (*.*)"
        )
        if filepath:
            self.cookies_input.setText(filepath)

    def start_download(self):
        if self.is_worker_running():
            self.log_status("A download or setup task is already in progress.")
            QMessageBox.warning(self, "Busy", "Another operation (download/setup) is currently running.")
            return

        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a video/playlist/channel URL.")
            return

        if not self.ytdlp_path or not os.path.exists(self.ytdlp_path):
            self._check_ytdlp_on_startup() # Try to find/prompt download again
            if not self.ytdlp_path or not os.path.exists(self.ytdlp_path):
                 QMessageBox.critical(self, "yt-dlp Not Found",
                                 f"yt-dlp executable was not found or is not accessible.\nExpected at: {self.ytdlp_path}\n\nPlease use 'Tools -> Download/Update yt-dlp' or ensure it's in PATH.")
                 return

        download_dir = self.dir_label.text()
        if not os.path.isdir(download_dir):
             try:
                 os.makedirs(download_dir) # Try creating the directory
                 self.log_status(f"Created download directory: {download_dir}")
             except OSError as e:
                 QMessageBox.warning(self, "Invalid Directory", f"The selected download directory does not exist and could not be created:\n{download_dir}\nError: {e}")
                 return


        # --- Build Command List ---
        command = [self.ytdlp_path]

        # Add --ignore-config to prevent user configs from interfering
        command.append('--ignore-config')
        # Add --no-mtime to prevent filesystem timestamp issues
        command.append('--no-mtime')


        # Output Directory/Template
        output_template = self.output_template_input.text().strip() if self.advanced_group.isChecked() else ""
        if output_template:
             # Let yt-dlp handle the path joining by default using -o
             full_output_path = os.path.join(download_dir, output_template)
             command.extend(['-o', full_output_path])
        else:
            # Default: save to selected directory with default naming using -P
            command.extend(['-P', download_dir])


        # Format Selection
        format_code = self.format_code_input.text().strip() if self.advanced_group.isChecked() else ""
        if format_code:
            command.extend(['-f', format_code])
        else:
            # Simple format selection
            selected_format = self.format_combo.currentText()
            if "Best Audio Only (MP3)" in selected_format:
                command.extend(['-x', '--audio-format', 'mp3', '-f', 'bestaudio/best'])
            elif "Best Audio Only (M4A/AAC)" in selected_format:
                 command.extend(['-x', '--audio-format', 'm4a', '-f', 'bestaudio/best'])
            elif "Best Audio Only (Opus)" in selected_format:
                 command.extend(['-x', '--audio-format', 'opus', '-f', 'bestaudio/best'])
            elif "Best Video Only" in selected_format:
                 command.extend(['-f', 'bestvideo/best'])
            elif "Force MP4" in selected_format:
                 command.extend(['--remux-video', 'mp4']) # Remux if possible, fallback to default format
            # Default ("Best Video + Audio") uses yt-dlp's default behavior

        # Advanced Checkboxes & Fields
        if self.advanced_group.isChecked():
            if self.embed_thumb_check.isChecked():
                command.extend(['--embed-thumbnail', '--convert-thumbnails', 'jpg']) # Convert ensures compatibility
            if self.add_meta_check.isChecked():
                command.append('--add-metadata')
            if self.embed_subs_check.isChecked():
                command.extend(['--embed-subs', '--sub-langs', 'all']) # Embed all available preferred langs
            if self.write_auto_subs_check.isChecked():
                command.append('--write-auto-subs')

            sponsor_choice = self.sponsorblock_combo.currentText()
            if "Remove All" in sponsor_choice:
                command.extend(['--sponsorblock-remove', 'all'])
            elif "Remove Sponsor" in sponsor_choice:
                command.extend(['--sponsorblock-remove', 'sponsor'])
            elif "Remove Selfpromo" in sponsor_choice:
                 command.extend(['--sponsorblock-remove', 'selfpromo'])
            # Add more elif for other specific categories if needed

            # Rate Limit
            rate_limit = self.rate_limit_input.text().strip()
            if rate_limit:
                command.extend(['--limit-rate', rate_limit]) # yt-dlp expects format like 50K, 4.2M

            # Cookies
            cookies_file = self.cookies_input.text().strip()
            if cookies_file and os.path.exists(cookies_file):
                command.extend(['--cookies', cookies_file])
            elif cookies_file:
                 self.log_status(f"Warning: Cookies file specified but not found: {cookies_file}")

            if self.keep_video_check.isChecked():
                 command.append('--keep-video')


            # Raw/Custom Arguments (Append these last, potentially overriding others)
            raw_args = self.raw_args_input.text().strip()
            if raw_args:
                try:
                    # Use shlex to handle quoted arguments properly
                    parsed_args = shlex.split(raw_args)
                    command.extend(parsed_args)
                except ValueError as e:
                     QMessageBox.warning(self, "Argument Error", f"Could not parse custom arguments: {e}\nArguments: {raw_args}")
                     return # Stop if custom args are malformed

        # --- Finally, add the URL ---
        command.append(url)

        # --- Log Command and Start Download ---
        self.log_status(f"--------------------")
        self.log_status(f"Starting download for: {url}")
        # Mask cookies file path if logging command
        logged_command = [arg if '--cookies' not in arg else '--cookies "..."' for arg in command]
        self.log_status(f"Command: {' '.join(logged_command)}") # Basic joining for display

        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p% - Starting...")
        self.set_ui_state(downloading=True) # Disable inputs, enable cancel
        self.status_area.clear() # Clear previous output

        # Create and start the download worker thread
        self.download_thread = QThread(self) # Pass parent
        self.download_worker = DownloadWorker(command)
        self.download_worker.moveToThread(self.download_thread)

        # Connect signals
        self.download_worker.progress.connect(self.update_progress)
        self.download_worker.finished.connect(self.download_finished)
        self.download_worker.process_created.connect(self.set_current_process) # Get the process object
        self.download_thread.started.connect(self.download_worker.run)
        # Clean up thread and worker when finished
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_worker.finished.connect(self.download_worker.deleteLater)
        self.download_thread.finished.connect(self.download_thread.deleteLater)

        self.download_thread.start()

    def cancel_download(self):
        """Stops the currently running download worker."""
        self.log_status("Attempting to cancel download...")
        if self.download_worker:
            self.download_worker.stop() # Signal the worker to stop

        # The finished signal (called with success=False) will handle UI state reset
        self.cancel_button.setEnabled(False) # Disable immediately

    # --- Slot Methods ---

    def update_progress(self, percentage, line):
        """Updates progress bar and status area from DownloadWorker."""
        # Sometimes yt-dlp might output > 100% briefly, cap it
        percentage = min(percentage, 100)
        self.progress_bar.setValue(percentage)
        # Update progress bar text based on the line content
        if "[download]" in line:
            self.progress_bar.setFormat(f"%p% - {line.split(']')[1].strip()}")
        elif "Merging formats" in line:
             self.progress_bar.setFormat("%p% - Merging...")
        elif "Deleting original file" in line:
             self.progress_bar.setFormat("%p% - Cleaning up...")
        # Add more specific status updates based on yt-dlp output if needed

        self.log_status(line) # Append line to status area

    def download_finished(self, success, message):
        """Handles completion of the download thread."""
        self.log_status(f"--------------------")
        self.log_status(message)
        if success:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100% - Finished")
            # Optionally show a success popup, but log is usually enough
            # QMessageBox.information(self, "Download Complete", message)
        else:
            # Keep progress bar where it was or reset
            self.progress_bar.setFormat(f"{self.progress_bar.value()}% - Failed")
            QMessageBox.warning(self, "Download Issue", message)

        # Reset UI state
        self.set_ui_state(downloading=False)
        self.current_process = None # Clear process reference

        # Worker and thread should delete themselves via deleteLater signals

    def setup_progress(self, message):
        """Shows progress from SetupWorker in the status area."""
        self.log_status(f"[Setup] {message}")

    def setup_finished(self, success, message, result_data):
        """Handles completion of the setup thread."""
        self.log_status(f"--------------------")
        self.log_status(f"[Setup] {message}")
        if success:
            # If yt-dlp was downloaded, update the path
            if self.setup_worker and self.setup_worker.task == 'download_ytdlp' and result_data:
                 self.ytdlp_path = result_data
                 self.log_status(f"yt-dlp path set to: {self.ytdlp_path}")
                 QMessageBox.information(self, "yt-dlp Ready", f"{YTDLP_EXE_FILENAME} downloaded successfully.")
            elif self.setup_worker and self.setup_worker.task == 'install_deps':
                 QMessageBox.information(self, "Dependencies Installed", "Required Python packages installed successfully. Please restart the application if needed.")
                 # Update the menu item state
                 self.install_deps_action.setEnabled(bool(missing_deps))
            else:
                 QMessageBox.information(self, "Setup Complete", message)

        else:
            QMessageBox.warning(self, "Setup Failed", message)

        # Reset UI state (enable relevant buttons)
        self.set_ui_state(downloading=False)

        # Clean up setup thread/worker
        if self.setup_thread and self.setup_thread.isRunning():
             self.setup_thread.quit()
             self.setup_thread.wait()
        self.setup_worker = None
        self.setup_thread = None


    def set_current_process(self, process):
        """Receives the subprocess object from the worker."""
        self.current_process = process

    def log_status(self, message):
        """Appends a message to the status text area."""
        self.status_area.appendPlainText(message)
        # Scroll to bottom
        self.status_area.verticalScrollBar().setValue(self.status_area.verticalScrollBar().maximum())

    def set_ui_state(self, downloading):
        """Enable/disable UI elements based on download state."""
        is_busy = downloading or (self.setup_thread and self.setup_thread.isRunning())

        self.url_input.setEnabled(not is_busy)
        self.browse_button.setEnabled(not is_busy)
        self.format_combo.setEnabled(not is_busy)
        self.advanced_group.setEnabled(not is_busy)
        self.download_button.setEnabled(not is_busy)
        # Also disable relevant menu items
        self.menuBar().setEnabled(not is_busy)

        # Cancel button only enabled during actual download
        self.cancel_button.setEnabled(downloading)

        if not is_busy:
             self.progress_bar.setFormat(f"{self.progress_bar.value()}% - Ready")


    # --- Setup and Helper Methods ---

    def _check_ytdlp_on_startup(self):
        """Checks for yt-dlp on startup and prompts if missing."""
        self.log_status("Checking for yt-dlp...")
        self.ytdlp_path = find_yt_dlp_path()
        if self.ytdlp_path:
            self.log_status(f"Found yt-dlp at: {self.ytdlp_path}")
            # Optionally check version here if needed
        else:
            self.log_status("yt-dlp not found.")
            reply = QMessageBox.question(self, "yt-dlp Not Found",
                                         f"{YTDLP_EXE_FILENAME} could not be found automatically.\n\n"
                                         f"Do you want to attempt to download the latest version from GitHub?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Yes:
                self.trigger_ytdlp_download()
            else:
                 self.log_status("yt-dlp download skipped by user. Please install manually or place it near the application.")


    def _show_dependency_warning(self):
        """Shows a warning if non-critical dependencies are missing."""
        if missing_deps:
            msg = ("Warning: The following Python dependencies are missing:\n"
                   f"- {', '.join(missing_deps)}\n\n"
                   "Some features might not work correctly (e.g., setup helpers, shortcuts).\n"
                   "You can try to install them using 'Tools -> Install Missing Python Dependencies'.")
            QMessageBox.warning(self, "Missing Dependencies", msg)
            self.log_status(msg)
            # Update install deps menu item state
            if hasattr(self, 'install_deps_action'):
                self.install_deps_action.setEnabled(True)

    def _show_critical_dependency_error_fallback(self, dep_name):
        """Fallback error display if PyQt itself is missing."""
        error_msg = (f"Critical Error: {dep_name} is not installed.\n"
                     f"This application requires {dep_name} to run.\n\n"
                     "Please install it using pip:\n"
                     f"pip install {dep_name}\n\n"
                     "Or install all dependencies if a requirements.txt is available.")
        print(error_msg, file=sys.stderr)
        try:
            # Attempt Tkinter fallback for a visible message
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw() # Hide the main Tk window
            messagebox.showerror("Critical Dependency Error", error_msg)
            root.destroy()
        except ImportError:
            pass # No GUI fallback available


    def run_full_check(self):
        """Menu action to check yt-dlp and dependencies."""
        if self.is_worker_running():
             QMessageBox.warning(self, "Busy", "Another operation is already running.")
             return

        self.log_status("--- Running Full Setup Check ---")
        # 1. Check yt-dlp
        self.ytdlp_path = find_yt_dlp_path()
        if self.ytdlp_path:
            self.log_status(f"yt-dlp Found: {self.ytdlp_path}")
            # TODO: Add optional version check? subprocess.run([self.ytdlp_path, '--version'])
        else:
            self.log_status("yt-dlp: Not Found")

        # 2. Check Python Dependencies
        if missing_deps:
            self.log_status(f"Missing Python Dependencies: {', '.join(missing_deps)}")
            self.install_deps_action.setEnabled(True)
        else:
             self.log_status("Python Dependencies: OK")
             self.install_deps_action.setEnabled(False)

        # 3. Check for ffmpeg (optional but recommended)
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
             self.log_status(f"ffmpeg Found: {ffmpeg_path}")
        else:
             self.log_status("ffmpeg: Not Found (Required for audio extraction and some embedding features)")

        QMessageBox.information(self, "Setup Check Complete", "Check results logged in the status area.")


    def trigger_ytdlp_download(self):
        """Menu action to start yt-dlp download."""
        if self.is_worker_running():
             QMessageBox.warning(self, "Busy", "Another operation is already running.")
             return

        self.log_status("Starting yt-dlp download...")
        self.set_ui_state(downloading=True) # Visually indicate busy state

        self.setup_thread = QThread(self)
        self.setup_worker = SetupWorker('download_ytdlp')
        self.setup_worker.moveToThread(self.setup_thread)

        self.setup_worker.progress.connect(self.setup_progress)
        self.setup_worker.finished.connect(self.setup_finished)
        self.setup_thread.started.connect(self.setup_worker.run)
        self.setup_worker.finished.connect(self.setup_thread.quit)
        self.setup_worker.finished.connect(self.setup_worker.deleteLater)
        self.setup_thread.finished.connect(self.setup_thread.deleteLater)

        self.setup_thread.start()

    def trigger_dep_install(self, deps_to_install):
        """Menu action to start installing missing Python dependencies."""
        if not deps_to_install:
             QMessageBox.information(self, "Dependencies OK", "No missing dependencies detected.")
             return

        if self.is_worker_running():
             QMessageBox.warning(self, "Busy", "Another operation is already running.")
             return

        reply = QMessageBox.question(self, "Install Dependencies?",
                                      f"Attempt to install the following missing packages using pip?\n- {', '.join(deps_to_install)}\n\nThis might require administrator privileges.",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.No:
            return


        self.log_status(f"Starting dependency installation for: {', '.join(deps_to_install)}")
        self.set_ui_state(downloading=True) # Use same busy state

        self.setup_thread = QThread(self)
        self.setup_worker = SetupWorker('install_deps', deps_to_install)
        self.setup_worker.moveToThread(self.setup_thread)

        self.setup_worker.progress.connect(self.setup_progress)
        self.setup_worker.finished.connect(self.setup_finished)
        self.setup_thread.started.connect(self.setup_worker.run)
        self.setup_worker.finished.connect(self.setup_thread.quit)
        self.setup_worker.finished.connect(self.setup_worker.deleteLater)
        self.setup_thread.finished.connect(self.setup_thread.deleteLater)

        self.setup_thread.start()


    def create_desktop_shortcut(self):
        """Creates a desktop shortcut for the application."""
        if "pyshortcuts" in missing_deps:
            QMessageBox.warning(self, "Missing Dependency", "The 'pyshortcuts' library is required to create shortcuts. Please install it first (Tools -> Install...).")
            return

        try:
            # Determine the target executable (Python script or frozen exe)
            if getattr(sys, 'frozen', False):
                target = sys.executable
                icon_path = target # Use exe's embedded icon
            else:
                # Need pythonw.exe to run without console window
                python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(python_exe): python_exe = sys.executable # Fallback if pythonw not found
                target = python_exe
                script_path = os.path.abspath(__file__)
                icon_path = "" # Optional: provide path to an .ico file here
                # Add script path as argument for pythonw
                target_args = f'"{script_path}"'


            shortcut_name = f"{APP_NAME}.lnk"
            desktop_path = pyshortcuts.get_desktop()
            shortcut_path = os.path.join(desktop_path, shortcut_name)

            # Use pyshortcuts.make_shortcut
            pyshortcuts.make_shortcut(
                script=target if getattr(sys, 'frozen', False) else target_args, # Pass args only for script mode
                name=APP_NAME,
                icon=icon_path,
                terminal=False, # Run without terminal
                desktop=True,
                startmenu=False
                )


            self.log_status(f"Desktop shortcut created/updated at: {shortcut_path}")
            QMessageBox.information(self, "Shortcut Created", f"Desktop shortcut '{shortcut_name}' created successfully.")

        except Exception as e:
            self.log_status(f"Error creating shortcut: {e}")
            QMessageBox.critical(self, "Shortcut Error", f"Failed to create desktop shortcut.\nError: {e}")
            import traceback
            traceback.print_exc()


    def show_about_dialog(self):
        """Displays a simple About dialog."""
        about_text = (f"<b>{APP_NAME}</b> v{VERSION}<br><br>"
                      "A simple GUI front-end for the powerful yt-dlp command-line tool.<br><br>"
                      "Developed using Python and PyQt6.<br>"
                      "Find yt-dlp at: <a href='https://github.com/yt-dlp/yt-dlp'>https://github.com/yt-dlp/yt-dlp</a><br><br>"
                      f"(C) 2024 {SETTINGS_ORG}" # Replace YourOrgName
                      )
        QMessageBox.about(self, f"About {APP_NAME}", about_text)

    def save_advanced_visibility(self, checked):
        """Saves the visibility state of the advanced options group."""
        self.settings.setValue("advancedVisible", checked)

    def is_worker_running(self):
        """Check if a download or setup worker is active."""
        return (self.download_thread and self.download_thread.isRunning()) or \
               (self.setup_thread and self.setup_thread.isRunning())

    def closeEvent(self, event):
        """Handle window close event."""
        if self.is_worker_running():
            reply = QMessageBox.question(self, "Operation in Progress",
                                         "A download or setup task is still running. Are you sure you want to quit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # Try to stop workers gracefully before exiting
                if self.download_worker: self.download_worker.stop()
                if self.setup_worker: self.setup_worker.stop()
                event.accept() # Allow closing
            else:
                event.ignore() # Prevent closing
        else:
            # Save settings before closing
            self.settings.setValue("advancedVisible", self.advanced_group.isChecked())
            # self.settings.setValue("geometry", self.saveGeometry()) # Optional: save window size/pos
            event.accept()


# --- Main Execution ---
if __name__ == "__main__":
    # Set Application details for QSettings and potentially packaging
    QApplication.setOrganizationName(SETTINGS_ORG)
    QApplication.setApplicationName(SETTINGS_APP)

    # Ensure high DPI scaling is enabled
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Check for critical missing dependencies before creating window
    # (We already check for PyQt6 *before* class definition if needed)
    # This is redundant here if the check above works, but safe fallback
    if "PyQt6" in missing_deps:
         # Use the fallback mechanism if PyQt6 wasn't found initially
         MainWindow._show_critical_dependency_error_fallback(None, "PyQt6") # Call statically
         sys.exit(1)

    window = MainWindow()
    window.show()

    # Show non-critical dependency warning after window is created
    window._show_dependency_warning()


    sys.exit(app.exec())
