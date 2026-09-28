import argparse
import sys
import time
from pathlib import Path
from .converter import PDFToMarkdownConverter

def main():
    parser = argparse.ArgumentParser(
        description="A highly optimized, layout-aware PDF to Markdown converter using Python & PyMuPDF."
    )
    parser.add_argument("input_pdf", type=str, help="Path to the input PDF file.")
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to save the output Markdown file. If omitted, prints to stdout."
    )
    
    args = parser.parse_args()

    pdf_path = Path(args.input_pdf)
    if not pdf_path.exists():
        print(f"Error: PDF file '{pdf_path}' not found.", file=sys.stderr)
        sys.exit(1)

    start_time = time.time()
    try:
        converter = PDFToMarkdownConverter(str(pdf_path))
        markdown_content = converter.convert()
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start_time

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(markdown_content, encoding="utf-8")
        print(f"Successfully converted '{pdf_path.name}' to '{out_path}' in {elapsed:.2f}s", file=sys.stderr)
    else:
        sys.stdout.write(markdown_content)

if __name__ == "__main__":
    main()
