import os
import hmac
import sqlite3
from datetime import datetime, timezone

from flask import Flask, request, abort, Response, send_from_directory, render_template_string

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
        "ts TEXT NOT NULL, ip TEXT NOT NULL, user_agent TEXT, student TEXT)"
    )
    return conn


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
  body { font-family: system-ui, sans-serif; background:#f4f6fb; margin:0;
         height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background:#fff; border-radius:16px; padding:40px 48px; text-align:center;
          box-shadow:0 10px 30px rgba(0,0,0,.08); max-width:360px; }
  img { width:110px; }
  h1 { font-size:20px; margin:18px 0 6px; color:#222; }
  p { color:#666; font-size:13px; margin:0 0 20px; }
  a.btn { display:inline-block; background:#345abd; color:#fff; text-decoration:none;
          padding:12px 26px; border-radius:8px; font-weight:600; }
  a.btn:hover { background:#2a478f; }
  .note { margin-top:18px; font-size:11px; color:#999; }
</style>
</head>
<body>
  <div class="card">
    <img src="/static/exam-logo.png" alt="exam">
    <h1>{{ title }}</h1>
    <p>Click below to open your exam.</p>
    <a class="btn" href="/open{{ query }}">Open Exam</a>
    <div class="note">Opening the exam records the time and your IP address.</div>
  </div>
</body>
</html>"""


@app.route("/")
def index():
    # Optional: put a name in the link, e.g. yoursite.com/?student=John
    student = request.args.get("student", "")
    query = f"?student={student}" if student else ""
    return render_template_string(PAGE, title=EXAM_TITLE, query=query)


@app.route("/open")
def open_exam():
    now = datetime.now(timezone.utc)
    ip = client_ip()
    ua = request.headers.get("User-Agent", "")[:300]
    student = request.args.get("student", "")

    print(f"OPEN {now.isoformat()} {ip} student={student!r}", flush=True)

    try:
        conn = db()
        conn.execute(
            "INSERT INTO opens (ts, ip, user_agent, student) VALUES (?, ?, ?, ?)",
            (now.isoformat(), ip, ua, student),
        )
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
        "SELECT ts, ip, student, user_agent FROM opens ORDER BY id DESC"
    ).fetchall()
    conn.close()
    unique = len({r[1] for r in rows})
    lines = [f"Total opens: {len(rows)} | Unique IPs: {unique}", "-" * 70]
    lines += [f"{ts}  {ip:<16}  student={student or '-':<15}  {ua}"
              for ts, ip, student, ua in rows]
    return Response("\n".join(lines), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
