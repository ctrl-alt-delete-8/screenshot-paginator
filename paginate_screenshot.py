#!/usr/bin/env python3
"""
Intelligent Screenshot Paginator

Splits long scrolling screenshots into pages with 9:16 aspect ratio,
cutting only at natural gaps (pure-color horizontal lines) to avoid
splitting content mid-line.

"""

from PIL import Image
import numpy as np
from typing import List, Tuple
from pathlib import Path
import argparse


class GapDetector:
    """Detects gaps (pure-color lines) in an image, both horizontal and vertical."""

    def __init__(self, tolerance: int = 5):
        """
        Args:
            tolerance: Maximum color variance to consider a line "pure color"
        """
        self.tolerance = tolerance

    def _is_pure_color(self, pixels_1d: np.ndarray) -> bool:
        """Check if a 1D slice of pixels is a single pure color."""
        if len(pixels_1d.shape) == 2:  # RGB/RGBA — shape (N, channels)
            std_devs = np.std(pixels_1d, axis=0)
            return bool(np.all(std_devs <= self.tolerance))
        else:  # Grayscale
            return float(np.std(pixels_1d)) <= self.tolerance

    def _find_gaps(self, pixels: np.ndarray, axis: int) -> List[Tuple[int, int]]:
        """
        Find gap groups along an axis.

        Args:
            pixels: Image pixel array (H, W, C)
            axis: 0 for horizontal gaps (scan rows), 1 for vertical gaps (scan columns)

        Returns:
            List of (start, end) tuples representing gap groups
        """
        length = pixels.shape[0] if axis == 0 else pixels.shape[1]

        gap_groups = []
        in_gap = False
        gap_start = 0

        for i in range(length):
            line = pixels[i] if axis == 0 else pixels[:, i]
            is_gap = self._is_pure_color(line)

            if is_gap and not in_gap:
                gap_start = i
                in_gap = True
            elif not is_gap and in_gap:
                gap_groups.append((gap_start, i - 1))
                in_gap = False

        if in_gap:
            gap_groups.append((gap_start, length - 1))

        return gap_groups

    def find_gap_groups(self, image: Image.Image) -> List[Tuple[int, int]]:
        """Find horizontal gap groups (pure-color rows)."""
        return self._find_gaps(np.array(image), axis=0)

    def find_vertical_gap_groups(self, image: Image.Image) -> List[Tuple[int, int]]:
        """Find vertical gap groups (pure-color columns)."""
        return self._find_gaps(np.array(image), axis=1)

    @staticmethod
    def get_gap_midlines(gap_groups: List[Tuple[int, int]]) -> List[int]:
        """Calculate the midline (center) of each gap group."""
        return [(start + end) // 2 for start, end in gap_groups]


class PageOptimizer:
    """Optimizes page splits to achieve target aspect ratio."""

    def __init__(self, target_ratio: float = 16/9):
        """
        Args:
            target_ratio: Target height/width ratio (default 16:9)
        """
        self.target_ratio = target_ratio

    def calculate_score(self, height: int, width: int) -> float:
        """
        Calculate how close a page is to the target ratio.
        Lower score is better.

        Args:
            height: Page height in pixels
            width: Page width in pixels

        Returns:
            Score (0 = perfect match)
        """
        actual_ratio = height / width
        return abs(actual_ratio - self.target_ratio)

    def find_optimal_cuts(
        self,
        total_length: int,
        breadth: int,
        cut_points: List[int],
        override_ideal: int = None,
        reverse: bool = False
    ) -> List[int]:
        """
        Select optimal cut points to create pages close to target ratio.

        Uses a greedy algorithm. When reverse=False, starts from position 0
        (left/top edge) — remainder falls on the last page (right/bottom).
        When reverse=True, starts from the far edge (right/bottom) —
        remainder falls on the first page (left/top), which is last in
        right-to-left reading order.

        Args:
            total_length: Total extent along the split axis (height or width)
            breadth: Extent along the other axis (width or height)
            cut_points: Available coordinates where cuts can be made
            override_ideal: If set, use as ideal page extent per page
            reverse: If True, greedy from far edge backward

        Returns:
            Selected cut points (sorted ascending, including 0 and total_length)
        """
        if not cut_points:
            return []

        all_points = sorted(set([0] + cut_points + [total_length]))
        ideal = override_ideal if override_ideal else int(breadth * self.target_ratio)

        # Like printing: fill each page as much as possible (up to ideal),
        # remainder goes on the next page no matter how small.
        # No strip may exceed ideal — otherwise content overflows the page.

        if reverse:
            # Greedy from the far edge backward (RTL reading)
            selected_cuts = [total_length]
            current_end = total_length

            while current_end > 0:
                available = [p for p in all_points if p < current_end]
                if not available:
                    break

                # Remainder fits in one page → take it all
                if current_end <= ideal:
                    selected_cuts.append(0)
                    break

                # Target: fill this page to ideal
                target = current_end - ideal

                # Pick the gap closest to target FROM ABOVE (≥ target)
                # This maximizes the strip size without exceeding ideal
                at_or_above = [p for p in available if p >= target]
                if at_or_above:
                    best_cut = min(at_or_above)  # closest to target from above
                else:
                    # All gaps are below target — pick the highest one
                    # (strip will exceed ideal, but no better option)
                    best_cut = max(available)

                selected_cuts.append(best_cut)
                current_end = best_cut

            if selected_cuts[-1] != 0:
                selected_cuts.append(0)

            return sorted(selected_cuts)

        else:
            # Greedy from position 0 forward (LTR / top-to-bottom)
            selected_cuts = [0]
            current_start = 0

            while current_start < total_length:
                available = [p for p in all_points if p > current_start]
                if not available:
                    break

                # Remainder fits in one page → take it all
                remaining = total_length - current_start
                if remaining <= ideal:
                    selected_cuts.append(total_length)
                    break

                # Target: fill this page to ideal
                target = current_start + ideal

                # Pick the gap closest to target FROM BELOW (≤ target)
                # This maximizes the strip size without exceeding ideal
                at_or_below = [p for p in available if p <= target]
                if at_or_below:
                    best_cut = max(at_or_below)  # closest to target from below
                else:
                    # All gaps are above target — pick the lowest one
                    # (strip will exceed ideal, but no better option)
                    best_cut = min(available)

                selected_cuts.append(best_cut)
                current_start = best_cut

            if selected_cuts[-1] != total_length:
                selected_cuts.append(total_length)

            return selected_cuts


class ScreenshotPaginator:
    """Main class for paginating screenshots."""

    def __init__(
        self,
        tolerance: int = 5,
        target_ratio: float = 16/9
    ):
        """
        Args:
            tolerance: Color variance tolerance for gap detection
            target_ratio: Target page aspect ratio (height/width)
        """
        self.gap_detector = GapDetector(tolerance)
        self.page_optimizer = PageOptimizer(target_ratio)

    def paginate(
        self,
        input_path: str,
        output_dir: str = ".",
        output_prefix: str = "page",
        padding: int = 20,
        margins: Tuple[int, int, int, int] = None,
        direction: str = "horizontal",
        pdf_path: str = None,
        pdf_size_cm: Tuple[float, float] = None,
        pdf_dpi: int = 300
    ) -> List[str]:
        """
        Paginate a long screenshot into multiple pages.

        Args:
            input_path: Path to input screenshot
            output_dir: Directory for output pages
            output_prefix: Prefix for output filenames
            padding: Padding in pixels (default: 20, ignored if margins set)
            margins: Optional (top, right, bottom, left) in pixels.
            direction: "horizontal" (top→bottom),
                       "vertical-ltr" (left→right),
                       "vertical-rtl" (right→left, for tategaki/manga).
            pdf_path: If set, export all pages as a single PDF.
            pdf_size_cm: (width_cm, height_cm) for PDF page size.
            pdf_dpi: DPI for PDF rendering (default: 300).

        Returns:
            List of output file paths
        """
        # Load image
        print(f"Loading image: {input_path}")
        image = Image.open(input_path)
        width, height = image.size

        print(f"Image dimensions: {width}x{height}")

        vertical = direction.startswith("vertical")
        rtl = (direction == "vertical-rtl")

        # Detect gaps
        if vertical:
            print("Detecting vertical gaps...")
            gap_groups = self.gap_detector.find_vertical_gap_groups(image)
        else:
            print("Detecting horizontal gaps...")
            gap_groups = self.gap_detector.find_gap_groups(image)
        print(f"Found {len(gap_groups)} gap groups")

        gap_midlines = self.gap_detector.get_gap_midlines(gap_groups)

        if vertical:
            total_length = width
            breadth = height
        else:
            total_length = height
            breadth = width

        if not gap_midlines:
            print("Warning: No gaps found. Creating single page.")
            gap_midlines = [total_length]

        # Determine margin mode
        if margins:
            m_top, m_right, m_bottom, m_left = margins
            if vertical:
                page_h_fixed = breadth + m_top + m_bottom
                target_page_w = int(page_h_fixed / self.page_optimizer.target_ratio)
                content_area_length = target_page_w - m_left - m_right
                if content_area_length <= 0:
                    raise ValueError(
                        f"Margins too large: left({m_left}) + right({m_right}) = {m_left + m_right} "
                        f"exceeds target page width {target_page_w}")
                print(f"Margin mode (vertical): page {target_page_w}x{page_h_fixed}, "
                      f"margins T{m_top}/R{m_right}/B{m_bottom}/L{m_left}, "
                      f"content area {content_area_length}x{breadth}")
            else:
                page_width = breadth + m_left + m_right
                page_height_from_ratio = int(page_width * self.page_optimizer.target_ratio)
                content_area_length = page_height_from_ratio - m_top - m_bottom
                if content_area_length <= 0:
                    raise ValueError(
                        f"Margins too large: top({m_top}) + bottom({m_bottom}) = {m_top + m_bottom} "
                        f"exceeds page height {page_height_from_ratio}")
                print(f"Margin mode: page {page_width}x{page_height_from_ratio}, "
                      f"margins T{m_top}/R{m_right}/B{m_bottom}/L{m_left}, "
                      f"content area {breadth}x{content_area_length}")
        else:
            m_top, m_right, m_bottom, m_left = 0, padding, 0, padding
            content_area_length = None

        # Find optimal cut points
        dir_label = {"horizontal": "top→bottom", "vertical-ltr": "left→right", "vertical-rtl": "right→left"}
        print(f"Optimizing page splits ({dir_label[direction]})...")
        if vertical:
            ideal = int(breadth / self.page_optimizer.target_ratio) if not content_area_length else None
            cut_points = self.page_optimizer.find_optimal_cuts(
                total_length, breadth, gap_midlines,
                override_ideal=content_area_length or ideal,
                reverse=rtl
            )
        else:
            cut_points = self.page_optimizer.find_optimal_cuts(
                total_length, breadth, gap_midlines,
                override_ideal=content_area_length
            )

        num_pages = len(cut_points) - 1
        print(f"Creating {num_pages} pages...")

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Calculate uniform page dimensions
        if margins:
            if vertical:
                uniform_w = target_page_w
                uniform_h = page_h_fixed
            else:
                uniform_w = breadth + m_left + m_right
                uniform_h = page_height_from_ratio
        else:
            if vertical:
                ideal_content_w = int(breadth / self.page_optimizer.target_ratio)
                uniform_w = ideal_content_w + m_left + m_right
                uniform_h = breadth
            else:
                ideal_content_h = int(breadth * self.page_optimizer.target_ratio)
                uniform_w = breadth + m_left + m_right
                uniform_h = ideal_content_h

        print(f"Uniform page size: {uniform_w}x{uniform_h} "
              f"(ratio: {uniform_h/uniform_w:.3f})")

        # Remainder page index:
        # RTL: greedy starts from right, remainder is at index 0 (leftmost)
        # LTR: greedy starts from left, remainder is at index -1 (rightmost/bottommost)
        last_page_idx = 0 if rtl else (num_pages - 1)

        # Extract pages
        output_files = []
        for i in range(num_pages):
            start = cut_points[i]
            end = cut_points[i + 1]
            is_last = (i == last_page_idx)

            if vertical:
                page_content = image.crop((start, 0, end, height))
                content_w = end - start
                content_h = height
            else:
                page_content = image.crop((0, start, width, end))
                content_w = width
                content_h = end - start

            page = Image.new('RGB', (uniform_w, uniform_h), color='white')

            if is_last and num_pages > 1:
                # Remainder page: align content to the reading-start edge
                if vertical:
                    if rtl:
                        # RTL remainder (leftmost): content flush right
                        paste_x = uniform_w - m_right - content_w
                    else:
                        # LTR remainder (rightmost): content flush left
                        paste_x = m_left
                    paste_y = m_top if margins else 0
                else:
                    # Horizontal remainder (bottom): content flush top
                    paste_x = m_left
                    paste_y = m_top if margins else 0
            else:
                # Normal pages: center content along the split axis
                if vertical:
                    paste_x = (uniform_w - content_w) // 2
                    paste_y = m_top if margins else 0
                else:
                    paste_x = m_left
                    if margins:
                        paste_y = m_top + (content_area_length - content_h) // 2 \
                                  if content_area_length and content_h < content_area_length else m_top
                    else:
                        paste_y = (uniform_h - content_h) // 2

            page.paste(page_content, (paste_x, paste_y))

            output_file = output_path / f"{output_prefix}_{i+1:03d}.png"
            page.save(output_file, "PNG")
            output_files.append(str(output_file))

            axis_label = "x" if vertical else "y"
            align = ("right" if rtl else "left") if (is_last and vertical and num_pages > 1) else \
                    "top" if (is_last and not vertical and num_pages > 1) else "center"
            print(f"  Page {i+1}: {uniform_w}x{uniform_h} "
                  f"(content: {content_w}x{content_h}, {axis_label}: {start}-{end}, align: {align})")

        # RTL: reverse page numbering (page 1 = rightmost)
        if rtl and len(output_files) > 1:
            print(f"\nApplying RTL page order (right→left)...")
            total = len(output_files)
            renamed_files = []
            for i, old_path in enumerate(output_files):
                tmp_file = output_path / f"_rtl_tmp_{i:03d}.png"
                Path(old_path).rename(tmp_file)
                renamed_files.append(tmp_file)
            for i, tmp_file in enumerate(renamed_files):
                new_num = total - i
                new_file = output_path / f"{output_prefix}_{new_num:03d}.png"
                tmp_file.rename(new_file)
            output_files = [str(output_path / f"{output_prefix}_{j:03d}.png")
                           for j in range(1, total + 1)]
            print(f"  Page 1 = rightmost, Page {total} = leftmost")

        print(f"\n✓ Successfully created {len(output_files)} pages")

        # PDF export
        if pdf_path:
            self._export_pdf(output_files, pdf_path, pdf_size_cm, pdf_dpi)

        return output_files

    @staticmethod
    def _export_pdf(
        page_files: List[str],
        pdf_path: str,
        size_cm: Tuple[float, float] = None,
        dpi: int = 300
    ):
        """Export page images as a single PDF."""
        if not page_files:
            return

        images = [Image.open(f).convert('RGB') for f in page_files]

        if size_cm:
            w_cm, h_cm = size_cm
            target_w = int(w_cm / 2.54 * dpi)
            target_h = int(h_cm / 2.54 * dpi)
            print(f"\nPDF page size: {w_cm}cm × {h_cm}cm @ {dpi}dpi = {target_w}×{target_h}px")

            resized = []
            for img in images:
                # Fit image into target size, centered on white background
                img_w, img_h = img.size
                scale = min(target_w / img_w, target_h / img_h)
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                fitted = img.resize((new_w, new_h), Image.LANCZOS)
                page = Image.new('RGB', (target_w, target_h), 'white')
                page.paste(fitted, ((target_w - new_w) // 2, (target_h - new_h) // 2))
                resized.append(page)
            images = resized

        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        images[0].save(
            pdf_path, "PDF", resolution=dpi,
            save_all=True, append_images=images[1:]
        )
        print(f"📄 PDF saved: {pdf_path} ({len(images)} pages)")


def _parse_ratio(ratio_str: str):
    """Parse 'W:H' ratio string to float (height/width). Returns None on failure."""
    parts = ratio_str.split(":")
    if len(parts) != 2:
        return None
    try:
        w, h = int(parts[0]), int(parts[1])
        if w <= 0 or h <= 0:
            return None
        return h / w  # height/width
    except ValueError:
        return None


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Intelligently paginate long screenshots at natural breaks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s screenshot.png
  %(prog)s screenshot.png -o pages/ -p chapter1
  %(prog)s screenshot.png -t 5 -r 0.5625
        """
    )

    parser.add_argument(
        "input",
        help="Input screenshot file"
    )

    parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Output directory for pages (default: current directory)"
    )

    parser.add_argument(
        "-p", "--prefix",
        default="page",
        help="Prefix for output filenames (default: 'page')"
    )

    parser.add_argument(
        "-t", "--tolerance",
        type=int,
        default=5,
        help="Color variance tolerance for gap detection (default: 5)"
    )

    parser.add_argument(
        "-r", "--ratio",
        type=str,
        default="16:9",
        help="Target page aspect ratio as W:H (default: '16:9'). Examples: '9:16', '4:3', '1:1'"
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=20,
        help="Left and right padding in pixels (default: 20)"
    )

    parser.add_argument(
        "-s", "--split",
        choices=["horizontal", "vertical-ltr", "vertical-rtl"],
        default="horizontal",
        help="Split direction: 'horizontal' (top→bottom, default), "
             "'vertical-ltr' (left→right), "
             "'vertical-rtl' (right→left, for tategaki/manga)"
    )

    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Export as single PDF file (e.g., 'output.pdf')"
    )

    parser.add_argument(
        "--pdf-size",
        type=str,
        default=None,
        help="PDF page size in cm as 'WxH' (e.g., '21x29.7' for A4, '14.8x21' for A5)"
    )

    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=300,
        help="PDF resolution in DPI (default: 300)"
    )

    parser.add_argument(
        "-m", "--margins",
        type=str,
        default=None,
        help="Page margins as 'top,right,bottom,left' in pixels (e.g., '40,30,40,30'). "
             "Page size is fixed by ratio; content shrinks inward. Overrides --padding."
    )

    args = parser.parse_args()

    # Parse margins
    margins = None
    if args.margins:
        parts = args.margins.split(",")
        if len(parts) == 1:
            # Single value = all four sides
            v = int(parts[0])
            margins = (v, v, v, v)
        elif len(parts) == 2:
            # Two values = (vertical, horizontal)
            v, h = int(parts[0]), int(parts[1])
            margins = (v, h, v, h)
        elif len(parts) == 4:
            margins = tuple(int(x) for x in parts)
        else:
            print(f"Error: Invalid margins '{args.margins}'. Use 'all', 'v,h', or 'top,right,bottom,left'")
            return 1

    # Parse page ratio
    page_ratio = _parse_ratio(args.ratio)
    if page_ratio is None:
        print(f"Error: Invalid ratio '{args.ratio}'. Use format W:H (e.g., 16:9)")
        return 1

    # Create paginator
    paginator = ScreenshotPaginator(
        tolerance=args.tolerance,
        target_ratio=page_ratio
    )

    # Process
    try:
        # Parse PDF size
        pdf_size_cm = None
        if args.pdf_size:
            parts = args.pdf_size.lower().split("x")
            if len(parts) != 2:
                print(f"Error: Invalid PDF size '{args.pdf_size}'. Use WxH in cm (e.g., 21x29.7)")
                return 1
            try:
                pdf_size_cm = (float(parts[0]), float(parts[1]))
            except ValueError:
                print(f"Error: Invalid PDF size '{args.pdf_size}'. Use numbers (e.g., 21x29.7)")
                return 1

        output_files = paginator.paginate(
            args.input,
            args.output_dir,
            args.prefix,
            args.padding,
            margins=margins,
            direction=args.split,
            pdf_path=args.pdf,
            pdf_size_cm=pdf_size_cm,
            pdf_dpi=args.pdf_dpi
        )

        print(f"\nOutput files:")
        for f in output_files:
            print(f"  {f}")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
