import json
from datetime import datetime, timedelta
from database.schema import ShelfTruthDB

class GovernanceAgent:
    """
    Governance Agent
    
    Provides governance, oversight, and audit logging across all agents.
    Manages the multi-agent dashboard and ensures traceability and transparency.
    """
    
    def __init__(self, db: ShelfTruthDB):
        self.db = db
        self.agent_name = "Governance Agent"
    
    def get_dashboard_data(self):
        """
        Get comprehensive dashboard data for multi-agent oversight
        
        Returns:
            Dictionary with all dashboard metrics and data
        """
        self.db.log_audit(self.agent_name, "DASHBOARD_DATA_REQUESTED", None, {
            "timestamp": datetime.now().isoformat()
        })
        
        dashboard_data = {
            'overview': self._get_overview_metrics(),
            'sku_status': self._get_sku_status_summary(),
            'claims_analysis': self._get_claims_analysis(),
            'verification_results': self._get_verification_results(),
            'task_management': self._get_task_management_data(),
            'certificate_status': self._get_certificate_status(),
            'agent_activity': self._get_agent_activity(),
            'audit_trail': self._get_recent_audit_trail(),
            'compliance_score': self._calculate_compliance_score()
        }
        
        return dashboard_data
    
    def _get_overview_metrics(self):
        """Get high-level overview metrics"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Total SKUs
        cursor.execute('SELECT COUNT(*) FROM skus')
        total_skus = cursor.fetchone()[0]
        
        # Total claims
        cursor.execute('SELECT COUNT(*) FROM claims')
        total_claims = cursor.fetchone()[0]
        
        # Total decisions
        cursor.execute('SELECT COUNT(*) FROM decisions')
        total_decisions = cursor.fetchone()[0]
        
        # Open tasks
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE status = "open"')
        open_tasks = cursor.fetchone()[0]
        
        # Completed tasks
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE status = "completed"')
        completed_tasks = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_skus': total_skus,
            'total_claims': total_claims,
            'total_decisions': total_decisions,
            'open_tasks': open_tasks,
            'completed_tasks': completed_tasks,
            'task_completion_rate': (completed_tasks / max(completed_tasks + open_tasks, 1)) * 100
        }
    
    def _get_sku_status_summary(self):
        """Get summary of SKU processing status"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                s.id, s.sku_code, s.name,
                COUNT(c.id) as claim_count,
                COUNT(d.id) as decision_count,
                COUNT(CASE WHEN t.status = 'open' THEN 1 END) as open_tasks,
                COUNT(CASE WHEN d.decision = 'PASS' THEN 1 END) as passed_claims,
                COUNT(CASE WHEN d.decision = 'FAIL' THEN 1 END) as failed_claims,
                COUNT(CASE WHEN d.decision = 'REVIEW' THEN 1 END) as review_claims
            FROM skus s
            LEFT JOIN claims c ON s.id = c.sku_id
            LEFT JOIN decisions d ON c.id = d.claim_id
            LEFT JOIN tasks t ON d.id = t.decision_id
            GROUP BY s.id, s.sku_code, s.name
            ORDER BY s.sku_code
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        sku_status = []
        for result in results:
            status = 'processing'
            if result[4] > 0:  # Has decisions
                if result[6] == 0:  # No open tasks
                    if result[8] == 0:  # No failed claims
                        status = 'approved'
                    else:
                        status = 'rejected'
                else:
                    status = 'pending_review'
            
            sku_status.append({
                'sku_id': result[0],
                'sku_code': result[1],
                'name': result[2],
                'claim_count': result[3],
                'decision_count': result[4],
                'open_tasks': result[5],
                'passed_claims': result[6],
                'failed_claims': result[7],
                'review_claims': result[8],
                'status': status
            })
        
        return sku_status
    
    def _get_claims_analysis(self):
        """Analyze claims across all SKUs"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Claims by source
        cursor.execute('''
            SELECT source, COUNT(*) as count
            FROM claims
            GROUP BY source
        ''')
        claims_by_source = dict(cursor.fetchall())
        
        # Most common claims
        cursor.execute('''
            SELECT claim_text, COUNT(*) as count
            FROM claims
            GROUP BY claim_text
            ORDER BY count DESC
            LIMIT 10
        ''')
        common_claims = cursor.fetchall()
        
        # Claims confidence distribution
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN confidence_score >= 0.9 THEN 'High (0.9+)'
                    WHEN confidence_score >= 0.7 THEN 'Medium (0.7-0.9)'
                    ELSE 'Low (<0.7)'
                END as confidence_range,
                COUNT(*) as count
            FROM claims
            GROUP BY confidence_range
        ''')
        confidence_distribution = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'claims_by_source': claims_by_source,
            'common_claims': [{'claim': claim, 'count': count} for claim, count in common_claims],
            'confidence_distribution': confidence_distribution
        }
    
    def _get_verification_results(self):
        """Get verification results summary"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Decisions by type
        cursor.execute('''
            SELECT decision, COUNT(*) as count
            FROM decisions
            GROUP BY decision
        ''')
        decisions_by_type = dict(cursor.fetchall())
        
        # Rule-based vs ML-based decisions
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN rule_matched IS NOT NULL THEN 'Rule-based'
                    WHEN ml_confidence IS NOT NULL THEN 'ML-based'
                    ELSE 'Manual'
                END as decision_method,
                COUNT(*) as count
            FROM decisions
            GROUP BY decision_method
        ''')
        decisions_by_method = dict(cursor.fetchall())
        
        # Certificate status distribution
        cursor.execute('''
            SELECT certificate_status, COUNT(*) as count
            FROM decisions
            WHERE certificate_status IS NOT NULL
            GROUP BY certificate_status
        ''')
        certificate_status_dist = dict(cursor.fetchall())
        
        # ML confidence distribution
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN ml_confidence >= 0.8 THEN 'High (0.8+)'
                    WHEN ml_confidence >= 0.6 THEN 'Medium (0.6-0.8)'
                    WHEN ml_confidence IS NOT NULL THEN 'Low (<0.6)'
                    ELSE 'N/A'
                END as confidence_range,
                COUNT(*) as count
            FROM decisions
            GROUP BY confidence_range
        ''')
        ml_confidence_dist = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'decisions_by_type': decisions_by_type,
            'decisions_by_method': decisions_by_method,
            'certificate_status_distribution': certificate_status_dist,
            'ml_confidence_distribution': ml_confidence_dist
        }
    
    def _get_task_management_data(self):
        """Get task management overview"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Tasks by type
        cursor.execute('''
            SELECT task_type, COUNT(*) as count
            FROM tasks
            GROUP BY task_type
        ''')
        tasks_by_type = dict(cursor.fetchall())
        
        # Tasks by status
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM tasks
            GROUP BY status
        ''')
        tasks_by_status = dict(cursor.fetchall())
        
        # Average task completion time
        cursor.execute('''
            SELECT AVG(
                CASE 
                    WHEN completed_at IS NOT NULL 
                    THEN (julianday(completed_at) - julianday(created_at)) * 24 * 60
                    ELSE NULL
                END
            ) as avg_completion_minutes
            FROM tasks
            WHERE status = 'completed'
        ''')
        avg_completion_time = cursor.fetchone()[0] or 0
        
        # Recent task activity
        cursor.execute('''
            SELECT 
                t.id, t.task_type, t.status, t.created_at,
                s.sku_code, c.claim_text
            FROM tasks t
            JOIN skus s ON t.sku_id = s.id
            JOIN decisions d ON t.decision_id = d.id
            JOIN claims c ON d.claim_id = c.id
            ORDER BY t.created_at DESC
            LIMIT 10
        ''')
        recent_tasks = cursor.fetchall()
        
        conn.close()
        
        return {
            'tasks_by_type': tasks_by_type,
            'tasks_by_status': tasks_by_status,
            'avg_completion_time_minutes': round(avg_completion_time, 2),
            'recent_tasks': [
                {
                    'task_id': task[0],
                    'task_type': task[1],
                    'status': task[2],
                    'created_at': task[3],
                    'sku_code': task[4],
                    'claim_text': task[5]
                }
                for task in recent_tasks
            ]
        }
    
    def _get_certificate_status(self):
        """Get certificate validation status"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT validation_status, COUNT(*) as count
            FROM certificate_validations
            GROUP BY validation_status
        ''')
        validation_status = dict(cursor.fetchall())
        
        cursor.execute('''
            SELECT certificate_type, COUNT(*) as count
            FROM certificate_validations
            GROUP BY certificate_type
            ORDER BY count DESC
        ''')
        certificate_types = cursor.fetchall()
        
        conn.close()
        
        return {
            'validation_status': validation_status,
            'certificate_types': [{'type': cert_type, 'count': count} for cert_type, count in certificate_types]
        }
    
    def _get_agent_activity(self):
        """Get activity summary for each agent"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Activity by agent
        cursor.execute('''
            SELECT agent_name, COUNT(*) as activity_count
            FROM audit_log
            GROUP BY agent_name
            ORDER BY activity_count DESC
        ''')
        agent_activity = cursor.fetchall()
        
        # Recent activity by agent
        cursor.execute('''
            SELECT agent_name, action, COUNT(*) as count
            FROM audit_log
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY agent_name, action
            ORDER BY agent_name, count DESC
        ''')
        recent_activity = cursor.fetchall()
        
        conn.close()
        
        # Group recent activity by agent
        recent_by_agent = {}
        for agent, action, count in recent_activity:
            if agent not in recent_by_agent:
                recent_by_agent[agent] = []
            recent_by_agent[agent].append({'action': action, 'count': count})
        
        return {
            'total_activity': [{'agent': agent, 'count': count} for agent, count in agent_activity],
            'recent_activity': recent_by_agent
        }
    
    def _get_recent_audit_trail(self, limit=50):
        """Get recent audit trail entries"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT agent_name, action, sku_id, details, timestamp
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        audit_trail = []
        for result in results:
            details = None
            if result[3]:
                try:
                    details = json.loads(result[3])
                except:
                    details = result[3]
            
            audit_trail.append({
                'agent_name': result[0],
                'action': result[1],
                'sku_id': result[2],
                'details': details,
                'timestamp': result[4]
            })
        
        return audit_trail
    
    def _calculate_compliance_score(self):
        """Calculate overall compliance score"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get decision counts
        cursor.execute('''
            SELECT decision, COUNT(*) as count
            FROM decisions
            GROUP BY decision
        ''')
        decision_counts = dict(cursor.fetchall())
        
        # Get certificate validation counts
        cursor.execute('''
            SELECT validation_status, COUNT(*) as count
            FROM certificate_validations
            GROUP BY validation_status
        ''')
        cert_counts = dict(cursor.fetchall())
        
        conn.close()
        
        # Calculate scores
        total_decisions = sum(decision_counts.values())
        if total_decisions == 0:
            return {'score': 0, 'grade': 'N/A', 'breakdown': {}}
        
        # Scoring weights
        decision_weights = {
            'PASS': 1.0,
            'WARNING': 0.7,
            'REVIEW': 0.5,
            'FAIL': 0.0,
            'SUPERSEDED': 0.5
        }
        
        # Calculate decision score
        decision_score = sum(
            decision_counts.get(decision, 0) * weight
            for decision, weight in decision_weights.items()
        ) / total_decisions
        
        # Calculate certificate score
        total_certs = sum(cert_counts.values())
        cert_score = 1.0
        if total_certs > 0:
            valid_certs = cert_counts.get('VALID', 0)
            cert_score = valid_certs / total_certs
        
        # Overall compliance score (weighted average)
        overall_score = (decision_score * 0.7 + cert_score * 0.3) * 100
        
        # Determine grade
        if overall_score >= 90:
            grade = 'A'
        elif overall_score >= 80:
            grade = 'B'
        elif overall_score >= 70:
            grade = 'C'
        elif overall_score >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        return {
            'score': round(overall_score, 1),
            'grade': grade,
            'breakdown': {
                'decision_score': round(decision_score * 100, 1),
                'certificate_score': round(cert_score * 100, 1),
                'total_decisions': total_decisions,
                'total_certificates': total_certs
            }
        }
    
    def refresh_dashboard(self):
        """Refresh dashboard data without touching original input files"""
        self.db.log_audit(self.agent_name, "DASHBOARD_REFRESH_REQUESTED", None, {
            "timestamp": datetime.now().isoformat()
        })
        
        # Get fresh dashboard data
        dashboard_data = self.get_dashboard_data()
        
        self.db.log_audit(self.agent_name, "DASHBOARD_REFRESH_COMPLETED", None, {
            "timestamp": datetime.now().isoformat(),
            "data_points": len(dashboard_data)
        })
        
        return dashboard_data
    
    def generate_compliance_report(self, sku_id=None):
        """Generate detailed compliance report"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if sku_id:
            # SKU-specific report
            cursor.execute('''
                SELECT 
                    s.sku_code, s.name, s.description,
                    c.claim_text, c.source,
                    d.decision, d.reasoning, d.certificate_status,
                    t.task_type, t.status as task_status
                FROM skus s
                LEFT JOIN claims c ON s.id = c.sku_id
                LEFT JOIN decisions d ON c.id = d.claim_id
                LEFT JOIN tasks t ON d.id = t.decision_id
                WHERE s.id = ?
                ORDER BY c.id, d.id
            ''', (sku_id,))
        else:
            # Full compliance report
            cursor.execute('''
                SELECT 
                    s.sku_code, s.name, s.description,
                    c.claim_text, c.source,
                    d.decision, d.reasoning, d.certificate_status,
                    t.task_type, t.status as task_status
                FROM skus s
                LEFT JOIN claims c ON s.id = c.sku_id
                LEFT JOIN decisions d ON c.id = d.claim_id
                LEFT JOIN tasks t ON d.id = t.decision_id
                ORDER BY s.sku_code, c.id, d.id
            ''')
        
        results = cursor.fetchall()
        conn.close()
        
        # Process results into report format
        report = {
            'generated_at': datetime.now().isoformat(),
            'scope': 'single_sku' if sku_id else 'all_skus',
            'skus': {}
        }
        
        for result in results:
            sku_code = result[0]
            if sku_code not in report['skus']:
                report['skus'][sku_code] = {
                    'name': result[1],
                    'description': result[2],
                    'claims': []
                }
            
            if result[3]:  # Has claim
                report['skus'][sku_code]['claims'].append({
                    'claim_text': result[3],
                    'source': result[4],
                    'decision': result[5],
                    'reasoning': result[6],
                    'certificate_status': result[7],
                    'task_type': result[8],
                    'task_status': result[9]
                })
        
        self.db.log_audit(self.agent_name, "COMPLIANCE_REPORT_GENERATED", sku_id, {
            "scope": report['scope'],
            "sku_count": len(report['skus'])
        })
        
        return report
