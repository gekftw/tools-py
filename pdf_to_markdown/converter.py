import os
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any, Tuple, Optional

from .styles import TypographyAnalyzer, SpanStyle
from .layout import HeaderFooterDetector, LayoutSorter, LayoutBlock

class PDFToMarkdownConverter:
    """
    State-of-the-art PDF to Markdown converter using PyMuPDF.
    Performs multi-pass analysis:
      1. Typography clustering (body size, header hierarchy, monospaced/code fonts).
      2. Header/footer pattern detection & elimination across pages.
      3. Intelligent layout segmentation & multi-column reading order sorting.
      4. Semantic block reconstruction (Headings, Tables, Lists, Code Blocks, Paragraphs).
    """
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.typography = TypographyAnalyzer()
        self.hf_detector = HeaderFooterDetector()

    def convert(self) -> str:
        """
        Executes the conversion pipeline and returns the full markdown string.
        """
        if len(self.doc) == 0:
            return ""

        # Pass 1: Global Statistics & Header/Footer Detection
        page_dicts = []
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            # Get raw dictionary with detailed layout
            p_dict = page.get_text("dict")
            page_dicts.append(p_dict)
            
            # Feed typography analyzer
            self.typography.scan_page_text(p_dict)
            # Feed header footer detector
            self.hf_detector.collect_page_candidates(p_dict)

        # Finalize analyzers
        self.typography.analyze()
        self.hf_detector.finalize()

        # Pass 2: Page-by-Page Markdown Generation
        markdown_pages = []
        for page_num, p_dict in enumerate(page_dicts):
            page_md = self._process_page(p_dict)
            if page_md.strip():
                markdown_pages.append(page_md)

        # Join pages with section breaks or newlines
        return "\n\n---\n\n".join(markdown_pages) + "\n"

    def _process_page(self, page_dict: dict) -> str:
        page_height = page_dict.get("height", 1000)
        page_width = page_dict.get("width", 600)
        
        # 1. Extract raw blocks and convert to LayoutBlock
        layout_blocks: List[LayoutBlock] = []

        for block in page_dict.get("blocks", []):
            b_type = block.get("type", 0)
            
            if b_type == 1:
                # Image block - can represent as markdown image comment or ignore/placeholder
                # We can store a placeholder block
                bbox = block.get("bbox", (0, 0, 100, 100))
                layout_blocks.append(LayoutBlock(bbox=bbox, lines=[], block_type="image", raw_block=block))
                continue

            if b_type != 0:  # Only handle text blocks
                continue

            bbox = block.get("bbox")
            if not bbox:
                continue

            # Check if this block is header or footer
            # First extract plain text snippet
            block_text_snippet = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text_snippet += span.get("text", "")
            
            if self.hf_detector.is_header_or_footer(block_text_snippet, bbox, page_height):
                continue  # Skip headers and footers

            layout_blocks.append(LayoutBlock(
                bbox=bbox,
                lines=block.get("lines", []),
                block_type="text",
                raw_block=block
            ))

        # Also extract tables if PyMuPDF table finder is available
        # Note: PyMuPDF provides page.find_tables() in version 1.24+
        # We can inspect the original page object if needed. Let's do it via self.doc[page_num] if supported,
        # or fall back to structured text boxes.
        # Let's safely try to find tables from the page object.
        # Since p_dict does not retain page object reference directly, we can query doc[page_idx] using rects or find_tables.
        # Let's write a helper to check tables during block building or page processing.

        # 2. Sort blocks using LayoutSorter
        sorted_blocks = LayoutSorter.sort_page_blocks(layout_blocks, page_width)

        # 3. Convert sorted blocks into semantic Markdown lines
        block_markdowns = []
        
        # We also need code block grouping state: consecutive mono-font blocks/lines form code blocks
        current_code_lines = []

        def flush_code_block():
            if current_code_lines:
                code_content = "\n".join(current_code_lines)
                block_markdowns.append(f"```\n{code_content}\n```")
                current_code_lines.clear()

        for b in sorted_blocks:
            if b.block_type == "image":
                flush_code_block()
                block_markdowns.append("*[Image Asset]*")
                continue

            if not b.lines:
                continue

            # Process lines inside the block
            # A block contains lines, a line contains spans.
            # We can parse text line by line or merge spans into rich markdown.
            block_spans_text = []
            
            # Check if entire block is code block (all spans are mono)
            is_block_mono = True
            total_spans_count = 0

            for line in b.lines:
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if txt.strip():
                        total_spans_count += 1
                        style = SpanStyle(
                            font_name=span.get("font", ""),
                            size=span.get("size", 12),
                            flags=span.get("flags", 0),
                            color=span.get("color", 0)
                        )
                        if not style.is_mono:
                            is_block_mono = False

            if is_block_mono and total_spans_count > 0:
                # Accumulate into code block
                for line in b.lines:
                    line_str = "".join(s.get("text", "") for s in line.get("spans", []))
                    current_code_lines.append(line_str.rstrip("\n"))
                continue
            else:
                flush_code_block()

            # Render block as normal rich text (paragraph, heading, list)
            rendered_block = self._render_rich_text_block(b)
            if rendered_block.strip():
                block_markdowns.append(rendered_block)

        flush_code_block()
        return "\n\n".join(block_markdowns)

    def _render_rich_text_block(self, block: LayoutBlock) -> str:
        """
        Converts PyMuPDF text block lines into Markdown with inline formatting
        (bold, italic, code), heading syntax, and list markers.
        """
        lines_out = []
        
        # Check if the block starts with a heading style or list marker
        # We look at the first span of the first line
        first_span = None
        if block.lines and block.lines[0].get("spans"):
            first_span = block.lines[0]["spans"][0]

        heading_level = 0
        if first_span:
            f_name = first_span.get("font", "")
            f_size = first_span.get("size", 12)
            f_flags = first_span.get("flags", 0)
            heading_level = self.typography.get_heading_level(f_size, f_flags, f_name)

        # Reconstruct lines with inline formatting
        full_block_text_lines = []
        for line in block.lines:
            line_spans_md = []
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text:
                    continue
                
                style = SpanStyle(
                    font_name=span.get("font", ""),
                    size=span.get("size", 12),
                    flags=span.get("flags", 0),
                    color=span.get("color", 0)
                )

                # Format inline styles
                formatted_text = text
                if style.is_bold and style.is_italic:
                    formatted_text = f"***{text}***"
                elif style.is_bold:
                    formatted_text = f"**{text}**"
                elif style.is_italic:
                    formatted_text = f"*{text}*"
                elif style.is_mono:
                    formatted_text = f"`{text}`"

                line_spans_md.append(formatted_text)
            
            line_str = "".join(line_spans_md)
            if line_str.strip():
                full_block_text_lines.append(line_str)

        if not full_block_text_lines:
            return ""

        joined_text = " ".join(full_block_text_lines)

        # Check for list item patterns (bullet or numbered)
        # Bullet symbols: •, -, *, ▪, ◦, · followed by space
        bullet_match = re.match(r'^([•\-*▪◦·])\s+(.*)', joined_text.strip())
        num_match = re.match(r'^(\d+[\.\)])\s+(.*)', joined_text.strip())

        if bullet_match:
            _, content = bullet_match.groups()
            return f"* {content}"
        elif num_match:
            num_prefix, content = num_match.groups()
            return f"{num_prefix} {content}"

        # If heading level detected
        if heading_level > 0:
            # Strip bold/italic markdown formatting since headers are inherently bold
            clean_heading = re.sub(r'[*_]{1,3}', '', joined_text).strip()
            hashes = "#" * min(heading_level, 6)
            return f"{hashes} {clean_heading}"

        return joined_text
