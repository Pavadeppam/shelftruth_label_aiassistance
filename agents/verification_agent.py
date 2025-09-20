import json
import os
import re
from datetime import datetime
from database.schema import ShelfTruthDB

# ML imports
try:
    import pickle
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("Warning: ML libraries not available. Install scikit-learn for full functionality.")

class VerificationAgent:
    """
    Verification Agent (Rules + ML + Certificates)
    
    Validates claims against compliance rules and required evidence.
    Uses rule-based decisions first, then falls back to ML classifier.
    Cross-checks required certificates for evidence validation.
    """
    
    def __init__(self, db: ShelfTruthDB, rules_path="input/rules.json"):
        self.db = db
        self.agent_name = "Verification Agent"
        self.rules_path = rules_path
        self.rules = self._load_rules()
        self.ml_classifier = None
        self.vectorizer = None
        self._load_or_create_ml_model()
    
    def _load_rules(self):
        """Load compliance rules from JSON file"""
        try:
            with open(self.rules_path, 'r') as f:
                rules_data = json.load(f)
            
            self.db.log_audit(self.agent_name, "RULES_LOADED", None, {
                "rules_count": len(rules_data.get('rules', [])),
                "version": rules_data.get('version', 'unknown')
            })
            
            return rules_data
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "RULES_LOAD_ERROR", None, {
                "error": str(e)
            })
            return {"rules": [], "scoring": {}, "globals": {}}
    
    def _load_or_create_ml_model(self):
        """Load existing ML model or create a new one"""
        model_path = "models/claim_classifier.pkl"
        vectorizer_path = "models/claim_vectorizer.pkl"
        
        if os.path.exists(model_path) and os.path.exists(vectorizer_path):
            try:
                with open(model_path, 'rb') as f:
                    self.ml_classifier = pickle.load(f)
                with open(vectorizer_path, 'rb') as f:
                    self.vectorizer = pickle.load(f)
                
                self.db.log_audit(self.agent_name, "ML_MODEL_LOADED", None, {
                    "model_path": model_path
                })
                
            except Exception as e:
                self.db.log_audit(self.agent_name, "ML_MODEL_LOAD_ERROR", None, {
                    "error": str(e)
                })
                self._create_default_ml_model()
        else:
            self._create_default_ml_model()
    
    def _create_default_ml_model(self):
        """Create a default ML model for claim classification"""
        if not ML_AVAILABLE:
            return
        
        # Create training data based on rules
        training_data = []
        labels = []
        
        for rule in self.rules.get('rules', []):
            claim = rule.get('claim', '')
            decision = rule.get('deterministic_decision', 'REVIEW')
            
            training_data.append(claim)
            # Convert decision to binary classification (1 = likely valid, 0 = likely invalid)
            if decision in ['PASS_IF_CERT', 'PASS']:
                labels.append(1)
            elif decision in ['FAIL']:
                labels.append(0)
            else:  # REVIEW, WARNING
                labels.append(0.5)
        
        # Add some synthetic training data
        synthetic_data = [
            ("organic certified", 1),
            ("natural ingredients", 0.8),
            ("artificial flavoring", 0.2),
            ("lab tested", 0.9),
            ("medical claim", 0.1),
            ("therapeutic benefit", 0.1),
            ("nutritionally balanced", 0.7),
            ("preservative free", 0.8),
            ("chemical free", 0.3),  # Often misleading
            ("scientifically proven", 0.6)
        ]
        
        for text, label in synthetic_data:
            training_data.append(text)
            labels.append(label)
        
        if len(training_data) > 0:
            try:
                # Create and train the model
                self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
                X = self.vectorizer.fit_transform(training_data)
                
                self.ml_classifier = LogisticRegression(random_state=42)
                self.ml_classifier.fit(X, labels)
                
                # Save the model
                os.makedirs("models", exist_ok=True)
                with open("models/claim_classifier.pkl", 'wb') as f:
                    pickle.dump(self.ml_classifier, f)
                with open("models/claim_vectorizer.pkl", 'wb') as f:
                    pickle.dump(self.vectorizer, f)
                
                self.db.log_audit(self.agent_name, "ML_MODEL_CREATED", None, {
                    "training_samples": len(training_data)
                })
                
            except Exception as e:
                self.db.log_audit(self.agent_name, "ML_MODEL_CREATE_ERROR", None, {
                    "error": str(e)
                })
    
    def verify_claims_for_skus(self, sku_ids=None):
        """
        Verify claims for all SKUs or specific SKU IDs
        
        Args:
            sku_ids: List of SKU IDs to process, or None for all SKUs
        
        Returns:
            Dictionary with verification results
        """
        if sku_ids is None:
            # Get all SKUs that have claims
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT sku_id FROM claims')
            sku_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
        
        self.db.log_audit(self.agent_name, "VERIFICATION_STARTED", None, {
            "sku_count": len(sku_ids)
        })
        
        verification_results = {
            'processed_skus': 0,
            'total_claims_verified': 0,
            'rule_based_decisions': 0,
            'ml_based_decisions': 0,
            'certificate_checks': 0,
            'errors': []
        }
        
        for sku_id in sku_ids:
            try:
                result = self._verify_claims_for_sku(sku_id)
                verification_results['processed_skus'] += 1
                verification_results['total_claims_verified'] += result['claims_verified']
                verification_results['rule_based_decisions'] += result['rule_based']
                verification_results['ml_based_decisions'] += result['ml_based']
                verification_results['certificate_checks'] += result['cert_checks']
                
            except Exception as e:
                verification_results['errors'].append({
                    'sku_id': sku_id,
                    'error': str(e)
                })
        
        self.db.log_audit(self.agent_name, "VERIFICATION_COMPLETED", None, verification_results)
        
        return verification_results
    
    def _verify_claims_for_sku(self, sku_id):
        """Verify all claims for a single SKU"""
        # Get claims for this SKU
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, claim_text, source, confidence_score
            FROM claims 
            WHERE sku_id = ?
        ''', (sku_id,))
        
        claims = cursor.fetchall()
        conn.close()
        
        result = {
            'sku_id': sku_id,
            'claims_verified': 0,
            'rule_based': 0,
            'ml_based': 0,
            'cert_checks': 0,
            'decisions': []
        }
        
        for claim_id, claim_text, source, confidence_score in claims:
            decision_result = self._verify_single_claim(sku_id, claim_id, claim_text)
            result['decisions'].append(decision_result)
            result['claims_verified'] += 1
            
            if decision_result['method'] == 'rule_based':
                result['rule_based'] += 1
            elif decision_result['method'] == 'ml_based':
                result['ml_based'] += 1
            
            if decision_result['certificate_checked']:
                result['cert_checks'] += 1
        
        return result
    
    def _verify_single_claim(self, sku_id, claim_id, claim_text):
        """Verify a single claim using rules and ML"""
        # First, try rule-based verification
        rule_result = self._check_rules(claim_text)
        
        if rule_result['matched']:
            # Rule-based decision
            decision = self._apply_rule_decision(sku_id, claim_id, claim_text, rule_result)
            method = 'rule_based'
            ml_confidence = None
        else:
            # Fall back to ML classifier
            ml_result = self._classify_with_ml(claim_text)
            decision = self._apply_ml_decision(sku_id, claim_id, claim_text, ml_result)
            method = 'ml_based'
            ml_confidence = ml_result['confidence']
        
        # Check certificates regardless of decision method
        certificate_result = self._check_certificates(sku_id, claim_text, rule_result.get('required_certs', []))
        
        # Store decision in database
        decision_id = self.db.insert_decision(
            sku_id=sku_id,
            claim_id=claim_id,
            decision=decision['decision'],
            rule_matched=rule_result.get('rule_name'),
            ml_confidence=ml_confidence,
            certificate_status=certificate_result['status'],
            reasoning=decision['reasoning']
        )
        
        # Create tasks if needed
        if decision['decision'] in ['REVIEW', 'FAIL', 'WARNING']:
            self._create_verification_task(sku_id, decision_id, decision, certificate_result)
        
        return {
            'claim_id': claim_id,
            'claim_text': claim_text,
            'decision': decision['decision'],
            'method': method,
            'certificate_checked': certificate_result['checked'],
            'decision_id': decision_id
        }
    
    def _check_rules(self, claim_text):
        """Check claim against loaded rules"""
        claim_lower = claim_text.lower().strip()
        
        for rule in self.rules.get('rules', []):
            rule_claim = rule.get('claim', '').lower()
            match_type = rule.get('match_type', 'exact')
            
            matched = False
            if match_type == 'exact':
                matched = claim_lower == rule_claim
            elif match_type == 'contains':
                matched = rule_claim in claim_lower
            elif match_type == 'regex':
                pattern = rule.get('match_value', rule_claim)
                matched = bool(re.search(pattern, claim_lower, re.IGNORECASE))
            
            if matched:
                return {
                    'matched': True,
                    'rule_name': rule.get('claim'),
                    'decision': rule.get('deterministic_decision'),
                    'required_certs': rule.get('required_cert_types', []),
                    'notes': rule.get('notes', ''),
                    'remediation': rule.get('remediation', '')
                }
        
        return {'matched': False}
    
    def _classify_with_ml(self, claim_text):
        """Classify claim using ML model"""
        if not self.ml_classifier or not self.vectorizer:
            return {
                'confidence': 0.5,
                'prediction': 'REVIEW',
                'available': False
            }
        
        try:
            # Vectorize the claim
            X = self.vectorizer.transform([claim_text])
            
            # Get prediction and probability
            prediction_proba = self.ml_classifier.predict_proba(X)[0]
            prediction = self.ml_classifier.predict(X)[0]
            
            # Convert to decision
            if prediction > 0.7:
                decision = 'PASS'
            elif prediction < 0.3:
                decision = 'FAIL'
            else:
                decision = 'REVIEW'
            
            return {
                'confidence': float(max(prediction_proba)),
                'prediction': decision,
                'available': True
            }
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "ML_CLASSIFICATION_ERROR", None, {
                "claim": claim_text,
                "error": str(e)
            })
            
            return {
                'confidence': 0.5,
                'prediction': 'REVIEW',
                'available': False
            }
    
    def _apply_rule_decision(self, sku_id, claim_id, claim_text, rule_result):
        """Apply rule-based decision logic"""
        decision = rule_result['decision']
        
        if decision == 'PASS_IF_CERT':
            # Check if required certificates are available
            cert_result = self._check_certificates(sku_id, claim_text, rule_result['required_certs'])
            if cert_result['status'] == 'FOUND':
                final_decision = 'PASS'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Required certificates found."
            else:
                final_decision = 'REVIEW'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Missing required certificates: {', '.join(rule_result['required_certs'])}"
        
        elif decision == 'REVIEW_IF_CERT_MISSING':
            cert_result = self._check_certificates(sku_id, claim_text, rule_result['required_certs'])
            if cert_result['status'] == 'FOUND':
                final_decision = 'PASS'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Required certificates found."
            else:
                final_decision = 'REVIEW'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Requires human review due to missing certificates."
        
        elif decision == 'REVIEW_IF_NO_THIRD_PARTY':
            cert_result = self._check_certificates(sku_id, claim_text, rule_result['required_certs'])
            if cert_result['has_third_party']:
                final_decision = 'PASS'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Third-party evidence found."
            else:
                final_decision = 'REVIEW'
                reasoning = f"Rule matched: {rule_result['rule_name']}. Only supplier declaration available, requires review."
        
        else:  # PASS, FAIL, WARNING, REVIEW
            final_decision = decision
            reasoning = f"Rule matched: {rule_result['rule_name']}. {rule_result.get('notes', '')}"
            
            if rule_result.get('remediation'):
                reasoning += f" Remediation: {rule_result['remediation']}"
        
        return {
            'decision': final_decision,
            'reasoning': reasoning
        }
    
    def _apply_ml_decision(self, sku_id, claim_id, claim_text, ml_result):
        """Apply ML-based decision logic"""
        if not ml_result['available']:
            return {
                'decision': 'REVIEW',
                'reasoning': 'ML classifier not available. Manual review required.'
            }
        
        decision = ml_result['prediction']
        confidence = ml_result['confidence']
        
        reasoning = f"ML classification: {decision} (confidence: {confidence:.2f}). "
        
        if confidence < 0.6:
            decision = 'REVIEW'
            reasoning += "Low confidence score, manual review recommended."
        elif decision == 'PASS' and confidence > 0.8:
            reasoning += "High confidence positive classification."
        elif decision == 'FAIL' and confidence > 0.8:
            reasoning += "High confidence negative classification."
        else:
            reasoning += "Moderate confidence classification."
        
        return {
            'decision': decision,
            'reasoning': reasoning
        }
    
    def _check_certificates(self, sku_id, claim_text, required_cert_types):
        """Check if required certificates are available for the claim"""
        # Get SKU certificate files
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT certificate_files FROM skus WHERE id = ?
        ''', (sku_id,))
        
        result = cursor.fetchone()
        if not result or not result[0]:
            conn.close()
            return {
                'checked': True,
                'status': 'MISSING',
                'found_certs': [],
                'has_third_party': False
            }
        
        certificate_files = json.loads(result[0])
        conn.close()
        
        if not required_cert_types:
            return {
                'checked': False,
                'status': 'NOT_REQUIRED',
                'found_certs': certificate_files,
                'has_third_party': self._has_third_party_certs(certificate_files)
            }
        
        # Check if any of the available certificates match the required types
        found_certs = []
        for cert_file in certificate_files:
            cert_type = self._determine_certificate_type(cert_file)
            if cert_type in required_cert_types:
                found_certs.append(cert_file)
        
        status = 'FOUND' if found_certs else 'MISSING'
        has_third_party = self._has_third_party_certs(certificate_files)
        
        return {
            'checked': True,
            'status': status,
            'found_certs': found_certs,
            'has_third_party': has_third_party
        }
    
    def _determine_certificate_type(self, cert_file):
        """Determine certificate type from filename"""
        filename_lower = cert_file.lower()
        
        if 'lab' in filename_lower and 'nutrition' in filename_lower:
            return "Lab Nutrition Analysis"
        elif 'lab' in filename_lower and 'allergen' in filename_lower:
            return "Allergen Lab Test"
        elif 'soil' in filename_lower and 'association' in filename_lower:
            return "Soil Association Certification"
        elif 'organic' in filename_lower:
            return "Organic Certification"
        elif 'fairtrade' in filename_lower:
            return "Fairtrade License"
        elif 'carbon' in filename_lower:
            return "Carbon Neutral Audit"
        elif 'third' in filename_lower and 'party' in filename_lower:
            return "Third-Party Audit"
        elif 'supplier' in filename_lower and 'declaration' in filename_lower:
            return "Supplier Declaration"
        elif 'gmo' in filename_lower:
            return "GMO Test Report"
        elif 'vegan' in filename_lower:
            return "Vegan Conformity Statement"
        else:
            return "Other Certificate"
    
    def _has_third_party_certs(self, certificate_files):
        """Check if any certificates are from third parties (not supplier declarations)"""
        for cert_file in certificate_files:
            filename_lower = cert_file.lower()
            if 'supplier' not in filename_lower and 'declaration' not in filename_lower:
                return True
        return False
    
    def _create_verification_task(self, sku_id, decision_id, decision, certificate_result):
        """Create a task for retail assistant based on verification result"""
        task_type = 'review'
        description = f"Claim verification result: {decision['decision']}. "
        
        if decision['decision'] == 'FAIL':
            task_type = 'reject'
            description += "Claim failed verification and should be rejected."
        elif decision['decision'] == 'WARNING':
            task_type = 'modify'
            description += "Claim requires modification or additional evidence."
        elif certificate_result['status'] == 'MISSING':
            task_type = 'request_evidence'
            description += "Required certificates are missing. Request evidence from supplier."
        else:
            description += "Manual review required for final approval."
        
        description += f" Reasoning: {decision['reasoning']}"
        
        self.db.create_task(sku_id, decision_id, task_type, description)
    
    def get_verification_summary(self):
        """Get summary of verification results"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT decision, COUNT(*) as count
            FROM decisions
            GROUP BY decision
        ''')
        
        decision_counts = dict(cursor.fetchall())
        
        cursor.execute('''
            SELECT COUNT(*) as total_claims
            FROM claims
        ''')
        
        total_claims = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) as open_tasks
            FROM tasks
            WHERE status = 'open'
        ''')
        
        open_tasks = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_claims': total_claims,
            'decision_counts': decision_counts,
            'open_tasks': open_tasks,
            'verification_rate': len(decision_counts) / max(total_claims, 1) * 100
        }
