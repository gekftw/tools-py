import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Set

# PyMuPDF font flags (binary bitmask values)
# Bit 0: Superscript/Subscript
# Bit 1: Italic
# Bit 2: Serifed
# Bit 3: Monospaced
# Bit 4: Bold
FONT_FLAG_SUPER = 1
FONT_FLAG_ITALIC = 2
FONT_FLAG_SERIF = 4
FONT_FLAG_MONO = 8
FONT_FLAG_BOLD = 16

@dataclass(frozen=True)
class SpanStyle:
    font_name: str
    size: float
    flags: int
    color: int

    @property
    def is_bold(self) -> bool:
        # Check standard PyMuPDF flags
        if self.flags & FONT_FLAG_BOLD:
            return True
        # Fallback check on font name
        name_lower = self.font_name.lower()
        return any(x in name_lower for x in ["bold", "black", "heavy", "medium", "semibold"])

    @property
    def is_italic(self) -> bool:
        if self.flags & FONT_FLAG_ITALIC:
            return True
        name_lower = self.font_name.lower()
        return any(x in name_lower for x in ["italic", "oblique", "slanted"])

    @property
    def is_mono(self) -> bool:
        if self.flags & FONT_FLAG_MONO:
            return True
        name_lower = self.font_name.lower()
        return any(x in name_lower for x in ["mono", "courier", "consolas", "code", "fixed"])


class TypographyAnalyzer:
    """
    Analyzes document typography to adaptively determine headers, body text,
    and code block font sizes using robust 1D clustering on font metadata.
    """
    def __init__(self):
        self.font_frequencies: Dict[Tuple[str, float, int], int] = {}
        self.size_frequencies: Dict[float, int] = {}
        self.body_size: float = 12.0
        self.heading_map: Dict[float, int] = {}  # Maps font size to Markdown heading level (1-6)
        self.caption_sizes: Set[float] = set()

    def scan_page_text(self, page_dict: dict) -> None:
        """
        Scans a PyMuPDF page dictionary ("dict") to gather typography statistics.
        """
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # Only process text blocks
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    
                    font_name = span.get("font", "")
                    size = round(span.get("size", 1), 2)
                    flags = span.get("flags", 0)
                    length = len(text)

                    key = (font_name, size, flags)
                    self.font_frequencies[key] = self.font_frequencies.get(key, 0) + length
                    self.size_frequencies[size] = self.size_frequencies.get(size, 0) + length

    def analyze(self) -> None:
        """
        Runs clustering and classification to establish markdown mapping rules.
        """
        if not self.size_frequencies:
            return

        # 1. Determine body text font size (most frequent size in the entire document)
        self.body_size = max(self.size_frequencies, key=self.size_frequencies.get)

        # 2. Cluster font sizes to group similar sizes (e.g. 10.9pt and 11.0pt)
        # We perform simple agglomerative 1D clustering with a threshold of 1.2pt
        sorted_sizes = sorted(self.size_frequencies.keys())
        clusters: List[List[float]] = []
        for s in sorted_sizes:
            if not clusters:
                clusters.append([s])
            else:
                last_cluster = clusters[-1]
                # If close enough, merge into current cluster
                if s - last_cluster[-1] <= 1.2:
                    last_cluster.append(s)
                else:
                    clusters.append([s])

        # For each cluster, we compute a weighted average or representative size (usually the most frequent)
        cluster_representatives: Dict[float, List[float]] = {}
        for cluster in clusters:
            # Find size in cluster with highest character count
            rep_size = max(cluster, key=lambda sz: self.size_frequencies.get(sz, 0))
            cluster_representatives[rep_size] = cluster

        # Classify clusters relative to body text size
        # We classify representatives:
        reps = sorted(cluster_representatives.keys())
        
        # Heading candidates are representatives significantly larger than body size (e.g., > body_size + 1.0)
        heading_reps = [r for r in reps if r >= self.body_size + 1.0]
        
        # Sort headings descending (largest size is H1)
        heading_reps.sort(reverse=True)
        
        # Map each heading representative to Markdown heading levels H1-H6
        temp_heading_map = {}
        for idx, h_rep in enumerate(heading_reps[:6]):
            # level is 1-indexed (idx + 1)
            temp_heading_map[h_rep] = idx + 1

        # Populate the final heading map for all sizes in those clusters
        self.heading_map.clear()
        for h_rep, level in temp_heading_map.items():
            for size in cluster_representatives[h_rep]:
                self.heading_map[size] = level

        # Caption sizes are significantly smaller than the body size (e.g. < body_size - 1.5)
        self.caption_sizes.clear()
        for rep in reps:
            if rep <= self.body_size - 1.5:
                for size in cluster_representatives[rep]:
                    self.caption_sizes.add(size)

    def get_heading_level(self, size: float, flags: int, font_name: str) -> int:
        """
        Returns heading level (1 to 6) or 0 if not a heading.
        Even if font size is close to body size, if it is explicitly bold and we want to
        treat it as subheading or it is mapped as a heading cluster, handle it.
        """
        rounded_size = round(size, 2)
        # First check the pre-analyzed heading map
        if rounded_size in self.heading_map:
            return self.heading_map[rounded_size]
        
        # Fallback: if size is slightly larger than body and font is bold
        style = SpanStyle(font_name=font_name, size=size, flags=flags, color=0)
        if rounded_size >= self.body_size and style.is_bold:
            # Treat as h4, h5 or h6 depending on size
            diff = rounded_size - self.body_size
            if diff >= 2.5:
                return 3
            elif diff >= 1.0:
                return 4
            else:
                return 5
                
        return 0

    def is_caption_or_footnote(self, size: float) -> bool:
        return round(size, 2) in self.caption_sizes
