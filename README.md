# yt-dlp-gui

This project provides a graphical interface for the `yt-dlp` command-line tool, making it easier for beginners and advanced users to download videos and playlists.

---

#### Features

1. Beginner-friendly interface:
   - Input URL
   - Format selection (e.g., Best Video + Audio)
   - Download location selection
   - Progress bar and logs

2. Advanced options for experienced users:
   - Custom `yt-dlp` arguments
   - Common options like embedding thumbnails, subtitles, and metadata

3. Setup Assistant:
   - Check for `yt-dlp` and dependencies
   - Automatic download of `yt-dlp`

---

#### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/MohamedMehrath/yt-dlp-gui.git
   cd yt-dlp-gui
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python main.py
   ```

---

#### Optional: Package into `.exe`

Use `PyInstaller` to create a standalone executable:
```bash
pip install pyinstaller
pyinstaller --onefile main.py
```

This will create a single `.exe` file under the `dist/` directory.
