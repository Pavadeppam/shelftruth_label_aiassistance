import json
import os
from datetime import datetime
from database.schema import ShelfTruthDB

class IntakeAgent:
    """
    Data Intake & Event Trigger Agent
    
    Captures new/updated product SKUs, labels, and certificates from suppliers.
    Mimics supplier uploading SKU details + label + certificates.
    """
    
    def __init__(self, db: ShelfTruthDB):
        self.db = db
        self.agent_name = "Intake Agent"
    
    def process_supplier_data(self, supplier_skus_path, labels_dir, certificates_dir):
        """
        Process supplier SKU data and associated files
        
        Args:
            supplier_skus_path: Path to supplier_skus.json
            labels_dir: Directory containing label PDFs
            certificates_dir: Directory containing certificate PDFs
        
        Returns:
            List of processed SKU IDs
        """
        processed_skus = []
        
        try:
            # Load supplier SKU data
            with open(supplier_skus_path, 'r') as f:
                supplier_data = json.load(f)
            
            self.db.log_audit(self.agent_name, "DATA_INTAKE_STARTED", None, {
                "source_file": supplier_skus_path,
                "sku_count": len(supplier_data)
            })
            
            for sku_data in supplier_data:
                sku_id = self._process_single_sku(sku_data, labels_dir, certificates_dir)
                if sku_id:
                    processed_skus.append(sku_id)
            
            self.db.log_audit(self.agent_name, "DATA_INTAKE_COMPLETED", None, {
                "processed_count": len(processed_skus),
                "sku_ids": processed_skus
            })
            
            return processed_skus
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "DATA_INTAKE_ERROR", None, {
                "error": str(e)
            })
            raise e
    
    def _process_single_sku(self, sku_data, labels_dir, certificates_dir):
        """Process a single SKU from supplier data"""
        try:
            sku_code = sku_data.get('sku')
            name = sku_data.get('name')
            description = sku_data.get('description')
            supplier_claims = sku_data.get('claims', [])
            certificate_names = sku_data.get('certificates', [])
            
            # Find label file
            label_file_path = self._find_label_file(sku_code, labels_dir)
            
            # Find certificate files
            certificate_files = self._find_certificate_files(sku_code, certificate_names, certificates_dir)
            
            # Store in database (this will be handled by Integration Agent)
            # For now, we'll return the data structure
            return {
                'sku_code': sku_code,
                'name': name,
                'description': description,
                'supplier_claims': supplier_claims,
                'label_file_path': label_file_path,
                'certificate_files': certificate_files,
                'raw_data': sku_data
            }
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "SKU_PROCESSING_ERROR", None, {
                "sku_code": sku_data.get('sku', 'unknown'),
                "error": str(e)
            })
            return None
    
    def _find_label_file(self, sku_code, labels_dir):
        """Find the label file for a given SKU"""
        if not os.path.exists(labels_dir):
            return None
        
        # Look for files that start with the SKU code
        for filename in os.listdir(labels_dir):
            if filename.startswith(sku_code) and filename.endswith('.pdf'):
                return os.path.join(labels_dir, filename)
        
        return None
    
    def _find_certificate_files(self, sku_code, certificate_names, certificates_dir):
        """Find certificate files for a given SKU"""
        found_certificates = []
        
        if not os.path.exists(certificates_dir):
            return found_certificates
        
        # Get all certificate files in directory
        available_files = os.listdir(certificates_dir)
        
        # Match certificate names to actual files
        for cert_name in certificate_names:
            # Try exact match first
            if cert_name in available_files:
                found_certificates.append(os.path.join(certificates_dir, cert_name))
                continue
            
            # Try to find files that contain the SKU code and certificate type
            for filename in available_files:
                if (sku_code in filename and 
                    any(keyword in filename.lower() for keyword in 
                        self._extract_cert_keywords(cert_name))):
                    found_certificates.append(os.path.join(certificates_dir, filename))
                    break
        
        return found_certificates
    
    def _extract_cert_keywords(self, cert_name):
        """Extract keywords from certificate name for matching"""
        cert_name_lower = cert_name.lower()
        keywords = []
        
        if 'lab' in cert_name_lower:
            keywords.append('lab')
        if 'nutrition' in cert_name_lower:
            keywords.append('nutrition')
        if 'allergen' in cert_name_lower:
            keywords.append('allergen')
        if 'soil' in cert_name_lower:
            keywords.append('soil')
        if 'fairtrade' in cert_name_lower:
            keywords.append('fairtrade')
        if 'carbon' in cert_name_lower:
            keywords.append('carbon')
        
        return keywords if keywords else [cert_name_lower.replace('.pdf', '')]
    
    def trigger_pipeline(self, supplier_skus_path="input/supplier_skus.json", 
                        labels_dir="input/sku_labels", 
                        certificates_dir="input/sku_certificates"):
        """
        Trigger the complete intake pipeline
        
        This simulates the user clicking the Upload CTA in the demo app
        """
        self.db.log_audit(self.agent_name, "PIPELINE_TRIGGERED", None, {
            "trigger_time": datetime.now().isoformat(),
            "source_paths": {
                "skus": supplier_skus_path,
                "labels": labels_dir,
                "certificates": certificates_dir
            }
        })
        
        # Process the supplier data
        processed_data = []
        
        try:
            with open(supplier_skus_path, 'r') as f:
                supplier_data = json.load(f)
            
            # Handle directory name typo gracefully: try alternate certificates directory if missing
            if not os.path.exists(certificates_dir):
                alt_dir = certificates_dir.replace("sku_certificates", "sku_cerificates")
                if os.path.exists(alt_dir):
                    certificates_dir = alt_dir
            
            for sku_data in supplier_data:
                processed_sku = self._process_single_sku(sku_data, labels_dir, certificates_dir)
                if processed_sku:
                    processed_data.append(processed_sku)
            
            self.db.log_audit(self.agent_name, "PIPELINE_COMPLETED", None, {
                "processed_count": len(processed_data)
            })
            
            return processed_data
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "PIPELINE_ERROR", None, {
                "error": str(e)
            })
            raise e
