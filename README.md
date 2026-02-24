# Screenshot Paginator

Split long scrolling screenshots into uniform pages at natural content gaps.

Supports horizontal (top→bottom) and vertical (left→right or right→left) splits, four-margin mode, and PDF export.

## Install & Run

```bash
# CLI (uv auto-installs dependencies)
uv run --with Pillow --with numpy python3 paginate_screenshot.py input.png

# Web UI
uv run --with Pillow --with numpy python3 web.py
# → http://localhost:8899
```

## CLI Usage

```bash
# Basic: split into 9:16 pages
python3 paginate_screenshot.py screenshot.png -o pages/

# Custom page ratio
python3 paginate_screenshot.py screenshot.png -r 210:297   # A4

# Vertical split for tategaki / manga (right→left reading)
python3 paginate_screenshot.py wide.png -s vertical-rtl -r 9:16

# Vertical split, left→right
python3 paginate_screenshot.py wide.png -s vertical-ltr -r 9:16

# Four-margin mode (content shrinks inward, page size fixed by ratio)
python3 paginate_screenshot.py screenshot.png -m 40,30,40,30

# Export as PDF (page size in cm)
python3 paginate_screenshot.py screenshot.png --pdf out.pdf --pdf-size 21x29.7

# Combine options
python3 paginate_screenshot.py tategaki.png \
  -s vertical-rtl -r 210:297 -m 60,40,60,40 \
  --pdf output.pdf --pdf-size 21x29.7
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `input` | Input image path | required |
| `-o, --output-dir` | Output directory | `.` |
| `-p, --prefix` | Output filename prefix | `page` |
| `-r, --ratio` | Page aspect ratio as `W:H` | `9:16` |
| `-t, --tolerance` | Gap detection tolerance (0–255) | `5` |
| `-s, --split` | Direction: `horizontal`, `vertical-ltr`, `vertical-rtl` | `horizontal` |
| `-m, --margins` | Margins in px: `top,right,bottom,left` or `all` or `tb,lr` | none |
| `--padding` | Side padding in px (ignored with `-m`) | `20` |
| `--pdf` | Export as single PDF | none |
| `--pdf-size` | PDF page size in cm: `WxH` | none |
| `--pdf-dpi` | PDF resolution | `300` |

## Web UI

Dark-free, clean light interface at `localhost:8899`.

- Drag-and-drop upload
- Page ratio presets (16:9, 9:16, 4:3, A4)
- 3-direction toggle (↕ Top→Bottom, ↔ L→R, ↔ R→L)
- Optional margins with presets
- PDF export with size presets (A4, A5, A6, B5 JIS)
- ZIP / PDF download
- Clear button to reset

## How It Works

### 1. Gap Detection

Scans rows (horizontal) or columns (vertical) for pure-color lines within tolerance. Consecutive gap lines are grouped.

### 2. Greedy Page Filling

Like printing an article: fill each page as close to the target ratio as possible, then move to the next. The last page holds whatever remains — even if it's just one line.

- **Forward** (horizontal, vertical-ltr): Greedy from top/left. Picks the gap closest to the ideal cut position **from below** (maximizes fill without exceeding page size).
- **Reverse** (vertical-rtl): Greedy from right edge. Picks the gap closest to ideal **from above**. Remainder falls on the leftmost page (last in reading order).

No strip ever exceeds the ideal page extent. Page dimensions stay fixed — font size never changes.

### 3. Uniform Pages

All pages share identical dimensions. Content is centered on non-remainder pages. The remainder page aligns content to the reading-start edge:

| Direction | Remainder Page | Content Alignment |
|-----------|---------------|-------------------|
| Horizontal (top→bottom) | Last (bottom) | Top |
| Vertical LTR | Last (rightmost) | Left |
| Vertical RTL | Last (leftmost) | Right |

### 4. PDF Export

Images are fitted (Lanczos resize) and centered onto pages at the specified cm dimensions and DPI.

## Programmatic Usage

```python
from paginate_screenshot import ScreenshotPaginator

paginator = ScreenshotPaginator(tolerance=5, target_ratio=16/9)

# Basic
pages = paginator.paginate("input.png", output_dir="pages")

# With margins, RTL, PDF
pages = paginator.paginate(
    "tategaki.png",
    output_dir="pages",
    margins=(60, 40, 60, 40),
    direction="vertical-rtl",
    pdf_path="output.pdf",
    pdf_size_cm=(21.0, 29.7)
)
```

## Architecture

```
paginate_screenshot.py
├── GapDetector          — finds pure-color rows/columns, groups them
├── PageOptimizer        — greedy cut selection (forward or reverse)
└── ScreenshotPaginator  — orchestrates detection → optimization → extraction → PDF

web.py                   — stdlib HTTP server, multipart parser, dark-free UI
```

## License

MIT
