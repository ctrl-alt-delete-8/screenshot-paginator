#!/usr/bin/env python3
"""Web UI for Screenshot Paginator. Pure stdlib — no Flask."""

import http.server
import json
import os
import re
import shutil
import tempfile
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image
from paginate_screenshot import ScreenshotPaginator

PORT = 8899
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="paginator-"))

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screenshot Paginator</title>
<style>
  :root {
    --bg: #fafafa; --surface: #fff; --border: #e2e2e2;
    --text: #1a1a1a; --text2: #666; --text3: #999;
    --accent: #2563eb; --accent-light: #eff6ff;
    --radius: 10px; --shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; -webkit-font-smoothing: antialiased; }

  .container { max-width: 960px; margin: 0 auto; padding: 2.5rem 1.5rem; }

  header { margin-bottom: 2rem; }
  header h1 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.01em; }
  header p { color: var(--text3); font-size: 0.8rem; margin-top: 0.25rem; }

  .layout { display: grid; grid-template-columns: 340px 1fr; gap: 1.5rem; align-items: start; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem; box-shadow: var(--shadow); }

  /* Sidebar */
  .sidebar .section { margin-bottom: 1.25rem; padding-bottom: 1.25rem; border-bottom: 1px solid #f0f0f0; }
  .sidebar .section:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
  .section-title { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text3); margin-bottom: 0.75rem; }

  /* Drop zone */
  .drop-zone { border: 1.5px dashed var(--border); border-radius: 8px; padding: 2rem 1rem; text-align: center; cursor: pointer; transition: all 0.15s; }
  .drop-zone:hover, .drop-zone.dragover { border-color: var(--accent); background: var(--accent-light); }
  .drop-zone.has-file { border-style: solid; border-color: var(--border); padding: 0.75rem 1rem; background: var(--accent-light); }
  .drop-zone p { color: var(--text3); font-size: 0.8rem; }
  .drop-zone .filename { color: var(--accent); font-weight: 500; font-size: 0.85rem; }
  .drop-zone .fileinfo { color: var(--text3); font-size: 0.7rem; margin-top: 0.2rem; }

  /* Form elements */
  label { display: block; font-size: 0.75rem; font-weight: 500; color: var(--text2); margin-bottom: 0.3rem; }
  input[type=number] { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 0.4rem 0.6rem; border-radius: 6px; font-size: 0.85rem; width: 100%; }
  input[type=number]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-light); }

  .row { display: flex; align-items: center; gap: 0.4rem; }
  .row input { width: 4rem; text-align: center; }
  .row span { color: var(--text3); font-weight: 500; font-size: 0.85rem; }

  .tags { display: flex; gap: 0.3rem; flex-wrap: wrap; margin-top: 0.4rem; }
  .tag { background: var(--bg); border: 1px solid var(--border); color: var(--text2); padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; cursor: pointer; transition: all 0.1s; user-select: none; }
  .tag:hover { border-color: var(--accent); color: var(--accent); }

  /* Segmented control */
  .seg { display: flex; background: var(--bg); border-radius: 8px; padding: 2px; gap: 2px; }
  .seg-btn { flex: 1; padding: 0.35rem 0.3rem; text-align: center; font-size: 0.7rem; font-weight: 500; color: var(--text2); cursor: pointer; border-radius: 6px; transition: all 0.15s; border: none; background: none; user-select: none; white-space: nowrap; }
  .seg-btn.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,0.08); }

  /* Toggle */
  .toggle-row { display: flex; align-items: center; gap: 0.5rem; }
  .toggle-row label { margin: 0; font-size: 0.8rem; color: var(--text); font-weight: 400; }
  input[type=checkbox] { accent-color: var(--accent); }
  .sub-options { padding-left: 0.25rem; margin-top: 0.5rem; }

  /* Buttons */
  .actions { display: flex; gap: 0.5rem; margin-top: 1.25rem; flex-wrap: wrap; }
  .btn { padding: 0.5rem 1.25rem; border-radius: 8px; font-size: 0.8rem; font-weight: 600; cursor: pointer; border: none; transition: all 0.1s; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { filter: brightness(1.08); }
  .btn-primary:disabled { opacity: 0.35; cursor: not-allowed; }
  .btn-outline { background: none; border: 1px solid var(--border); color: var(--text2); }
  .btn-outline:hover { border-color: #bbb; color: var(--text); }

  /* Progress */
  .progress { display: none; margin-bottom: 0.75rem; }
  .progress.active { display: block; }
  .progress-bar { height: 2px; background: #eee; border-radius: 2px; overflow: hidden; }
  .progress-fill { height: 100%; background: var(--accent); width: 0%; transition: width 0.3s; }
  .progress-text { font-size: 0.7rem; color: var(--text3); margin-top: 0.3rem; }

  /* Result grid */
  .result-area { min-height: 300px; display: flex; align-items: center; justify-content: center; }
  .result-area.empty::after { content: 'Results will appear here'; color: #ccc; font-size: 0.85rem; }
  .pages-grid { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; width: 100%; }
  .page-card { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; max-width: 240px; background: var(--surface); box-shadow: var(--shadow); }
  .page-card img { width: 100%; display: block; }
  .page-card .meta { padding: 0.3rem 0.5rem; font-size: 0.65rem; color: var(--text3); text-align: center; border-top: 1px solid #f0f0f0; }

  @media (max-width: 720px) {
    .layout { grid-template-columns: 1fr; }
    .container { padding: 1rem; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Screenshot Paginator</h1>
    <p>Split long screenshots into uniform pages at natural gaps</p>
  </header>

  <div class="layout">
    <!-- Sidebar -->
    <div class="sidebar card">

      <!-- Upload -->
      <div class="section">
        <div class="section-title">Image</div>
        <input type="file" id="fileInput" accept="image/*" hidden>
        <div class="drop-zone" id="dropZone">
          <p>Drop image or click to upload</p>
        </div>
      </div>

      <!-- Page ratio -->
      <div class="section">
        <div class="section-title">Page Ratio</div>
        <label>Width : Height</label>
        <div class="row">
          <input type="number" id="ratioW" value="9" min="1" max="999">
          <span>:</span>
          <input type="number" id="ratioH" value="16" min="1" max="999">
        </div>
        <div class="tags" id="ratioTags">
          <span class="tag" data-w="16" data-h="9">16:9</span>
          <span class="tag" data-w="9" data-h="16">9:16</span>
          <span class="tag" data-w="4" data-h="3">4:3</span>
          <span class="tag" data-w="3" data-h="4">3:4</span>
          <span class="tag" data-w="210" data-h="297">A4</span>
        </div>
      </div>

      <!-- Split direction -->
      <div class="section">
        <div class="section-title">Split Direction</div>
        <div class="seg" id="dirSeg">
          <div class="seg-btn active" data-dir="horizontal">↕ Top→Bottom</div>
          <div class="seg-btn" data-dir="vertical-ltr">↔ L→R</div>
          <div class="seg-btn" data-dir="vertical-rtl">↔ R→L</div>
        </div>
      </div>

      <!-- Margins -->
      <div class="section">
        <div class="section-title">Spacing</div>
        <div class="toggle-row">
          <input type="checkbox" id="enableMargins">
          <label for="enableMargins">Four-margin mode</label>
        </div>
        <div id="marginControls" style="display:none" class="sub-options">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;">
            <div><label>Top</label><input type="number" id="mTop" value="40" min="0"></div>
            <div><label>Bottom</label><input type="number" id="mBottom" value="40" min="0"></div>
            <div><label>Left</label><input type="number" id="mLeft" value="30" min="0"></div>
            <div><label>Right</label><input type="number" id="mRight" value="30" min="0"></div>
          </div>
          <div class="tags" id="marginTags" style="margin-top:0.4rem">
            <span class="tag" data-t="20" data-r="20" data-b="20" data-l="20">20 all</span>
            <span class="tag" data-t="40" data-r="30" data-b="40" data-l="30">40/30</span>
            <span class="tag" data-t="60" data-r="40" data-b="60" data-l="40">60/40</span>
          </div>
        </div>
        <div id="paddingControl" class="sub-options" style="margin-top:0.5rem">
          <label>Padding (px)</label>
          <input type="number" id="padding" value="20" min="0" max="200" style="width:5rem">
        </div>
        <div style="margin-top:0.5rem">
          <label>Gap Tolerance</label>
          <input type="number" id="tolerance" value="5" min="0" max="50" style="width:5rem">
        </div>
      </div>

      <!-- PDF -->
      <div class="section">
        <div class="section-title">PDF Export</div>
        <div class="toggle-row">
          <input type="checkbox" id="enablePdf">
          <label for="enablePdf">Export as PDF</label>
        </div>
        <div id="pdfControls" style="display:none" class="sub-options">
          <label>Page size (cm)</label>
          <div class="row">
            <input type="number" id="pdfW" value="21" step="0.1" min="1">
            <span>×</span>
            <input type="number" id="pdfH" value="29.7" step="0.1" min="1">
            <span style="font-size:0.7rem;color:var(--text3)">cm</span>
          </div>
          <div class="tags" id="pdfTags" style="margin-top:0.4rem">
            <span class="tag" data-w="21" data-h="29.7">A4</span>
            <span class="tag" data-w="14.8" data-h="21">A5</span>
            <span class="tag" data-w="10.5" data-h="14.8">A6</span>
            <span class="tag" data-w="18.2" data-h="25.7">B5</span>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="btn btn-primary" id="processBtn" disabled>Process</button>
        <button class="btn btn-outline" id="clearBtn">Clear</button>
        <button class="btn btn-outline" id="downloadBtn" style="display:none">ZIP</button>
        <button class="btn btn-outline" id="pdfBtn" style="display:none">PDF</button>
      </div>
    </div>

    <!-- Main area -->
    <div>
      <div id="progress" class="progress">
        <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
        <div class="progress-text" id="progressText">Processing...</div>
      </div>
      <div class="card">
        <div class="result-area empty" id="resultArea"></div>
      </div>
    </div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
let uploadedFile = null, sessionId = null;
const dropZone = $('#dropZone'), fileInput = $('#fileInput');

// Upload
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFile(e.dataTransfer.files[0]); });
fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

function handleFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  uploadedFile = file;
  dropZone.classList.add('has-file');
  dropZone.innerHTML = '<p class="filename">' + file.name + '</p><p class="fileinfo">' + (file.size/1024/1024).toFixed(1) + ' MB</p>';
  $('#processBtn').disabled = false;
}

// Direction toggle
$('#dirSeg').addEventListener('click', e => {
  const btn = e.target.closest('.seg-btn');
  if (!btn) return;
  $('#dirSeg').querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
});

// Ratio presets
$('#ratioTags').addEventListener('click', e => {
  if (e.target.classList.contains('tag')) { $('#ratioW').value = e.target.dataset.w; $('#ratioH').value = e.target.dataset.h; }
});

// Margin toggle & presets
$('#enableMargins').addEventListener('change', e => {
  $('#marginControls').style.display = e.target.checked ? 'block' : 'none';
  $('#paddingControl').style.display = e.target.checked ? 'none' : 'block';
});
$('#marginTags').addEventListener('click', e => {
  if (e.target.classList.contains('tag')) {
    $('#mTop').value = e.target.dataset.t; $('#mRight').value = e.target.dataset.r;
    $('#mBottom').value = e.target.dataset.b; $('#mLeft').value = e.target.dataset.l;
  }
});

// PDF toggle & presets
$('#enablePdf').addEventListener('change', e => { $('#pdfControls').style.display = e.target.checked ? 'block' : 'none'; });
$('#pdfTags').addEventListener('click', e => {
  if (e.target.classList.contains('tag')) { $('#pdfW').value = e.target.dataset.w; $('#pdfH').value = e.target.dataset.h; }
});

// Clear
$('#clearBtn').addEventListener('click', () => {
  uploadedFile = null; sessionId = null;
  fileInput.value = '';
  dropZone.classList.remove('has-file');
  dropZone.innerHTML = '<p>Drop image or click to upload</p>';
  $('#processBtn').disabled = true;
  $('#downloadBtn').style.display = 'none';
  $('#pdfBtn').style.display = 'none';
  const ra = $('#resultArea');
  ra.innerHTML = ''; ra.classList.add('empty');
  $('#progress').classList.remove('active');
});

// Process
$('#processBtn').addEventListener('click', async () => {
  if (!uploadedFile) return;
  const prog = $('#progress'), fill = $('#progressFill'), ptxt = $('#progressText');
  prog.classList.add('active');
  fill.style.width = '30%'; ptxt.textContent = 'Uploading...';

  const fd = new FormData();
  fd.append('file', uploadedFile);
  fd.append('ratio_w', $('#ratioW').value);
  fd.append('ratio_h', $('#ratioH').value);
  fd.append('tolerance', $('#tolerance').value);
  fd.append('padding', $('#padding').value);
  fd.append('direction', $('#dirSeg').querySelector('.seg-btn.active').dataset.dir);

  if ($('#enableMargins').checked) {
    fd.append('m_top', $('#mTop').value); fd.append('m_right', $('#mRight').value);
    fd.append('m_bottom', $('#mBottom').value); fd.append('m_left', $('#mLeft').value);
  }
  if ($('#enablePdf').checked) {
    fd.append('pdf', '1');
    fd.append('pdf_w', $('#pdfW').value);
    fd.append('pdf_h', $('#pdfH').value);
  }

  fill.style.width = '60%'; ptxt.textContent = 'Processing...';

  try {
    const res = await fetch('/process', { method: 'POST', body: fd });
    const data = await res.json();
    fill.style.width = '100%';

    if (data.error) { ptxt.textContent = 'Error: ' + data.error; return; }

    sessionId = data.session_id;
    const ra = $('#resultArea');
    ra.classList.remove('empty');
    let html = '<div class="pages-grid">';
    data.pages.forEach((p, i) => {
      html += '<div class="page-card"><img src="/page/' + sessionId + '/' + i + '" loading="lazy"><div class="meta">' + p.width + '×' + p.height + '</div></div>';
    });
    html += '</div>';
    ra.innerHTML = html;

    $('#downloadBtn').style.display = 'inline-block';
    if (data.has_pdf) $('#pdfBtn').style.display = 'inline-block';
    ptxt.textContent = data.pages.length + ' pages';
  } catch (err) {
    ptxt.textContent = 'Error: ' + err.message;
  }
});

// Downloads
$('#downloadBtn').addEventListener('click', () => { if (sessionId) location = '/download/' + sessionId; });
$('#pdfBtn').addEventListener('click', () => { if (sessionId) location = '/pdf/' + sessionId; });
</script>
</body>
</html>"""


class PaginatorHandler(http.server.BaseHTTPRequestHandler):
    sessions = {}

    def log_message(self, format, *args):
        pass  # Silence request logs

    def do_GET(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._send_html(HTML_PAGE)

        elif parsed.path.startswith("/page/"):
            parts = parsed.path.split("/")
            if len(parts) >= 4:
                sid, idx = parts[2], int(parts[3])
                session = self.sessions.get(sid)
                if session and 0 <= idx < len(session["pages"]):
                    self._send_file(session["pages"][idx], "image/png")
                    return
            self._send_error(404, "Page not found")

        elif parsed.path.startswith("/pdf/"):
            sid = parsed.path.split("/")[-1]
            session = self.sessions.get(sid)
            if session and session.get("pdf") and os.path.exists(session["pdf"]):
                self._send_file(session["pdf"], "application/pdf",
                               headers={"Content-Disposition": "attachment; filename=pages.pdf"})
            else:
                self._send_error(404, "PDF not found")

        elif parsed.path.startswith("/download/"):
            sid = parsed.path.split("/")[-1]
            session = self.sessions.get(sid)
            if session:
                self._send_zip(session)
            else:
                self._send_error(404, "Session not found")
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        if self.path != "/process":
            self._send_error(404, "Not found")
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "Expected multipart/form-data"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        fields, file_data = self._parse_multipart(content_type, body)

        if not file_data:
            self._send_json({"error": "No file uploaded"})
            return

        ratio_w = int(fields.get("ratio_w", "9"))
        ratio_h = int(fields.get("ratio_h", "16"))
        ratio = ratio_h / ratio_w
        tolerance = int(fields.get("tolerance", "5"))
        padding = int(fields.get("padding", "20"))
        direction = fields.get("direction", "horizontal")
        want_pdf = fields.get("pdf") == "1"
        pdf_w = fields.get("pdf_w")
        pdf_h = fields.get("pdf_h")

        m_top = fields.get("m_top")
        margins = None
        if m_top is not None:
            margins = (int(m_top), int(fields.get("m_right", 0)),
                       int(fields.get("m_bottom", 0)), int(fields.get("m_left", 0)))

        sid = uuid.uuid4().hex[:12]
        session_dir = UPLOAD_DIR / sid
        session_dir.mkdir(parents=True)
        input_path = session_dir / "input.png"

        with open(input_path, "wb") as f:
            f.write(file_data)

        try:
            paginator = ScreenshotPaginator(tolerance=tolerance, target_ratio=ratio)
            output_dir = str(session_dir / "pages")
            pdf_path = str(session_dir / "output.pdf") if want_pdf else None
            pdf_size_cm = (float(pdf_w), float(pdf_h)) if want_pdf and pdf_w and pdf_h else None

            output_files = paginator.paginate(
                str(input_path), output_dir, "page", padding,
                margins=margins, direction=direction,
                pdf_path=pdf_path, pdf_size_cm=pdf_size_cm
            )

            pages_info = []
            for f_path in output_files:
                img = Image.open(f_path)
                pages_info.append({"width": img.size[0], "height": img.size[1]})

            self.sessions[sid] = {"pages": output_files, "dir": session_dir, "pdf": pdf_path}
            self._send_json({"session_id": sid, "pages": pages_info, "has_pdf": pdf_path is not None})

        except Exception as e:
            self._send_json({"error": str(e)})

    # --- Helpers ---

    def _send_html(self, html):
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, filepath, content_type, headers=None):
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(data))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_zip(self, session):
        import zipfile
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page_path in enumerate(session["pages"]):
                zf.write(page_path, f"page_{i+1:03d}.png")
        data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", "attachment; filename=pages.zip")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _parse_multipart(content_type, body):
        match = re.search(r'boundary=([^\s;]+)', content_type)
        if not match:
            return {}, None
        boundary = match.group(1).encode()
        fields = {}
        file_data = None
        for part in body.split(b"--" + boundary):
            if not part or part.strip() in (b"", b"--", b"--\r\n"):
                continue
            if b"\r\n\r\n" not in part:
                continue
            header_data, part_body = part.split(b"\r\n\r\n", 1)
            if part_body.endswith(b"\r\n"):
                part_body = part_body[:-2]
            header_str = header_data.decode("utf-8", errors="replace")
            name_match = re.search(r'name="([^"]+)"', header_str)
            if not name_match:
                continue
            if re.search(r'filename="', header_str):
                file_data = part_body
            else:
                fields[name_match.group(1)] = part_body.decode("utf-8", errors="replace")
        return fields, file_data

    def _send_error(self, code, msg):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode())


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), PaginatorHandler)
    print(f"Screenshot Paginator → http://localhost:{PORT}")
    print(f"Temp: {UPLOAD_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
