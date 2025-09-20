import sqlite3
import json
from datetime import datetime
import os

class ShelfTruthDB:
    def __init__(self, db_path="shelftruth.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database with all required tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # SKUs table - master product data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                supplier_claims TEXT, -- JSON array of claims from supplier
                label_file_path TEXT,
                certificate_files TEXT, -- JSON array of certificate file paths
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Claims table - extracted claims from labels and descriptions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER,
                claim_text TEXT NOT NULL,
                source TEXT, -- 'supplier', 'label_ocr', 'description'
                confidence_score REAL DEFAULT 1.0,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
        ''')
        
        # Decisions table - verification results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER,
                claim_id INTEGER,
                decision TEXT NOT NULL, -- 'PASS', 'FAIL', 'REVIEW', 'WARNING'
                rule_matched TEXT,
                ml_confidence REAL,
                certificate_status TEXT, -- 'FOUND', 'MISSING', 'INVALID'
                reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus (id),
                FOREIGN KEY (claim_id) REFERENCES claims (id)
            )
        ''')
        
        # Tasks table - retail assistant actions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER,
                decision_id INTEGER,
                task_type TEXT NOT NULL, -- 'approve', 'reject', 'request_evidence', 'modify'
                status TEXT DEFAULT 'open', -- 'open', 'completed', 'cancelled'
                assigned_to TEXT DEFAULT 'retail_assistant',
                description TEXT,
                action_taken TEXT,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus (id),
                FOREIGN KEY (decision_id) REFERENCES decisions (id)
            )
        ''')
        
        # Audit log table - governance and traceability
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                action TEXT NOT NULL,
                sku_id INTEGER,
                details TEXT, -- JSON with additional context
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
        ''')
        
        # Certificate validation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS certificate_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER,
                certificate_name TEXT,
                certificate_type TEXT,
                validation_status TEXT, -- 'VALID', 'INVALID', 'MISSING', 'EXPIRED'
                validation_details TEXT,
                validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sku_id) REFERENCES skus (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_audit(self, agent_name, action, sku_id=None, details=None):
        """Log an action to the audit trail"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        details_json = json.dumps(details) if details else None
        
        cursor.execute('''
            INSERT INTO audit_log (agent_name, action, sku_id, details)
            VALUES (?, ?, ?, ?)
        ''', (agent_name, action, sku_id, details_json))
        
        conn.commit()
        conn.close()
    
    def insert_sku(self, sku_code, name, description, supplier_claims, label_file_path=None, certificate_files=None):
        """Insert a new SKU into the database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        supplier_claims_json = json.dumps(supplier_claims) if supplier_claims else None
        certificate_files_json = json.dumps(certificate_files) if certificate_files else None
        
        cursor.execute('''
            INSERT OR REPLACE INTO skus 
            (sku_code, name, description, supplier_claims, label_file_path, certificate_files, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (sku_code, name, description, supplier_claims_json, label_file_path, certificate_files_json, datetime.now()))
        
        sku_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Log the action
        self.log_audit("Integration Agent", "SKU_INSERTED", sku_id, {
            "sku_code": sku_code,
            "name": name
        })
        
        return sku_id
    
    def insert_claim(self, sku_id, claim_text, source, confidence_score=1.0):
        """Insert a claim for a SKU"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO claims (sku_id, claim_text, source, confidence_score)
            VALUES (?, ?, ?, ?)
        ''', (sku_id, claim_text, source, confidence_score))
        
        claim_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Log the action
        self.log_audit("Claim Extraction Agent", "CLAIM_EXTRACTED", sku_id, {
            "claim_text": claim_text,
            "source": source,
            "confidence": confidence_score
        })
        
        return claim_id
    
    def insert_decision(self, sku_id, claim_id, decision, rule_matched=None, ml_confidence=None, certificate_status=None, reasoning=None):
        """Insert a verification decision"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO decisions 
            (sku_id, claim_id, decision, rule_matched, ml_confidence, certificate_status, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (sku_id, claim_id, decision, rule_matched, ml_confidence, certificate_status, reasoning))
        
        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Log the action
        self.log_audit("Verification Agent", "DECISION_MADE", sku_id, {
            "decision": decision,
            "rule_matched": rule_matched,
            "reasoning": reasoning
        })
        
        return decision_id
    
    def create_task(self, sku_id, decision_id, task_type, description):
        """Create a task for retail assistant"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tasks (sku_id, decision_id, task_type, description)
            VALUES (?, ?, ?, ?)
        ''', (sku_id, decision_id, task_type, description))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Log the action
        self.log_audit("Decision Agent", "TASK_CREATED", sku_id, {
            "task_type": task_type,
            "description": description
        })
        
        return task_id
    
    def get_skus_with_claims_and_decisions(self):
        """Get all SKUs with their claims and decisions for dashboard"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                s.id, s.sku_code, s.name, s.description, s.supplier_claims,
                c.id as claim_id, c.claim_text, c.source, c.confidence_score,
                d.id as decision_id, d.decision, d.rule_matched, d.ml_confidence, 
                d.certificate_status, d.reasoning,
                t.id as task_id, t.task_type, t.status as task_status, t.description as task_description
            FROM skus s
            LEFT JOIN claims c ON s.id = c.sku_id
            LEFT JOIN decisions d ON c.id = d.claim_id
            LEFT JOIN tasks t ON d.id = t.decision_id
            ORDER BY s.sku_code, c.id, d.id
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return results

    def clear_audit_log(self):
        """Purge all entries from the audit_log table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM audit_log')
        conn.commit()
        conn.close()

    def clear_all_data(self):
        """Purge all entries from all business tables.
        Order matters to avoid FK issues if enabled: tasks -> decisions -> claims -> certificate_validations -> skus -> audit_log.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM tasks')
            cursor.execute('DELETE FROM decisions')
            cursor.execute('DELETE FROM claims')
            cursor.execute('DELETE FROM certificate_validations')
            cursor.execute('DELETE FROM skus')
            cursor.execute('DELETE FROM audit_log')
            conn.commit()
        finally:
            conn.close()
    
    def get_open_tasks(self):
        """Get all open tasks for retail assistant"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                t.id, t.task_type, t.description, t.created_at,
                s.sku_code, s.name,
                c.claim_text,
                d.decision, d.reasoning
            FROM tasks t
            JOIN skus s ON t.sku_id = s.id
            JOIN decisions d ON t.decision_id = d.id
            JOIN claims c ON d.claim_id = c.id
            WHERE t.status = 'open'
            ORDER BY t.created_at DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def complete_task(self, task_id, action_taken):
        """Mark a task as completed"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tasks 
            SET status = 'completed', action_taken = ?, completed_at = ?
            WHERE id = ?
        ''', (action_taken, datetime.now(), task_id))
        
        conn.commit()
        conn.close()
        
        # Log the action
        self.log_audit("Retail Assistant", "TASK_COMPLETED", None, {
            "task_id": task_id,
            "action_taken": action_taken
        })
    
    def get_audit_log(self, limit=100):
        """Get recent audit log entries"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT agent_name, action, sku_id, details, timestamp
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
