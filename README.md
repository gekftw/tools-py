# PDF-to-Markdown Optimized Converter

A lightning-fast, high-fidelity PDF to Markdown converter written in Python, powered by **PyMuPDF** (fitz). It implements a cohesive, multi-pass layout analysis algorithm designed to preserve document structure, typography, multi-column flows, code blocks, lists, and clean heading hierarchies.

---

## Key Features

1. **Robust Typography Clustering (`styles.py`)**:
   - Automatically detects the document's primary body font size.
   - Uses 1D agglomerative clustering on font sizes to establish a clean, adaptive Markdown heading hierarchy (`#` to `######`).
   - Parses PyMuPDF font flags and font metadata to detect **bold**, *italics*, and `monospaced` code fonts.

2. **Multi-Column & Zone-Based Layout Sorting (`layout.py`)**:
   - Detects wide spanning banners (e.g., titles, section breaks) to slice pages into horizontal vertical bands.
   - Performs projection-based column detection on horizontal bands to sort multi-column layouts into correct left-to-right reading order.

3. **Header, Footer & Page Number Removal (`layout.py`)**:
   - Scans document margins across pages to identify and suppress recurring running headers, footers, and page number patterns (`Page X`, `X of Y`, `- X -`).

4. **Semantic Block Reconstruction (`converter.py`)**:
   - Converts headings, paragraphs, bullet/numbered lists (`*`, `1.`), and code blocks (` ``` `) into clean Markdown.

---

## Installation & Setup

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install pymupdf pytest
   ```

---

## Usage

### Command Line Interface (CLI)

Convert a PDF and save to a Markdown file:
```bash
python3 -m pdf_to_markdown.cli input.pdf -o output.md
```

Print converted Markdown to `stdout`:
```bash
python3 -m pdf_to_markdown.cli input.pdf
```

### Python API

```python
from pdf_to_markdown import PDFToMarkdownConverter

converter = PDFToMarkdownConverter("path/to/document.pdf")
markdown_content = converter.convert()

print(markdown_content)
```

---

## Testing

Run the comprehensive test suite with pytest:
```python
PYTHONPATH=. .venv/bin/pytest -v
```
