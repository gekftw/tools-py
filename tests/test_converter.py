import pytest
import fitz
from pathlib import Path
from pdf_to_markdown.styles import TypographyAnalyzer, SpanStyle
from pdf_to_markdown.layout import LayoutSorter, LayoutBlock, HeaderFooterDetector
from pdf_to_markdown.converter import PDFToMarkdownConverter

def create_sample_pdf(tmp_path: Path) -> str:
    """
    Creates a simple programmatic PDF file for testing conversion and layout analysis.
    """
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()

    # Insert a title
    page.insert_text((50, 50), "Document Title", fontsize=24, fontname="Helvetica-Bold")
    
    # Insert heading
    page.insert_text((50, 100), "1. Introduction", fontsize=16, fontname="Helvetica-Bold")
    
    # Insert body paragraph
    page.insert_text((50, 130), "This is a body paragraph with normal text.", fontsize=11, fontname="Helvetica")
    
    # Insert a bullet list item
    page.insert_text((50, 160), "• First bullet point", fontsize=11, fontname="Helvetica")

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_span_style():
    style = SpanStyle(font_name="Helvetica-Bold", size=14.0, flags=16, color=0)
    assert style.is_bold is True
    assert style.is_italic is False
    assert style.is_mono is False

    mono_style = SpanStyle(font_name="Courier", size=10.0, flags=8, color=0)
    assert mono_style.is_mono is True

def test_typography_analyzer():
    analyzer = TypographyAnalyzer()
    # Mock page dict
    page_dict = {
        "blocks": [
            {
                "type": 0,
                "lines": [
                    {
                        "spans": [
                            {"text": "Body text here", "font": "Helvetica", "size": 11.0, "flags": 0},
                            {"text": "Heading text", "font": "Helvetica-Bold", "size": 18.0, "flags": 16}
                        ]
                    }
                ]
            }
        ]
    }
    analyzer.scan_page_text(page_dict)
    analyzer.analyze()
    
    assert analyzer.body_size == 11.0
    assert analyzer.get_heading_level(18.0, 16, "Helvetica-Bold") == 1

def test_header_footer_detector():
    detector = HeaderFooterDetector(top_margin_pct=0.1, bottom_margin_pct=0.1)
    
    # Page height = 800. Top margin is y <= 80.
    page_dict = {
        "height": 800,
        "blocks": [
            {
                "type": 0,
                "bbox": [50, 20, 200, 40],
                "lines": [{"spans": [{"text": "Confidential Report"}]}]
            }
        ]
    }
    
    detector.collect_page_candidates(page_dict)
    detector.collect_page_candidates(page_dict)  # twice to pass threshold
    detector.finalize()
    
    assert detector.is_header_or_footer("Confidential Report", (50, 20, 200, 40), 800) is True
    assert detector.is_header_or_footer("Page 5", (300, 780, 350, 795), 800) is True

def test_layout_sorter():
    b1 = LayoutBlock(bbox=(50, 100, 250, 150), lines=[], block_type="text")
    b2 = LayoutBlock(bbox=(50, 50, 550, 80), lines=[], block_type="text")  # wide spanning banner
    b3 = LayoutBlock(bbox=(300, 100, 500, 150), lines=[], block_type="text")

    sorted_blocks = LayoutSorter.sort_page_blocks([b1, b2, b3], page_width=600)
    # b2 is spanning banner at top, should come first
    assert sorted_blocks[0] == b2

def test_end_to_end_conversion(tmp_path):
    pdf_path = create_sample_pdf(tmp_path)
    converter = PDFToMarkdownConverter(pdf_path)
    md = converter.convert()

    assert "# Document Title" in md or "Document Title" in md
    assert "1. Introduction" in md
    assert "This is a body paragraph" in md
    assert "* First bullet point" in md
