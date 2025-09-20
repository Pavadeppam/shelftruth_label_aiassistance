import json
from datetime import datetime
from database.schema import ShelfTruthDB

class IntegrationAgent:
    """
    Integration Agent
    
    Detects uploads and synchronizes data into ERP/PIM system.
    Treats SQLite as the "mini ERP/PIM" layer.
    """
    
    def __init__(self, db: ShelfTruthDB):
        self.db = db
        self.agent_name = "Integration Agent"
    
    def sync_sku_data(self, processed_skus):
        """
        Synchronize processed SKU data into the database (ERP/PIM)
        
        Args:
            processed_skus: List of processed SKU data from Intake Agent
        
        Returns:
            List of SKU IDs that were successfully synced
        """
        synced_sku_ids = []
        
        self.db.log_audit(self.agent_name, "SYNC_STARTED", None, {
            "sku_count": len(processed_skus)
        })
        
        try:
            for sku_data in processed_skus:
                sku_id = self._sync_single_sku(sku_data)
                if sku_id:
                    synced_sku_ids.append(sku_id)
            
            self.db.log_audit(self.agent_name, "SYNC_COMPLETED", None, {
                "synced_count": len(synced_sku_ids),
                "sku_ids": synced_sku_ids
            })
            
            return synced_sku_ids
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "SYNC_ERROR", None, {
                "error": str(e)
            })
            raise e
    
    def _sync_single_sku(self, sku_data):
        """Sync a single SKU into the database"""
        try:
            sku_code = sku_data['sku_code']
            name = sku_data['name']
            description = sku_data['description']
            supplier_claims = sku_data['supplier_claims']
            label_file_path = sku_data['label_file_path']
            certificate_files = sku_data['certificate_files']
            
            # Insert SKU master data into database
            sku_id = self.db.insert_sku(
                sku_code=sku_code,
                name=name,
                description=description,
                supplier_claims=supplier_claims,
                label_file_path=label_file_path,
                certificate_files=certificate_files
            )
            
            # Insert supplier claims as initial claims
            for claim in supplier_claims:
                self.db.insert_claim(
                    sku_id=sku_id,
                    claim_text=claim,
                    source='supplier',
                    confidence_score=1.0
                )
            
            # Validate certificate files exist
            self._validate_certificate_files(sku_id, certificate_files)
            
            self.db.log_audit(self.agent_name, "SKU_SYNCED", sku_id, {
                "sku_code": sku_code,
                "claims_count": len(supplier_claims),
                "certificates_count": len(certificate_files) if certificate_files else 0,
                "label_available": label_file_path is not None
            })
            
            return sku_id
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "SKU_SYNC_ERROR", None, {
                "sku_code": sku_data.get('sku_code', 'unknown'),
                "error": str(e)
            })
            return None
    
    def _validate_certificate_files(self, sku_id, certificate_files):
        """Validate that certificate files exist and log their status"""
        if not certificate_files:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        for cert_file in certificate_files:
            try:
                import os
                if os.path.exists(cert_file):
                    validation_status = "VALID"
                    validation_details = f"File found at {cert_file}"
                else:
                    validation_status = "MISSING"
                    validation_details = f"File not found at {cert_file}"
                
                # Determine certificate type from filename
                cert_type = self._determine_certificate_type(cert_file)
                cert_name = os.path.basename(cert_file)
                
                cursor.execute('''
                    INSERT INTO certificate_validations 
                    (sku_id, certificate_name, certificate_type, validation_status, validation_details)
                    VALUES (?, ?, ?, ?, ?)
                ''', (sku_id, cert_name, cert_type, validation_status, validation_details))
                
            except Exception as e:
                cursor.execute('''
                    INSERT INTO certificate_validations 
                    (sku_id, certificate_name, certificate_type, validation_status, validation_details)
                    VALUES (?, ?, ?, ?, ?)
                ''', (sku_id, os.path.basename(cert_file), "UNKNOWN", "ERROR", str(e)))
        
        conn.commit()
        conn.close()
    
    def _determine_certificate_type(self, cert_file):
        """Determine certificate type from filename"""
        filename_lower = cert_file.lower()
        
        if 'lab' in filename_lower and 'nutrition' in filename_lower:
            return "Lab Nutrition Analysis"
        elif 'lab' in filename_lower and 'allergen' in filename_lower:
            return "Allergen Lab Test"
        elif 'soil' in filename_lower and 'association' in filename_lower:
            return "Soil Association Certification"
        elif 'fairtrade' in filename_lower:
            return "Fairtrade License"
        elif 'carbon' in filename_lower:
            return "Carbon Neutral Audit"
        elif 'supplier' in filename_lower and 'declaration' in filename_lower:
            return "Supplier Declaration"
        else:
            return "Other Certificate"
    
    def get_sku_by_code(self, sku_code):
        """Retrieve SKU data by SKU code"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, sku_code, name, description, supplier_claims, 
                   label_file_path, certificate_files, created_at, updated_at
            FROM skus 
            WHERE sku_code = ?
        ''', (sku_code,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'id': result[0],
                'sku_code': result[1],
                'name': result[2],
                'description': result[3],
                'supplier_claims': json.loads(result[4]) if result[4] else [],
                'label_file_path': result[5],
                'certificate_files': json.loads(result[6]) if result[6] else [],
                'created_at': result[7],
                'updated_at': result[8]
            }
        
        return None
    
    def get_all_skus(self):
        """Retrieve all SKUs from the database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, sku_code, name, description, supplier_claims, 
                   label_file_path, certificate_files, created_at, updated_at
            FROM skus 
            ORDER BY sku_code
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        skus = []
        for result in results:
            skus.append({
                'id': result[0],
                'sku_code': result[1],
                'name': result[2],
                'description': result[3],
                'supplier_claims': json.loads(result[4]) if result[4] else [],
                'label_file_path': result[5],
                'certificate_files': json.loads(result[6]) if result[6] else [],
                'created_at': result[7],
                'updated_at': result[8]
            })
        
        return skus
    
    def update_sku_status(self, sku_id, status_updates):
        """Update SKU status information"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # This could be extended to include status fields in the SKU table
        # For now, we'll log the status update
        self.db.log_audit(self.agent_name, "SKU_STATUS_UPDATED", sku_id, status_updates)
        
        conn.close()
