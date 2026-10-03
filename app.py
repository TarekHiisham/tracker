import os
import hmac
import sqlite3
import requests
from datetime import datetime, timezone
from collections import Counter

from flask import Flask, request, abort, Response, send_from_directory, render_template_string, jsonify

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "visits.db")
LOG_TOKEN = os.environ.get("LOG_TOKEN")          # secret to view /logs
EXAM_FILENAME = os.environ.get("EXAM_FILENAME", "exam.pdf")  # file inside exams/
EXAM_TITLE = os.environ.get("EXAM_TITLE", "Exam")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS opens ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts TEXT NOT NULL, ip TEXT NOT NULL, user_agent TEXT, student TEXT, "
        "country TEXT, region TEXT, "
        "gps_lat REAL, gps_lon REAL, gps_accuracy REAL, gps_status TEXT)"
    )
    return conn


def lookup_country(ip):
    """Country/region for an IP (not precise GPS) -- used as a fallback and
    for the aggregate country breakdown."""
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


PREVIEW_PATH = os.path.join("static", "preview.png")


def ensure_preview_image():
    """Render page 1 of the PDF to static/preview.png, once, for link previews
    (WhatsApp/Facebook/Twitter/etc show this when the link is shared)."""
    if os.path.exists(PREVIEW_PATH):
        return
    try:
        import pymupdf
        pdf_path = os.path.join("exams", EXAM_FILENAME)
        doc = pymupdf.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # ~144 DPI
        pix.save(PREVIEW_PATH)
        doc.close()
        print("Generated link-preview image from PDF page 1", flush=True)
    except Exception as e:
        print(f"Could not generate preview image: {e}", flush=True)


CONSENT_PAGE = """<!doctype html>
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
<style>
  body { font-family: system-ui, sans-serif; background:#f4f6fb; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px;
         box-sizing:border-box; }
  .card { background:#fff; border-radius:16px; padding:36px 40px; text-align:center;
          box-shadow:0 10px 30px rgba(0,0,0,.08); max-width:380px; }
  img.logo { width:90px; }
  img.preview { width:100%; max-width:280px; border-radius:8px; border:1px solid #e4e6ef;
                margin:14px 0 4px; box-shadow:0 4px 14px rgba(0,0,0,.06); }
  h1 { font-size:19px; margin:16px 0 8px; color:#222; }
  p { color:#555; font-size:13.5px; line-height:1.5; margin:0 0 18px; }
  button { background:#345abd; color:#fff; border:none; cursor:pointer;
           padding:12px 26px; border-radius:8px; font-weight:600; font-size:14px; width:100%; }
  button:hover { background:#2a478f; }
  button.secondary { background:none; color:#777; margin-top:10px; font-weight:500; text-decoration:underline; }
  .note { margin-top:16px; font-size:11px; color:#999; }
  #status { font-size:12.5px; color:#888; margin-top:12px; min-height:16px; }
</style>
</head>
<body>
  <div class="card">
    <img class="logo" src="/static/exam-logo.png" alt="">
    <h1>{{ title }}</h1>
    <img class="preview" src="{{ preview_url }}" alt="Preview of page 1">
    <p>This is a short survey about regional preferences in Europe.
       To help with the regional analysis, we'd like your approximate location.
       Your browser will ask you to confirm before anything is shared.</p>
    <button id="allow">Allow location &amp; continue</button>
    <button id="skip" class="secondary">Continue without location</button>
    <div id="status"></div>
    <div class="note">Your IP address is recorded for all visitors regardless of this choice.</div>
  </div>

<script>
const visitId = "{{ visit_id }}";

function goNext() {
  window.location.href = "/open?vid=" + encodeURIComponent(visitId) + "&student={{ student }}";
}

document.getElementById("skip").addEventListener("click", goNext);

document.getElementById("allow").addEventListener("click", function () {
  const statusEl = document.getElementById("status");
  if (!("geolocation" in navigator)) {
    statusEl.textContent = "Location isn't available in this browser.";
    setTimeout(goNext, 600);
    return;
  }
  statusEl.textContent = "Requesting permission…";
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      statusEl.textContent = "Thanks! Continuing…";
      fetch("/record-location", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visit_id: visitId,
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      }).finally(goNext);
    },
    function (err) {
      statusEl.textContent = "Permission not granted, continuing…";
      setTimeout(goNext, 600);
    },
    { timeout: 8000 }
  );
});
</script>
</body>
</html>"""


