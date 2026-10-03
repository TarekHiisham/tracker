import os
import hmac
import sqlite3
from datetime import datetime, timezone

from flask import Flask, request, abort, Response, send_from_directory

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "visits.db")
LOG_TOKEN = os.environ.get("LOG_TOKEN")          # secret to view /logs
EXAM_FILENAME = os.environ.get("DOCUMENT", "CV Resturant.pdf")  # file inside exams/
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


@app.route("/")
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