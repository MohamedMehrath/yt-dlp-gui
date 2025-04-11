# YTDLP-GUI v1.0.0

A simple desktop GUI application for Windows (10/11) to make using the command-line tool `yt-dlp` easier.

![Screenshot Placeholder](screenshot.png)  <!-- Add a screenshot later -->

## Features

*   **Easy Interface:** Simple controls for common download tasks (URL input, basic format selection, directory selection).
*   **Advanced Options:** Access powerful `yt-dlp` features like custom format codes, embedding metadata/thumbnails, SponsorBlock integration, rate limiting, custom arguments, and more.
*   **Real-time Output:** See the output from `yt-dlp` directly in the application.
*   **Progress Tracking:** Visual progress bar for downloads.
*   **Automatic Setup:**
    *   Downloads the latest `yt-dlp.exe` if not found.
    *   Helps install missing Python dependencies (`PyQt6`, `requests`, `pyshortcuts`).
*   **Desktop Shortcut:** Easily create a desktop shortcut for quick access.

## Requirements

*   **OS:** Windows 10 or Windows 11
*   **Python:** Python 3.7 or newer (Python 3.9+ recommended). Make sure Python is added to your system's PATH during installation.

## Installation & Running

1.  **Download:** Download the `main.py` and `requirements.txt` files to a new folder on your computer.
2.  **Install Dependencies:**
    *   Open a Command Prompt (`cmd`) or PowerShell **in that folder**.
    *   Run the command: `pip install -r requirements.txt`
    *   If you encounter errors, you might need to run the Command Prompt as Administrator.
    *   Alternatively, use the "Tools -> Install Missing Dependencies" option within the application after running it once (it will prompt if needed).
3.  **Run the Application:**
    *   Double-click `main.py` OR
    *   Run from the Command Prompt/PowerShell in the folder: `python main.py`

## First Run & Setup

*   **`yt-dlp.exe` Check:** On the first run, the application will check if `yt-dlp.exe` is available (either in the same folder or in your system PATH).
    *   If **not found**, it will prompt you or you can use **"Tools -> Download/Update yt-dlp"** to automatically download the latest version into the application's folder.
*   **Dependency Check:** The application will also check if required Python libraries are installed.
    *   If any are **missing**, it will show a warning. Use **"Tools -> Install Missing Dependencies"** to attempt automatic installation via `pip`. You might need Administrator rights for this.

## Basic Usage

1.  **Enter URL:** Paste the URL of the video, playlist, or channel into the "URL" field.
2.  **Choose Directory:** Click "Browse..." to select where you want to save the downloaded files.
3.  **Select Format:** Choose the desired format from the dropdown (e.g., "Best Video + Audio", "Best Audio Only (MP3)").
4.  **Download:** Click the "Download" button.
5.  **Monitor:** Watch the progress bar and the status area for output from `yt-dlp`.
6.  **Cancel:** Click "Cancel" to stop the current download.

## Advanced Usage

*   Check the "Advanced Options" box to reveal more settings.
*   **Custom Arguments:** Enter any valid `yt-dlp` command-line arguments here (e.g., `--playlist-items 1-5`). These are added *after* the GUI options and may override them.
*   **Format Code (-f):** Specify complex format selections (e.g., `bestvideo[height<=720]+bestaudio/best`). This overrides the basic format dropdown.
*   **Output Template (-o):** Define custom filenames and subdirectories (e.g., `%(uploader)s/%(title)s.%(ext)s`). This is relative to the selected "Save To" directory unless you include absolute paths.
*   **Checkboxes/Fields:** Enable options like embedding thumbnails, metadata, subtitles, SponsorBlock, rate limiting, or using cookies.

## Creating a Shortcut

*   Go to **"Tools -> Create Desktop Shortcut"** to place a convenient shortcut on your desktop.

## (Optional) Packaging with PyInstaller

If you want to distribute this application as a standalone `.exe` file without requiring users to install Python:

1.  Install PyInstaller: `pip install pyinstaller`
2.  Open Command Prompt/PowerShell in the application's folder.
3.  Run the command:
    ```bash
    pyinstaller --onefile --windowed --name YTDLP-GUI --icon=your_icon.ico main.py
    ```
    *   Replace `your_icon.ico` with an actual icon file if you have one.
    *   `--onefile`: Creates a single executable.
    *   `--windowed`: Prevents the console window from appearing when the `.exe` is run.
4.  The standalone executable will be located in the `dist` subfolder.
5.  **Important:** You **still** need to distribute `yt-dlp.exe` alongside your packaged application, or ensure the user downloads it using the application's built-in tool. PyInstaller *won't* bundle `yt-dlp.exe` automatically. You could modify the PyInstaller spec file for more advanced bundling if needed.

## Disclaimer

This application is a front-end for `yt-dlp`. Please respect copyright laws and the terms of service of the websites you download from. The developers of this GUI are not responsible for its misuse.
