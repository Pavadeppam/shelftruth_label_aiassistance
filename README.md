# ShelfTruth - Multi-Agent AI Orchestration System

ShelfTruth is a comprehensive multi-agent AI system that automates the compliance lifecycle of SKUs in retail business. The system orchestrates multiple specialized agents to handle data intake, integration, claim extraction, verification, decision-making, and governance.

## System Architecture

### Agents Overview

1. **Intake Agent** - Captures new/updated product SKUs, labels, and certificates
2. **Integration Agent** - Synchronizes data into ERP/PIM systems
3. **Claim Extraction Agent** - Extracts claims using OCR and NLP
4. **Verification Agent** - Validates claims against rules and ML models
5. **Decision & Feedback Agents** - Human-in-the-loop finalization
6. **Governance Agent** - Multi-agent dashboard and audit logging

## Installation

1. Install Python dependencies (pure pip stack, no OS-level OCR tools required):
```bash
pip install -r requirements.txt
```

This installs:
- `pdfminer.six` for text-based PDF extraction
- `PyMuPDF` for rendering PDF pages to images in-memory
- `EasyOCR` for OCR on scanned/image PDFs (installs a CPU PyTorch wheel automatically)

Note: We removed the `pytesseract` + `pdf2image` path to avoid system-level installs. If you later want to add Tesseract-based OCR, we can re-enable it.

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Use the dashboard to:
   - Upload new SKU data
   - Monitor compliance pipeline
   - Review and approve decisions
   - View audit logs and governance metrics

## Project Structure

```
shelftruth_label/
├── agents/                 # Individual agent implementations
├── database/              # Database schema and operations
├── models/                # ML models and training scripts
├── static/                # Frontend assets (CSS, JS, images)
├── templates/             # HTML templates
├── input/                 # Sample data files
├── app.py                 # Main Flask application
└── requirements.txt       # Python dependencies
```

## Sample Data

The system comes with pre-loaded sample data:
- `input/supplier_skus.json` - Sample SKU data
- `input/sku_labels/` - Product label PDFs
- `input/sku_certificates/` - Certificate PDFs
- `input/rules.json` - Compliance rules configuration

## Features

- **Real-time OCR** - Extract text from product labels
- **Rule-based Validation** - Deterministic compliance checking
- **ML-powered Classification** - Intelligent claim verification
- **Human-in-the-loop** - Retail assistant workflow
- **Audit Trail** - Complete governance and logging
- **Multi-agent Dashboard** - Centralized monitoring and control
