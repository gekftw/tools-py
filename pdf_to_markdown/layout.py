import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Optional

@dataclass
class LayoutBlock:
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    lines: list
    block_type: str  # "text" or "table"
    raw_block: Optional[dict] = None  # Original PyMuPDF block dict

    @property
    def x0(self) -> float: return self.bbox[0]
    @property
    def y0(self) -> float: return self.bbox[1]
    @property
    def x1(self) -> float: return self.bbox[2]
    @property
    def y1(self) -> float: return self.bbox[3]
    @property
    def width(self) -> float: return self.x1 - self.x0
    @property
    def height(self) -> float: return self.y1 - self.y0


class HeaderFooterDetector:
    """
    Detects and filters out document headers, footers, and page numbers
    by examining recurring text in top and bottom margins across pages.
    """
    def __init__(self, top_margin_pct: float = 0.12, bottom_margin_pct: float = 0.12):
        self.top_margin_pct = top_margin_pct
        self.bottom_margin_pct = bottom_margin_pct
        self.recurring_headers: Set[str] = set()
        self.recurring_footers: Set[str] = set()
        
        # Track text frequencies in top and bottom margins across pages
        self.top_text_counts: Dict[str, int] = {}
        self.bottom_text_counts: Dict[str, int] = {}
        self.total_pages_scanned = 0

    def collect_page_candidates(self, page_dict: dict) -> None:
        """
        Gathers candidate headers/footers from a page's top and bottom regions.
        """
        self.total_pages_scanned += 1
        height = page_dict.get("height", 1000)
        top_boundary = height * self.top_margin_pct
        bottom_boundary = height * (1 - self.bottom_margin_pct)

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            
            # Extract plain text for block
            lines_text = []
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    lines_text.append(line_text.strip())
            
            block_text = " ".join(lines_text).strip()
            if not block_text:
                continue

            # Determine position
            x0, y0, x1, y1 = block.get("bbox")
            
            # If block lies entirely or mostly in the top/bottom margins, log it
            if y1 <= top_boundary:
                self.top_text_counts[block_text] = self.top_text_counts.get(block_text, 0) + 1
            elif y0 >= bottom_boundary:
                self.bottom_text_counts[block_text] = self.bottom_text_counts.get(block_text, 0) + 1

    def finalize(self) -> None:
        """
        Identifies recurring header/footer texts that appear on multiple pages.
        """
        threshold = max(2, int(self.total_pages_scanned * 0.35))  # occurs in at least 35% of pages (or min 2 pages)
        
        for text, count in self.top_text_counts.items():
            if count >= threshold:
                self.recurring_headers.add(text)
                
        for text, count in self.bottom_text_counts.items():
            if count >= threshold:
                self.recurring_footers.add(text)

    def is_header_or_footer(self, text: str, bbox: Tuple[float, float, float, float], page_height: float) -> bool:
        """
        Returns True if the block is a header, footer, or page number.
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            return False

        # Regular expressions for typical page numbers
        # E.g., "Page 1", "1 of 10", "Chapter 3 - Page 45", "- 12 -", "[12]"
        page_num_patterns = [
            r'^(page|pg\.?)\s*\d+$',
            r'^\d+\s*/\s*\d+$',
            r'^\d+\s+of\s+\d+$',
            r'^-\s*\d+\s*-$',
            r'^\[\s*\d+\s*\]$',
            r'^\d+$'  # just a single raw digit in margin
        ]
        
        x0, y0, x1, y1 = bbox
        top_boundary = page_height * self.top_margin_pct
        bottom_boundary = page_height * (1 - self.bottom_margin_pct)

        # Check if inside top or bottom margin
        in_top = y1 <= top_boundary
        in_bottom = y0 >= bottom_boundary

        if in_top or in_bottom:
            # Check if it matches recurring texts
            if cleaned_text in self.recurring_headers or cleaned_text in self.recurring_footers:
                return True
            
            # Check pattern-based page numbers
            text_lower = cleaned_text.lower()
            for pattern in page_num_patterns:
                if re.match(pattern, text_lower):
                    return True

        return False


class LayoutSorter:
    """
    Renders visual blocks into a coherent reading order.
    Supports multi-column layouts, page spanning banners (e.g. titles),
    and grids.
    """
    @staticmethod
    def sort_page_blocks(blocks: List[LayoutBlock], page_width: float) -> List[LayoutBlock]:
        """
        Sorts layout blocks on a page to respect visual columns and reading flows.
        """
        if not blocks:
            return []

        # 1. Identify full-width horizontal dividing spans (like title blocks, full width section breaks)
        # We classify a block as "spanning" if it is very wide (e.g. > 65% of page width)
        # and has centered horizontal alignment.
        spanning_blocks: List[LayoutBlock] = []
        regular_blocks: List[LayoutBlock] = []

        for b in blocks:
            # Table is a special block; it can span or be treated in layout flow
            is_wide = b.width >= (page_width * 0.65)
            # Centered condition (horizontal margins are relatively symmetric)
            left_margin = b.x0
            right_margin = page_width - b.x1
            is_centered = abs(left_margin - right_margin) < (page_width * 0.20)

            if b.block_type == "table" or (is_wide and is_centered):
                spanning_blocks.append(b)
            else:
                regular_blocks.append(b)

        # 2. Slice the page vertically into bands defined by these spanning blocks.
        # We sort spanning blocks by their vertical position (y0)
        spanning_blocks.sort(key=lambda b: b.y0)

        # Create bands
        bands: List[Tuple[float, float, Optional[LayoutBlock]]] = []
        current_y = 0.0
        for sb in spanning_blocks:
            # Band above the spanning block
            if sb.y0 > current_y:
                bands.append((current_y, sb.y0, None))
            # The spanning block itself gets its own 1-item band
            bands.append((sb.y0, sb.y1, sb))
            current_y = sb.y1
        # Final band below the last spanning block
        bands.append((current_y, float('inf'), None))

        sorted_blocks: List[LayoutBlock] = []

        for y_start, y_end, span_block in bands:
            if span_block is not None:
                sorted_blocks.append(span_block)
                continue

            # Find regular blocks falling within this vertical band
            band_blocks = [
                b for b in regular_blocks 
                if b.y0 >= y_start - 2 and b.y1 <= y_end + 2
            ]
            if not band_blocks:
                continue

            # 3. Within this horizontal band, check for multi-column structures.
            # We do this by projecting the blocks on the X-axis and finding non-overlapping intervals.
            # If we have 2 columns, we can cluster blocks based on x-coordinates.
            cols = LayoutSorter._detect_columns(band_blocks)
            if len(cols) > 1:
                # Sort columns from left to right
                cols.sort(key=lambda col: col[0])  # col is (col_x_start, col_blocks)
                for _, col_blocks in cols:
                    # Sort blocks within each column from top to bottom
                    col_blocks.sort(key=lambda b: b.y0)
                    sorted_blocks.extend(col_blocks)
            else:
                # Single column flow, sort top-to-bottom
                band_blocks.sort(key=lambda b: b.y0)
                sorted_blocks.extend(band_blocks)

        # Any block left out? (due to strict boundaries)
        # Just in case, append any block in regular_blocks that was not sorted
        sorted_ids = {id(b) for b in sorted_blocks}
        leftover = [b for b in regular_blocks if id(b) not in sorted_ids]
        if leftover:
            leftover.sort(key=lambda b: (b.y0, b.x0))
            sorted_blocks.extend(leftover)

        return sorted_blocks

    @staticmethod
    def _detect_columns(blocks: List[LayoutBlock]) -> List[Tuple[float, List[LayoutBlock]]]:
        """
        Group blocks into columns based on horizontal overlap.
        Returns a list of tuples: (column_x_start, list_of_blocks)
        """
        if not blocks:
            return []

        # Find overlapping horizontal intervals
        # Each block defines an interval [b.x0, b.x1]
        intervals = sorted([(b.x0, b.x1, b) for b in blocks], key=lambda x: x[0])
        
        # Merge intervals to find distinct column boundaries
        merged_columns: List[Tuple[float, float, List[LayoutBlock]]] = []
        for x0, x1, b in intervals:
            if not merged_columns:
                merged_columns.append((x0, x1, [b]))
            else:
                # Check overlap with the last column
                last_cx0, last_cx1, col_blocks = merged_columns[-1]
                # If there's horizontal overlap (or they are extremely close, e.g. within 15pt)
                if x0 <= last_cx1 + 15:
                    # Update column horizontal boundary
                    new_cx1 = max(last_cx1, x1)
                    new_cx0 = min(last_cx0, x0)
                    merged_columns[-1] = (new_cx0, new_cx1, col_blocks + [b])
                else:
                    merged_columns.append((x0, x1, [b]))

        return [(cx0, col_blocks) for cx0, _, col_blocks in merged_columns]
