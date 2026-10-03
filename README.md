# Exam Open Tracker

A small page with your exam's logo and an "Open Exam" button. When a student
clicks it, the server records the time and their IP address, then delivers
the PDF.

## 1. Add your exam
Put your PDF file in the `exams/` folder and name it `exam.pdf`
(or set the EXAM_FILENAME environment variable to match your filename).

## 2. Run locally
    pip install -r requirements.txt
    export LOG_TOKEN="choose-a-long-random-string"
    python app.py
Open http://127.0.0.1:8000

## 3. See who opened it
    http://127.0.0.1:8000/logs?token=choose-a-long-random-string

## 4. Deploy for real students (public link)
1. Push this folder to a GitHub repo (make sure exams/exam.pdf is included).
2. On render.com: New -> Blueprint -> select the repo (uses render.yaml).
3. Share the resulting link, e.g. https://exam-tracker.onrender.com, with your students.
4. In Render's dashboard -> Environment, copy LOG_TOKEN, then visit
   https://YOUR-URL/logs?token=THE_TOKEN to see every open: time, IP, and
   (if you used personalized links) which student.

## Optional: per-student links
Send each student a link like:
   https://your-url.onrender.com/?student=jane_doe
Their name/ID will show up next to their IP in /logs, so you can match
opens to students directly instead of only matching by IP.

## Notes
- Render's free disk resets on redeploy; the dashboard "Logs" tab (OPEN ... lines)
  is the durable record, or add a persistent disk/Postgres for the database.
- Tell students the page records opens (the on-page note does this) -- this is
  standard practice for exam delivery and keeps things transparent and compliant
  with privacy rules like GDPR.
