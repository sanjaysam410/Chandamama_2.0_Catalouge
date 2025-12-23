# Chandamama Magazine Indexer

A Streamlit application to extract structured metadata (stories, authors, page numbers) from Chandamama magazine PDFs using the Google Gemini API.

## Features
- **Strict JSON Extraction**: Uses Gemini to analyze magazine content and return a standardized JSON format.
- **Robust Parsing**: Includes automatic repair for common JSON errors (missing commas, quotes, etc.) using `json_repair`.
- **Bulk Processing**: Process entire directories of PDFs automatically with progress tracking.
- **Verification UI**: Review and edit extracted data before saving.
- **Global Statistics**: Tracks total stories, authors, and genres across the collection.

## Installation

1.  **Clone/Open the Repository**:
    Ensure you are in the project root directory.

2.  **Install Dependencies**:
    ```bash
    cd MetaData_Extractor
    pip install -r requirements.txt
    ```

## How to Run

1.  **Start the App**:
    ```bash
    cd MetaData_Extractor
    streamlit run streamlit_indexer.py
    ```

2.  **Enter API Key**:
    You will need a valid Google Gemini API Key. Enter it in the password field when prompted.

## Usage Guide

### Mode 1: Single File Processing
Use this for testing or processing individual PDFs.
1.  Select **"Single File"** from the sidebar.
2.  Upload a PDF.
3.  Click **"Analyze PDF"**.
4.  Wait for Gemini to extract the content.
5.  Review the table of extracted stories.
6.  Click **"Download JSON"** to save the result.

### Mode 2: Bulk Processing
Use this for processing entire years/months of magazines.
1.  Select **"Bulk Processing"** from the sidebar.
2.  Enter the **Input Directory** (e.g., `D:\Chandamama\1951`).
3.  (Optional) Change the Output Directory.
4.  Click **"Start Batch Processing"**.
    - The app will process files one by one.
    - Progress is saved automatically to `_bulk_progress_backup.json`.
    - If you stop the app, it will resume from where it left off.
5.  **Verify & Export**:
    - Below the progress bar, select a file to view its extracted data.
    - Make edits if needed.
    - Click **"Mark as Verified"**.
    - Finally, click **"Generate JSONs for Verified Files"** to export clean JSON files.

## Important Notes

### Global Statistics
- The app maintains a `global_stats.json` file to track total counts.
- **Multi-Terminal Support**: The app now uses **File Locking** to safely handle global stats even when running multiple instances (e.g., 2 terminals).
- You can run `streamlit run ...` on different ports (e.g., 8501, 8502) and process different folders simultaneously without worry.

### Common Errors
- **"API Response format invalid"**:
    - This usually means the model was blocked by safety filters.
    - **Fix**: We have enabled `BLOCK_NONE` safety settings to prevent this for harmless content. Restart the app if you see this.
- **"429 Too Many Requests"**:
    - You are hitting the API rate limit. Wait a minute or close extra terminal instances.