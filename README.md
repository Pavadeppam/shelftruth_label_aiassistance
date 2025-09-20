# ShelfTruth - Multi-Agent AI Orchestration System

ShelfTruth automates the SKU compliance lifecycle: it ingests supplier data and PDFs, extracts claims via text/OCR, verifies claims with rules/ML, creates tasks for human review, and provides dashboards and auditability.

---

## Prerequisites

- Python 3.11 recommended (many scientific packages provide wheels for 3.11)
- A virtual environment (venv)

## Setup

```bash
# 1) Create and activate a Python 3.11 virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# 2) Install dependencies (pure pip OCR stack, no OS installs required)
pip install -r requirements.txt
```

OCR/Text dependencies installed by requirements:

- `pdfminer.six` – fast text extraction for text-based PDFs
- `PyMuPDF` (`fitz`) – render PDFs to images in-memory
- `EasyOCR` – OCR for scanned/image PDFs

Note: We intentionally removed `pytesseract` and `pdf2image` to avoid OS-level installs.

## Run

```bash
# Optional: choose a port (defaults to 5000)
export PORT=5001

python app.py

PORT=5001 .venv/bin/python app.py
```

Open the app:

- Dashboard: `http://localhost:<PORT>` (e.g., `http://localhost:5001`)
- Retail Assistant: `http://localhost:<PORT>/retail-assistant`
- Compliance Report: `http://localhost:<PORT>/compliance-report`
- Audit Trail: `http://localhost:<PORT>/audit-trail`

---

## Python Libraries and Their Purpose

- **flask** – Web server and routing for pages and REST APIs (`app.py`).
- **flask-cors** – Enables CORS for API endpoints during local development.
- **jinja2** – Server-side HTML templating used by files under `templates/`.
- **werkzeug** – Utilities used by Flask under the hood (HTTP, WSGI helpers).
- **requests** – Outbound HTTP if/when agents need to call external services.
- **python-dotenv** – Loads environment variables (e.g., `PORT`) from `.env` if present.
- **Pillow (PIL)** – Image handling when converting rendered PDF pages to images for OCR.
- **pdfminer.six** – Extracts text directly from text-based PDFs in Claim Extraction Agent.
- **PyMuPDF (fitz)** – Renders PDF pages to images when a PDF is image-only/scanned.
- **easyocr** – Performs OCR on rendered images to get label text.
- **numpy** – Array ops used when handling images and general utilities.
- **pandas** – Tabular data handling (e.g., intermediate processing, summaries if needed).
- **scikit-learn** – ML components (TF-IDF, Logistic Regression) for claim classification.

Database and local persistence:

- **sqlite3 (built-in)** – Python standard library module used in `database/schema.py` to store SKUs, claims, decisions, tasks, audit logs, and certificate validations.

Note on exclusions:

- We do not use `pytesseract`/`pdf2image` to avoid OS-level dependencies (Tesseract/Poppler).

## Quick Start Flow

1. Open the Dashboard. The “Pre-loaded Files” card shows:
   - `input/supplier_skus.json`
   - `input/sku_labels/*.pdf`
   - `input/sku_certificates/*.pdf` (also tolerant to `sku_cerificates/` typo)
2. Click “Upload & Process” or “Trigger Pipeline”. This runs:
   - Intake → Integration → Claim Extraction → Verification → Task creation
3. Open Retail Assistant to approve/reject or request evidence.
4. Review audit events on Audit Trail and metrics on Dashboard.

---

## UI Pages

- `templates/dashboard.html` – KPIs, charts, SKU status, pre-loaded files card
- `templates/retail_assistant.html` – task list and actions (approve/reject/request_evidence/modify)
- `templates/audit_trail.html` – recent audit events with filters
- `templates/compliance_report.html` – report generation view

---

## REST API (selected)

- `POST /api/trigger-pipeline` – run full pipeline on current inputs
- `GET  /api/dashboard` – aggregated dashboard data
- `GET  /api/tasks` – retail assistant open tasks
- `POST /api/tasks/<id>/decision` – act on a task
- `POST /api/tasks/bulk-approve` – bulk approval
- `GET  /api/statistics` – task/verification stats
- `GET  /api/audit-log?limit=N` – recent audit events
- `GET  /api/skus` – list SKUs
- `GET  /api/skus/<id>/claims` – claims for a SKU
- `GET  /api/sample-data` – preview of `input/` files
- `GET  /api/download?type=skus|labels|certificates|all` – download ZIPs of inputs
- `GET  /api/refresh` – clears all DB data (current behavior) and refreshes dashboard

---

## Agents Overview

1. **Intake Agent** – reads `input/` JSON & PDFs; normalizes payloads
2. **Integration Agent** – upserts SKUs into SQLite; logs audit
3. **Claim Extraction Agent** – supplier + description + label OCR
4. **Verification Agent** – rules/ML verification; certificate status
5. **Decision Agent** – creates tasks for HITL
6. **Governance Agent** – aggregates metrics, reports, and audit trail

---

## Project Structure

```
shelftruth_label_aiassistant/
├── agents/                 # Individual agent implementations
├── database/               # Database schema and operations
├── models/                 # ML models and training scripts
├── static/                 # Frontend assets (CSS, JS, images)
├── templates/              # HTML templates (Dashboard, Retail, Audit, Report)
├── input/                  # Sample data files
├── app.py                  # Flask application entrypoint
└── requirements.txt        # Python dependencies
```

### Sample Data (`input/`)

- `supplier_skus.json` – sample SKUs with claims and descriptions
- `sku_labels/` – product label PDFs
- `sku_certificates/` (or `sku_cerificates/`) – certificate PDFs
- `rules.json` – compliance rule configuration

---

## Claim Sources (as shown in Retail Assistant)

- **supplier** – declared in `supplier_skus.json`
- **description** – detected from SKU description text
- **label_ocr** – detected on the label via OCR

---

## Troubleshooting

- Use Python 3.11 and a fresh venv if install errors occur.
- If the app says “Address already in use”, set a different `PORT`.
- If OCR seems slow on large PDFs, try running the pipeline once then refresh the dashboard.
- The Refresh button currently clears all DB data (SKUs, claims, decisions, tasks, audit). Run the pipeline again after a refresh to repopulate.
- If the UI ever shows a spinner too long, use the Cancel button; network calls have timeouts and the spinner auto-hides.

---

## Notes

- Pure-Python OCR stack (no system installs required).
- The download API helps export the sample inputs as ZIP files for demos.
- `.gitignore` excludes virtualenvs, caches, and local DB by default; you may re-enable DB tracking if desired.
