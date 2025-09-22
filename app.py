from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime
import io
import zipfile
from werkzeug.utils import secure_filename

# Import our agents
from database.schema import ShelfTruthDB
from agents.intake_agent import IntakeAgent
from agents.integration_agent import IntegrationAgent
from agents.claim_extraction_agent import ClaimExtractionAgent
from agents.verification_agent import VerificationAgent
from agents.decision_agent import DecisionAgent
from agents.governance_agent import GovernanceAgent

app = Flask(__name__)
CORS(app)

# Initialize database and agents
db = ShelfTruthDB()
intake_agent = IntakeAgent(db)
integration_agent = IntegrationAgent(db)
claim_extraction_agent = ClaimExtractionAgent(db)
verification_agent = VerificationAgent(db)
decision_agent = DecisionAgent(db)
governance_agent = GovernanceAgent(db)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/dashboard')
def api_dashboard():
    """API endpoint for dashboard data"""
    try:
        dashboard_data = governance_agent.get_dashboard_data()
        return jsonify({
            'success': True,
            'data': dashboard_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/refresh')
def api_refresh():
    """API endpoint to refresh dashboard data"""
    try:
        # Purge ALL business data as requested when refresh is triggered
        db.clear_all_data()
        dashboard_data = governance_agent.refresh_dashboard()
        return jsonify({
            'success': True,
            'data': dashboard_data,
            'message': 'Dashboard refreshed successfully and all data cleared'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/trigger-pipeline', methods=['POST'])
def api_trigger_pipeline():
    """API endpoint to trigger the complete pipeline"""
    try:
        # Step 1: Intake Agent - Process supplier data
        processed_skus = intake_agent.trigger_pipeline()
        
        # Step 2: Integration Agent - Sync to database
        synced_sku_ids = integration_agent.sync_sku_data(processed_skus)
        
        # Step 3: Claim Extraction Agent - Extract claims
        extraction_results = claim_extraction_agent.extract_claims_from_skus(synced_sku_ids)
        
        # Step 4: Verification Agent - Verify claims
        verification_results = verification_agent.verify_claims_for_skus(synced_sku_ids)
        
        return jsonify({
            'success': True,
            'message': 'Pipeline executed successfully',
            'results': {
                'processed_skus': len(processed_skus),
                'synced_skus': len(synced_sku_ids),
                'extraction': extraction_results,
                'verification': verification_results
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks')
def api_tasks():
    """API endpoint to get pending tasks"""
    try:
        task_type = request.args.get('type')
        limit = int(request.args.get('limit', 50))
        
        tasks = decision_agent.get_pending_tasks(task_type, limit)
        
        return jsonify({
            'success': True,
            'tasks': tasks
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks/<int:task_id>/decision', methods=['POST'])
def api_task_decision(task_id):
    """API endpoint to process task decision"""
    try:
        data = request.get_json()
        action = data.get('action')
        reasoning = data.get('reasoning', '')
        additional_data = data.get('additional_data', {})
        
        result = decision_agent.process_task_decision(
            task_id, action, reasoning, additional_data
        )
        
        return jsonify({
            'success': True,
            'result': result,
            'message': f'Task {task_id} processed successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tasks/bulk-approve', methods=['POST'])
def api_bulk_approve():
    """API endpoint for bulk task approval"""
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        reasoning = data.get('reasoning', 'Bulk approval')
        
        results = decision_agent.bulk_approve_tasks(task_ids, reasoning)
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': len(task_ids),
                'successful': successful,
                'failed': failed
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/compliance-report')
def api_compliance_report():
    """API endpoint to generate compliance report"""
    try:
        sku_id = request.args.get('sku_id')
        if sku_id:
            sku_id = int(sku_id)
        
        report = governance_agent.generate_compliance_report(sku_id)
        
        return jsonify({
            'success': True,
            'report': report
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/audit-log')
def api_audit_log():
    """API endpoint to get audit log"""
    try:
        limit = int(request.args.get('limit', 100))
        audit_log = governance_agent._get_recent_audit_trail(limit)
        
        return jsonify({
            'success': True,
            'audit_log': audit_log
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/skus')
def api_skus():
    """API endpoint to get all SKUs"""
    try:
        skus = integration_agent.get_all_skus()
        return jsonify({
            'success': True,
            'skus': skus
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/skus/<int:sku_id>/claims')
def api_sku_claims(sku_id):
    """API endpoint to get claims for a specific SKU"""
    try:
        claims = claim_extraction_agent.get_claims_for_sku(sku_id)
        return jsonify({
            'success': True,
            'claims': claims
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/retail-assistant')
def retail_assistant():
    """Retail Assistant interface"""
    return render_template('retail_assistant.html')

@app.route('/compliance-report')
def compliance_report_page():
    """Compliance report page"""
    return render_template('compliance_report.html')

@app.route('/audit-trail')
def audit_trail_page():
    """Audit trail page"""
    return render_template('audit_trail.html')

@app.route('/api/statistics')
def api_statistics():
    """API endpoint for various statistics"""
    try:
        task_stats = decision_agent.get_task_statistics()
        verification_summary = verification_agent.get_verification_summary()
        
        return jsonify({
            'success': True,
            'statistics': {
                'tasks': task_stats,
                'verification': verification_summary
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/sample-data')
def api_sample_data():
    """API endpoint to get information about sample data files"""
    try:
        sample_data = {
            'supplier_skus': [],
            'labels': [],
            'certificates': []
        }
        
        # Check supplier SKUs
        skus_path = 'input/supplier_skus.json'
        if os.path.exists(skus_path):
            with open(skus_path, 'r') as f:
                sample_data['supplier_skus'] = json.load(f)
        
        # Check labels directory
        labels_dir = 'input/sku_labels'
        if os.path.exists(labels_dir):
            sample_data['labels'] = [
                f for f in os.listdir(labels_dir) 
                if f.endswith('.pdf')
            ]
        
        # Check certificates directory (standardized)
        certs_dir = 'input/sku_certificates'
        if os.path.exists(certs_dir):
            sample_data['certificates'] = [
                f for f in os.listdir(certs_dir) 
                if f.endswith('.pdf')
            ]
        
        return jsonify({
            'success': True,
            'sample_data': sample_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download')
def api_download():
    """Download pre-loaded data as ZIP. Supported types: skus, labels, certificates, all"""
    try:
        download_type = request.args.get('type', 'all')
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            base_prefix = 'input/'

            def add_file_to_zip(file_path, arcname=None):
                if not os.path.exists(file_path):
                    return
                arc = arcname or os.path.relpath(file_path, start='.')
                zf.write(file_path, arcname=arc)

            # Supplier SKUs JSON
            if download_type in ('skus', 'all'):
                skus_path = os.path.join('input', 'supplier_skus.json')
                if os.path.exists(skus_path):
                    add_file_to_zip(skus_path, arcname=os.path.join(base_prefix, 'supplier_skus.json'))

            # Labels
            if download_type in ('labels', 'all'):
                labels_dir = os.path.join('input', 'sku_labels')
                if os.path.exists(labels_dir):
                    for fname in os.listdir(labels_dir):
                        if fname.lower().endswith('.pdf'):
                            add_file_to_zip(os.path.join(labels_dir, fname), arcname=os.path.join(base_prefix, 'sku_labels', fname))

            # Certificates
            if download_type in ('certificates', 'all'):
                certs_dir = os.path.join('input', 'sku_certificates')
                if os.path.exists(certs_dir):
                    for fname in os.listdir(certs_dir):
                        if fname.lower().endswith('.pdf'):
                            add_file_to_zip(os.path.join(certs_dir, fname), arcname=os.path.join(base_prefix, 'sku_certificates', fname))

        memory_file.seek(0)
        filename_map = {
            'skus': 'shelftruth_skus.zip',
            'labels': 'shelftruth_labels.zip',
            'certificates': 'shelftruth_certificates.zip',
            'all': 'shelftruth_all_data.zip'
        }
        fname = filename_map.get(download_type, 'shelftruth_all_data.zip')
        return send_file(memory_file, as_attachment=True, download_name=fname, mimetype='application/zip')

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload a new SKU with label and certificate PDFs (multipart/form-data)

    Expected form fields:
    - sku: string (required)
    - name: string (required)
    - description: string (optional)
    - claims: string (optional, comma-separated)
    - label: file (PDF, optional)
    - certificates: files[] (PDFs, optional, multiple)
    """
    try:
        # Ensure input directories exist
        os.makedirs('input', exist_ok=True)
        labels_dir = os.path.join('input', 'sku_labels')
        certs_dir = os.path.join('input', 'sku_certificates')
        os.makedirs(labels_dir, exist_ok=True)
        os.makedirs(certs_dir, exist_ok=True)

        sku = request.form.get('sku', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        claims_raw = request.form.get('claims', '').strip()

        if not sku or not name:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: sku and name'
            }), 400

        # Parse claims (comma-separated -> list)
        claims = [c.strip() for c in claims_raw.split(',') if c.strip()] if claims_raw else []

        saved_label_filename = None
        label_file = request.files.get('label')
        if label_file and label_file.filename:
            if not label_file.filename.lower().endswith('.pdf'):
                return jsonify({'success': False, 'error': 'Label must be a PDF'}), 400
            safe_name = secure_filename(label_file.filename)
            # Prefix with SKU for easier matching by IntakeAgent
            prefixed = f"{sku}_{safe_name}"
            label_path = os.path.join(labels_dir, prefixed)
            label_file.save(label_path)
            saved_label_filename = prefixed

        saved_cert_filenames = []
        # certificates may be provided as single or multiple files under key 'certificates'
        cert_files = request.files.getlist('certificates') or []
        for cf in cert_files:
            if not cf or not cf.filename:
                continue
            if not cf.filename.lower().endswith('.pdf'):
                return jsonify({'success': False, 'error': 'All certificates must be PDFs'}), 400
            safe_name = secure_filename(cf.filename)
            prefixed = f"{sku}_{safe_name}"
            cert_path = os.path.join(certs_dir, prefixed)
            cf.save(cert_path)
            saved_cert_filenames.append(prefixed)

        # Append to supplier_skus.json
        skus_json_path = os.path.join('input', 'supplier_skus.json')
        skus_data = []
        if os.path.exists(skus_json_path):
            try:
                with open(skus_json_path, 'r') as f:
                    skus_data = json.load(f)
                    if not isinstance(skus_data, list):
                        skus_data = []
            except Exception:
                # If file is corrupt, reset to empty list
                skus_data = []

        new_entry = {
            'sku': sku,
            'name': name,
            'description': description,
            'claims': claims,
            # Intake/Integration expect certificate filenames
            'certificates': saved_cert_filenames
        }
        # If a label was uploaded, it's not directly referenced in JSON, but IntakeAgent
        # finds it by SKU prefix in input/sku_labels/. We still include raw_data consistency.

        skus_data.append(new_entry)
        with open(skus_json_path, 'w') as f:
            json.dump(skus_data, f, indent=2)

        # Log audit event
        db.log_audit('Intake Agent', 'SKU_UPLOADED', None, {
            'sku': sku,
            'label_file': saved_label_filename,
            'certificates': saved_cert_filenames
        })

        # Check if pipeline should run automatically (default: true)
        run_pipeline_flag = str(request.form.get('run_pipeline', 'true')).lower() in ('1', 'true', 'yes', 'on')

        if run_pipeline_flag:
            # Automatically trigger the full pipeline so the UI doesn't need a separate click
            processed_skus = intake_agent.trigger_pipeline(
                supplier_skus_path=os.path.join('input', 'supplier_skus.json'),
                labels_dir=os.path.join('input', 'sku_labels'),
                certificates_dir=os.path.join('input', 'sku_certificates')
            )
            synced_sku_ids = integration_agent.sync_sku_data(processed_skus)
            extraction_results = claim_extraction_agent.extract_claims_from_skus(synced_sku_ids)
            verification_results = verification_agent.verify_claims_for_skus(synced_sku_ids)

            return jsonify({
                'success': True,
                'message': 'SKU uploaded and pipeline executed successfully',
                'sku': new_entry,
                'pipeline': {
                    'processed_skus': len(processed_skus),
                    'synced_skus': len(synced_sku_ids),
                    'extraction': extraction_results,
                    'verification': verification_results
                }
            })
        else:
            return jsonify({
                'success': True,
                'message': 'SKU uploaded successfully (pipeline not executed)',
                'sku': new_entry,
                'pipeline': None
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', 
                         error_code=404, 
                         error_message="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', 
                         error_code=500, 
                         error_message="Internal server error"), 500

if __name__ == '__main__':
    # Ensure required directories exist
    os.makedirs('models', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Initialize the database
    print("Initializing ShelfTruth database...")
    db.init_database()
    
    print("ShelfTruth Multi-Agent AI System")
    print("================================")
    print("Starting Flask application...")
    port = int(os.environ.get('PORT', 5000))
    base_url = f"http://localhost:{port}"
    print(f"Dashboard: {base_url}")
    print(f"Retail Assistant: {base_url}/retail-assistant")
    print(f"Compliance Report: {base_url}/compliance-report")
    print(f"Audit Trail: {base_url}/audit-trail")
    
    app.run(debug=True, host='0.0.0.0', port=port)
