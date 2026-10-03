# Document Open Tracker

A link that shows a preview card when shared, then opens your PDF
automatically. Every open is logged with IP address and approximate
country/region.

## 1. Add your PDF
Put your file in the `documents/` folder and name it `document.pdf`
(or set the DOC_FILENAME environment variable to match your filename).

## 2. Run locally
    pip install -r requirements.txt
    export LOG_TOKEN="choose-a-long-random-string"
    python app.py
Open http://127.0.0.1:8000 -- it redirects straight to the PDF.

## 3. See who opened it
    http://127.0.0.1:8000/logs?token=choose-a-long-random-string

## 4. Deploy for a public link
1. Push this folder to a GitHub repo (make sure documents/document.pdf is included).
2. On render.com: New -> Blueprint -> select the repo (uses render.yaml).
3. Share the resulting link, e.g. https://document-tracker.onrender.com
4. In Render's dashboard -> Environment, copy LOG_TOKEN, then visit
   https://YOUR-URL/logs?token=THE_TOKEN to see every open: time, IP, country.

## Link preview
The root page automatically renders page 1 of your PDF to an image
(static/preview.png, generated once) and sets it as the Open Graph /
Twitter Card image, so apps like WhatsApp and Facebook show a preview
of your document when the link is shared. Visitors are redirected to
the PDF itself immediately (no click needed).

## Notes
- Render's free disk resets on redeploy; for a durable log, add a
  persistent disk or Postgres.
- The page records visitor IPs -- let recipients know if that matters
  for your use case.
