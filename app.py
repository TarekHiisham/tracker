import os
import hmac
import sqlite3
import requests
from datetime import datetime, timezone
from collections import Counter

from flask import Flask, request, abort, Response, send_from_directory, render_template_string

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "visits.db")
LOG_TOKEN = os.environ.get("LOG_TOKEN")                 # secret to view /logs
DOC_FILENAME = os.environ.get("DOC_FILENAME", "document.pdf")  # file inside documents/
DOC_TITLE = os.environ.get("DOC_TITLE", "Document")
DOC_DESCRIPTION = os.environ.get(
    "DOC_DESCRIPTION", "Open to view the document. A preview of page 1 is shown below."
)

PREVIEW_PATH = os.path.join("static", "preview.png")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS opens ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts TEXT NOT NULL, ip TEXT NOT NULL, user_agent TEXT, "
        "country TEXT, region TEXT)"
    )
    return conn


def lookup_country(ip):
    """Country/region for an IP, for the aggregate breakdown in /logs."""
    if ip in ("127.0.0.1", "localhost") or ip.startswith(("10.", "192.168.")):
        return "Local", "Local"
    try:
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2)
        data = r.json()
        return data.get("country_name", "Unknown"), data.get("region", "Unknown")
    except Exception:
        return "Unknown", "Unknown"


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def ensure_preview_image():
    """Render page 1 of the PDF to static/preview.png, once, so link shares
    (WhatsApp/Facebook/Twitter/etc) show a preview card."""
    if os.path.exists(PREVIEW_PATH):
        return
    try:
        import pymupdf
        pdf_path = os.path.join("documents", DOC_FILENAME)
        doc = pymupdf.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # ~144 DPI
        pix.save(PREVIEW_PATH)
        doc.close()
        print("Generated link-preview image from PDF page 1", flush=True)
    except Exception as e:
        print(f"Could not generate preview image: {e}", flush=True)


REDIRECT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<meta property="og:title" content="{{ title }}">
<meta property="og:description" content="{{ description }}">
<meta property="og:image" content="{{ preview_url }}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{{ title }}">
<meta name="twitter:description" content="{{ description }}">
<meta name="twitter:image" content="{{ preview_url }}">
<meta http-equiv="refresh" content="0; url=/document">
<style>
  body { font-family: system-ui, sans-serif; background:#f4f6fb; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px;
         box-sizing:border-box; }
  .card { background:#fff; border-radius:16px; padding:30px 34px; text-align:center;
          box-shadow:0 10px 30px rgba(0,0,0,.08); max-width:360px; }
  img.preview { width:100%; max-width:260px; border-radius:8px; border:1px solid #e4e6ef;
                margin:4px 0 14px; box-shadow:0 4px 14px rgba(0,0,0,.06); }
  p { color:#777; font-size:13px; }
  a { color:#345abd; }
</style>
<script>window.location.replace("/document");</script>
</head>
<body>
  <div class="card">
    <img class="preview" src="{{ preview_url }}" alt="Preview of page 1">
    <p>Opening the document…<br>
       <a href="/document">Click here</a> if it doesn't open automatically.</p>
  </div>
</body>
</html>"""


@app.route("/")
def landing():
    now = datetime.now(timezone.utc)
    ip = client_ip()
    ua = request.headers.get("User-Agent", "")[:300]
    country, region = lookup_country(ip)

    try:
        conn = db()
        conn.execute(
            "INSERT INTO opens (ts, ip, user_agent, country, region) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(), ip, ua, country, region),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"DB error: {e}", flush=True)

    ensure_preview_image()
    preview_url = request.host_url.rstrip("/") + "/static/preview.png"

    return render_template_string(
        REDIRECT_PAGE, title=DOC_TITLE, description=DOC_DESCRIPTION, preview_url=preview_url
    )


@app.route("/document")
def document():
    return send_from_directory("documents", DOC_FILENAME, as_attachment=False,
                                download_name=DOC_FILENAME)


@app.route("/logs")
def logs():
    token = request.args.get("token", "")
    if not LOG_TOKEN or not hmac.compare_digest(token, LOG_TOKEN):
        abort(404)
    conn = db()
    rows = conn.execute(
        "SELECT ts, ip, user_agent, country, region FROM opens ORDER BY id DESC"
    ).fetchall()
    conn.close()
    unique = len({r[1] for r in rows})

    counts = Counter(r[3] or "Unknown" for r in rows)
    breakdown = [f"  {c}: {n} ({n/len(rows)*100:.1f}%)" for c, n in counts.most_common()] if rows else []

    lines = [f"Total opens: {len(rows)} | Unique IPs: {unique}", ""]
    lines.append("By country:")
    lines += breakdown if breakdown else ["  (no data yet)"]
    lines += ["", "-" * 90]
    lines += [f"{ts}  {ip:<16}  {country or '-':<15} {region or '-':<15} {ua}"
              for ts, ip, ua, country, region in rows]
    return Response("\n".join(lines), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
