# 📄 AI PDF Data Extractor and Verifier

Welcome to the **AI PDF Data Extractor and Verifier**! This robust desktop application streamlines the extraction of complex data from PDF documents—such as Actuarial Valuation reports—using the power of Google's Gemini LLMs. It then systematically verifies the extracted data against the original PDF content and allows users to manually counter-check and update information via an intuitive side-by-side interface. Finally, it seamlessly merges the approved data directly into your Excel spreadsheets.

---

## 🎥 Video Demo



https://github.com/user-attachments/assets/e8e911a9-15ea-4450-a81b-293f1dc0ef90



---

## ✨ Key Features

*   **🚀 Automated Batch Extraction**: Process hundreds of PDFs automatically using the Google Gemini API (supporting both Batch API for cost-effective large runs and One-by-One processing).
*   **🔍 Intelligent Verification Engine**: Automatically cross-references the AI-extracted JSON data (values and page numbers) with the actual text within the PDF to catch hallucinations or missed context keywords.
*   **✅ Interactive Counter-Check UI**: 
    *   Review flagged verification problems in a powerful side-by-side or stacked layout.
    *   Built-in PDF viewer with automatic page jumping and custom zoom.
    *   Visual highlighting: search terms are highlighted in yellow, and extracted values are highlighted in orange directly on the PDF.
*   **📊 Excel Data Merging**: Instantly merge your verified JSON data back into your master Excel sheets based on document matching.
*   **💾 Session Persistence**: Safely close and reopen the app without losing your configured folders, JSON files, or API settings.
*   **🎛️ Modular Architecture**: Clean separation between core background processing threads and the PyQt5 frontend for smooth, non-blocking UI experiences.

---

## 🛠️ Technologies & Architecture

**Technologies Used:**
*   **Language**: Python 3
*   **GUI Framework**: PyQt5 (using QThread for background asynchronous tasks)
*   **AI Integration**: `google-genai` (Google Gemini 3.5 Flash / 3.1 Pro via File API)
*   **PDF Processing**: `PyMuPDF` (fitz) for text extraction, highlighting, and rendering.
*   **Data Handling**: `openpyxl` for reading and merging data into Excel workbooks, and native `json` for data persistence.

**Architecture Overview:**
The application is divided into a `core/` backend and a `ui/` frontend. The `MainWindow` orchestrates a tabbed interface (Batch Processing, Verify Results, Counter Check). Background workers (`ProcessingThread`, `VerificationThread`, `MergeThread`) handle heavy tasks like API communication and PDF text searching, preventing the UI from freezing.

---

## 📂 Project Structure

```text
├── main_app.py                      # Main entry point and Tab manager
├── start_extraction.bat             # Quick launch script
├── Extraction_Prompt Updated.txt    # The core system prompt passed to Gemini
├── core/                            # Core Backend Logic
│   ├── batch_processor.py           # Gemini API uploading and batch handling
│   ├── excel_merger.py              # Logic for mapping JSON to Excel rows
│   ├── pdf_cleaner.py               # Pre-processing PDFs before API upload
│   ├── verifier.py                  # Cross-referencing JSON with PDF text
│   └── session.py                   # Managing local session state
└── ui/                              # User Interface Components
    ├── batch_tab.py                 # Step 1: Extraction & Merging UI
    ├── verify_tab.py                # Step 2: Verification Engine UI
    ├── counter_check_tab.py         # Step 3: PDF Viewer & Editor UI
    ├── dialogs.py                   # Reusable popups and API settings
    └── previous_jobs_dialog.py      # Resuming and downloading Gemini batches
```

---

## ⚙️ Prerequisites & Setup

### 1. Install Dependencies
Ensure you have Python installed. You will need to install the required packages:
```bash
pip install PyQt5 google-genai pymupdf openpyxl
```

### 2. Google Gemini API Setup
To use the AI extraction, you need a Google Gemini API Key.
1. Go to Google AI Studio (aistudio.google.com).
2. Create a new API Key in the API Keys section.
3. Open the application, go to the **Batch Processing** tab, and click **🔑 API Settings**.
4. Paste your API Key and save.

---

## 📝 How to Use & Change Parameters

### Adjusting the Extraction Prompt
The AI's behavior is dictated by the `Extraction_Prompt Updated.txt` file. 
*   **To change what data is extracted**: Open this file and update the requested JSON structure and instructions. 
*   **To select a different prompt file**: Click **🔑 API Settings** in the app and browse for a different `.txt` file.

### Changing the AI Model
By default, the application uses `gemini-3.5-flash`.
*   Click **🔑 API Settings**.
*   Select or type a different model in the dropdown (e.g., `gemini-3.1-pro-preview` or `gemini-2.5-pro`).

### Running the Workflow
1.  **Batch Processing**: Select your folder of PDFs, set your API key, and click Process. Once complete, select your target Excel file to merge.
2.  **Verify Results**: Select the output JSON from Step 1 and the folder of cleaned PDFs. Run the verification to generate a list of discrepancies.
3.  **Counter Check**: Use this tab to manually navigate through flagged PDFs. Update the extracted values and hit "Update" to save directly to the JSON file before a final Excel merge.

---

## 🔒 Privacy & Security Notes

*   **Cloud Processing**: PDF documents are uploaded to Google's servers via the Gemini File API for processing. Please ensure you comply with your organization's data privacy policies regarding uploading sensitive or confidential Actuarial Valuation documents to third-party cloud services.
*   **Local Storage**: Extracted data, session keys, and modified PDFs are saved entirely on your local machine.
*   **API Key Security**: Your API key is stored locally in the session configuration. Do not commit your session files or hardcoded keys to version control.