EXAM_DESCRIPTION = os.environ.get(
    "EXAM_DESCRIPTION",
    "Open to view the document. A preview of the first page is shown below."
)


@app.route("/")
def consent_page():
    now = datetime.now(timezone.utc)
    ip = client_ip()
    ua = request.headers.get("User-Agent", "")[:300]
    student = request.args.get("student", "")
    country, region = lookup_country(ip)

    conn = db()
    cur = conn.execute(
        "INSERT INTO opens (ts, ip, user_agent, student, country, region, gps_status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (now.isoformat(), ip, ua, student, country, region),
    )
    visit_id = cur.lastrowid
    conn.commit()
    conn.close()

    ensure_preview_image()
    preview_url = request.host_url.rstrip("/") + "/static/preview.png"

    return render_template_string(
        CONSENT_PAGE, title=EXAM_TITLE, description=EXAM_DESCRIPTION,
        preview_url=preview_url, visit_id=visit_id, student=student,
    )


@app.route("/record-location", methods=["POST"])
def record_location():
    data = request.get_json(silent=True) or {}
    visit_id = data.get("visit_id")
    lat = data.get("lat")
    lon = data.get("lon")
    accuracy = data.get("accuracy")
    if not visit_id:
        return jsonify(ok=False), 400
    try:
        conn = db()
        conn.execute(
            "UPDATE opens SET gps_lat=?, gps_lon=?, gps_accuracy=?, gps_status='granted' WHERE id=?",
            (lat, lon, accuracy, visit_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"DB error: {e}", flush=True)
        return jsonify(ok=False), 500
    return jsonify(ok=True)


@app.route("/open")
def open_exam():
    visit_id = request.args.get("vid")
    if visit_id:
        try:
            conn = db()
            row = conn.execute("SELECT gps_status FROM opens WHERE id=?", (visit_id,)).fetchone()
            if row and row[0] == "pending":
                conn.execute("UPDATE opens SET gps_status='denied' WHERE id=?", (visit_id,))
                conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"DB error: {e}", flush=True)

    return send_from_directory("exams", EXAM_FILENAME, as_attachment=False,
                                download_name=EXAM_FILENAME)


@app.route("/logs")
def logs():
    token = request.args.get("token", "")
    if not LOG_TOKEN or not hmac.compare_digest(token, LOG_TOKEN):
        abort(404)
    conn = db()
    rows = conn.execute(
        "SELECT ts, ip, student, user_agent, country, region, gps_lat, gps_lon, gps_accuracy, gps_status "
        "FROM opens ORDER BY id DESC"
    ).fetchall()
    conn.close()
    unique = len({r[1] for r in rows})

    counts = Counter(r[4] or "Unknown" for r in rows)
    breakdown = [f"  {c}: {n} ({n/len(rows)*100:.1f}%)" for c, n in counts.most_common()] if rows else []
    granted = sum(1 for r in rows if r[9] == "granted")

    lines = [f"Total opens: {len(rows)} | Unique IPs: {unique} | Location granted: {granted}", ""]
    lines.append("By country (IP-based):")
    lines += breakdown if breakdown else ["  (no data yet)"]
    lines += ["", "-" * 110]
    for ts, ip, student, ua, country, region, lat, lon, acc, status in rows:
        gps = f"{lat:.5f},{lon:.5f} (±{acc:.0f}m)" if status == "granted" and lat is not None else f"[{status}]"
        lines.append(f"{ts}  {ip:<16}  {country or '-':<14} {region or '-':<14} GPS={gps:<28} student={student or '-'}")
    return Response("\n".join(lines), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
