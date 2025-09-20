import os
import re
import json
from datetime import datetime
from database.schema import ShelfTruthDB

# PIL is required for EasyOCR path
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Pure-Python PDF text extraction (no OS deps)
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

# Pure-Python OCR pipeline using PyMuPDF (render) + EasyOCR (OCR)
try:
    import fitz  # PyMuPDF
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

class ClaimExtractionAgent:
    """
    Claim Extraction Agent (OCR + NLP)
    
    Extracts claims from SKU descriptions and product labels using OCR and NLP techniques.
    """
    
    def __init__(self, db: ShelfTruthDB):
        self.db = db
        self.agent_name = "Claim Extraction Agent"
        
        # Common claim patterns for regex matching
        self.claim_patterns = [
            r'\b(?:100%\s*)?organic\b',
            r'\bhigh\s+in\s+fi[bv]re\b',
            r'\blow\s+fat\b',
            r'\bgluten[-\s]*free\b',
            r'\b100%\s*natural\b',
            r'\bno\s+msg\b',
            r'\bfda\s+approved\b',
            r'\bboosts?\s+immunity\b',
            r'\bsugar[-\s]*free\b',
            r'\b100%\s*vegan\b',
            r'\bgmo[-\s]*free\b',
            r'\bfairtrade\s+certified\b',
            r'\bcarbon\s+neutral\b',
            r'\bsuitable\s+for\s+vegans?\b',
            r'\bnon[-\s]*gmo\b',
            r'\bno\s+artificial\s+(?:colors?|flavou?rs?|preservatives?)\b',
            r'\brich\s+in\s+(?:protein|vitamins?|minerals?)\b',
            r'\bwhole\s+grain\b',
            r'\bno\s+added\s+sugar\b',
            r'\bkosher\b',
            r'\bhalal\b'
        ]
    
    def extract_claims_from_skus(self, sku_ids=None):
        """
        Extract claims from all SKUs or specific SKU IDs
        
        Args:
            sku_ids: List of SKU IDs to process, or None for all SKUs
        
        Returns:
            Dictionary with extraction results
        """
        if sku_ids is None:
            # Get all SKUs from database
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM skus')
            sku_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
        
        self.db.log_audit(self.agent_name, "EXTRACTION_STARTED", None, {
            "sku_count": len(sku_ids)
        })
        
        extraction_results = {
            'processed_skus': 0,
            'total_claims_extracted': 0,
            'ocr_successful': 0,
            'ocr_failed': 0,
            'errors': []
        }
        
        for sku_id in sku_ids:
            try:
                result = self._extract_claims_for_sku(sku_id)
                extraction_results['processed_skus'] += 1
                extraction_results['total_claims_extracted'] += result['claims_count']
                
                if result['ocr_success']:
                    extraction_results['ocr_successful'] += 1
                else:
                    extraction_results['ocr_failed'] += 1
                    
            except Exception as e:
                extraction_results['errors'].append({
                    'sku_id': sku_id,
                    'error': str(e)
                })
        
        self.db.log_audit(self.agent_name, "EXTRACTION_COMPLETED", None, extraction_results)
        
        return extraction_results
    
    def _extract_claims_for_sku(self, sku_id):
        """Extract claims for a single SKU"""
        # Get SKU data
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sku_code, name, description, label_file_path
            FROM skus WHERE id = ?
        ''', (sku_id,))
        
        sku_data = cursor.fetchone()
        conn.close()
        
        if not sku_data:
            raise ValueError(f"SKU with ID {sku_id} not found")
        
        sku_code, name, description, label_file_path = sku_data
        
        result = {
            'sku_id': sku_id,
            'sku_code': sku_code,
            'claims_count': 0,
            'ocr_success': False,
            'extracted_claims': []
        }
        
        # Extract claims from description
        if description:
            description_claims = self._extract_claims_from_text(description)
            for claim in description_claims:
                claim_id = self.db.insert_claim(sku_id, claim, 'description', 0.9)
                result['extracted_claims'].append({
                    'claim_id': claim_id,
                    'text': claim,
                    'source': 'description'
                })
                result['claims_count'] += 1
        
        # Extract claims from label using OCR
        if label_file_path and os.path.exists(label_file_path):
            try:
                ocr_claims = self._extract_claims_from_label_ocr(label_file_path)
                result['ocr_success'] = True
                
                for claim, confidence in ocr_claims:
                    claim_id = self.db.insert_claim(sku_id, claim, 'label_ocr', confidence)
                    result['extracted_claims'].append({
                        'claim_id': claim_id,
                        'text': claim,
                        'source': 'label_ocr',
                        'confidence': confidence
                    })
                    result['claims_count'] += 1
                    
            except Exception as e:
                self.db.log_audit(self.agent_name, "OCR_ERROR", sku_id, {
                    "label_file": label_file_path,
                    "error": str(e)
                })
        
        self.db.log_audit(self.agent_name, "CLAIMS_EXTRACTED", sku_id, {
            "claims_count": result['claims_count'],
            "ocr_success": result['ocr_success']
        })
        
        return result
    
    def _extract_claims_from_text(self, text):
        """Extract claims from text using regex patterns"""
        claims = []
        text_lower = text.lower()
        
        for pattern in self.claim_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                # Clean up the match and convert to proper case
                claim = self._normalize_claim(match)
                if claim and claim not in claims:
                    claims.append(claim)
        
        # Also look for explicit claims in the original text
        # Split by common delimiters and check each part
        parts = re.split(r'[,;]', text)
        for part in parts:
            part = part.strip()
            if self._is_likely_claim(part):
                normalized = self._normalize_claim(part)
                if normalized and normalized not in claims:
                    claims.append(normalized)
        
        return claims
    
    def _extract_claims_from_label_ocr(self, label_file_path):
        """Extract claims from label PDF using layered approaches without OS-level deps.
        Order of attempts:
        1) pdfminer.six text extraction (works for text-based PDFs)
        2) PyMuPDF render + EasyOCR (pip-installable OCR for scanned/image PDFs)
        """
        claims_with_confidence = []

        # 1) Try pdfminer (text-based PDFs)
        if PDFMINER_AVAILABLE:
            try:
                text = pdfminer_extract_text(label_file_path) or ""
                text_clean = text.strip()
                if len(text_clean) >= 10:  # likely text-based
                    claims = self._extract_claims_from_text(text)
                    for claim in claims:
                        confidence = self._calculate_ocr_confidence(claim, text)
                        claims_with_confidence.append((claim, max(0.6, confidence)))
                    if claims_with_confidence:
                        return claims_with_confidence
            except Exception as e:
                # Continue to next method
                self.db.log_audit(self.agent_name, "PDFMINER_ERROR", None, {"file": label_file_path, "error": str(e)})

        # 2) Try EasyOCR on images rendered by PyMuPDF
        if EASYOCR_AVAILABLE:
            try:
                reader = easyocr.Reader(['en'], gpu=False)
                doc = fitz.open(label_file_path)
                aggregated_text = ""
                for page in doc:
                    pix = page.get_pixmap(dpi=180)
                    img_bytes = pix.tobytes("png")
                    # Convert bytes to numpy RGB array using PIL (no OpenCV dependency)
                    from io import BytesIO
                    import numpy as np
                    pil_img = Image.open(BytesIO(img_bytes)).convert('RGB')
                    img = np.array(pil_img)
                    result = reader.readtext(img, detail=0, paragraph=True)
                    page_text = "\n".join(result)
                    aggregated_text += "\n" + page_text
                doc.close()
                claims = self._extract_claims_from_text(aggregated_text)
                for claim in claims:
                    confidence = self._calculate_ocr_confidence(claim, aggregated_text)
                    claims_with_confidence.append((claim, confidence))
                if claims_with_confidence:
                    return claims_with_confidence
            except Exception as e:
                self.db.log_audit(self.agent_name, "EASYOCR_ERROR", None, {"file": label_file_path, "error": str(e)})

        # If no method available, return empty list gracefully
        return []
    
    def _normalize_claim(self, claim_text):
        """Normalize claim text to standard format"""
        # Remove extra whitespace
        claim = re.sub(r'\s+', ' ', claim_text.strip())
        
        # Capitalize first letter of each word for consistency
        claim = claim.title()
        
        # Handle special cases
        claim_mapping = {
            'Organic': 'Organic',
            'High In Fibre': 'High in fibre',
            'High In Fiber': 'High in fibre',
            'Low Fat': 'Low fat',
            'Gluten-Free': 'Gluten-free',
            'Gluten Free': 'Gluten-free',
            '100% Natural': '100% Natural',
            'No Msg': 'No MSG',
            'Fda Approved': 'FDA Approved',
            'Boosts Immunity': 'Boosts immunity',
            'Sugar-Free': 'Sugar-free',
            'Sugar Free': 'Sugar-free',
            '100% Vegan': '100% Vegan',
            'Gmo-Free': 'GMO-free',
            'Gmo Free': 'GMO-free',
            'Non-Gmo': 'GMO-free',
            'Non Gmo': 'GMO-free',
            'Fairtrade Certified': 'Fairtrade Certified',
            'Carbon Neutral': 'Carbon Neutral',
            'Suitable For Vegans': 'Suitable for vegans'
        }
        
        return claim_mapping.get(claim, claim)
    
    def _is_likely_claim(self, text):
        """Determine if text is likely to be a claim"""
        text = text.strip().lower()
        
        # Skip very short or very long text
        if len(text) < 3 or len(text) > 50:
            return False
        
        # Skip common non-claim words
        skip_words = ['ingredients', 'nutrition', 'serving', 'calories', 'weight', 'size']
        if any(word in text for word in skip_words):
            return False
        
        # Look for claim indicators
        claim_indicators = [
            'free', 'natural', 'organic', 'certified', 'approved', 'rich', 'high', 'low',
            'no', 'without', 'pure', 'fresh', 'healthy', 'nutritious', 'vegan', 'vegetarian'
        ]
        
        return any(indicator in text for indicator in claim_indicators)
    
    def _calculate_ocr_confidence(self, claim, ocr_text):
        """Calculate confidence score for OCR-extracted claim"""
        # Simple confidence calculation based on text clarity
        base_confidence = 0.7
        
        # Boost confidence if claim appears multiple times
        claim_count = ocr_text.lower().count(claim.lower())
        if claim_count > 1:
            base_confidence += 0.1
        
        # Reduce confidence for very short claims (might be OCR errors)
        if len(claim) < 5:
            base_confidence -= 0.2
        
        # Boost confidence for well-known claims
        known_claims = ['organic', 'gluten-free', 'natural', 'vegan']
        if any(known in claim.lower() for known in known_claims):
            base_confidence += 0.1
        
        return min(max(base_confidence, 0.1), 1.0)
    
    def get_claims_for_sku(self, sku_id):
        """Get all extracted claims for a specific SKU"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, claim_text, source, confidence_score, extracted_at
            FROM claims 
            WHERE sku_id = ?
            ORDER BY extracted_at DESC
        ''', (sku_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        claims = []
        for result in results:
            claims.append({
                'id': result[0],
                'claim_text': result[1],
                'source': result[2],
                'confidence_score': result[3],
                'extracted_at': result[4]
            })
        
        return claims
