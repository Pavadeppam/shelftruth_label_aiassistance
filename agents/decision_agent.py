import json
from datetime import datetime
from database.schema import ShelfTruthDB

class DecisionAgent:
    """
    Decision & Feedback Agent
    
    Handles human-in-the-loop finalization through the Retail Assistant UI.
    Manages task completion and feedback processing.
    """
    
    def __init__(self, db: ShelfTruthDB):
        self.db = db
        self.agent_name = "Decision Agent"
    
    def get_pending_tasks(self, task_type=None, limit=50):
        """
        Get pending tasks for retail assistant review
        
        Args:
            task_type: Filter by specific task type ('approve', 'reject', 'request_evidence', 'modify')
            limit: Maximum number of tasks to return
        
        Returns:
            List of pending tasks with context
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                t.id, t.task_type, t.description, t.created_at,
                s.id as sku_id, s.sku_code, s.name as sku_name,
                c.id as claim_id, c.claim_text, c.source,
                d.id as decision_id, d.decision, d.reasoning, d.certificate_status
            FROM tasks t
            JOIN skus s ON t.sku_id = s.id
            JOIN decisions d ON t.decision_id = d.id
            JOIN claims c ON d.claim_id = c.id
            WHERE t.status = 'open'
        '''
        
        params = []
        if task_type:
            query += ' AND t.task_type = ?'
            params.append(task_type)
        
        query += ' ORDER BY t.created_at ASC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        tasks = []
        for result in results:
            tasks.append({
                'task_id': result[0],
                'task_type': result[1],
                'description': result[2],
                'created_at': result[3],
                'sku': {
                    'id': result[4],
                    'sku_code': result[5],
                    'name': result[6]
                },
                'claim': {
                    'id': result[7],
                    'text': result[8],
                    'source': result[9]
                },
                'decision': {
                    'id': result[10],
                    'decision': result[11],
                    'reasoning': result[12],
                    'certificate_status': result[13]
                }
            })
        
        self.db.log_audit(self.agent_name, "TASKS_RETRIEVED", None, {
            "task_count": len(tasks),
            "task_type_filter": task_type
        })
        
        return tasks
    
    def process_task_decision(self, task_id, action, reasoning=None, additional_data=None):
        """
        Process a decision made by the retail assistant
        
        Args:
            task_id: ID of the task being processed
            action: Action taken ('approve', 'reject', 'request_evidence', 'modify', 'escalate')
            reasoning: Human reasoning for the decision
            additional_data: Any additional context or requirements
        
        Returns:
            Result of the decision processing
        """
        # Get task details
        task = self._get_task_details(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        self.db.log_audit(self.agent_name, "TASK_DECISION_STARTED", task['sku_id'], {
            "task_id": task_id,
            "action": action,
            "task_type": task['task_type']
        })
        
        try:
            result = self._execute_task_action(task, action, reasoning, additional_data)
            
            # Mark task as completed
            action_description = f"Action: {action}"
            if reasoning:
                action_description += f". Reasoning: {reasoning}"
            
            self.db.complete_task(task_id, action_description)
            
            self.db.log_audit(self.agent_name, "TASK_DECISION_COMPLETED", task['sku_id'], {
                "task_id": task_id,
                "action": action,
                "result": result
            })
            
            return result
            
        except Exception as e:
            self.db.log_audit(self.agent_name, "TASK_DECISION_ERROR", task['sku_id'], {
                "task_id": task_id,
                "action": action,
                "error": str(e)
            })
            raise e
    
    def _get_task_details(self, task_id):
        """Get detailed information about a task"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                t.id, t.task_type, t.description, t.sku_id, t.decision_id,
                s.sku_code, s.name,
                c.id as claim_id, c.claim_text,
                d.decision, d.reasoning
            FROM tasks t
            JOIN skus s ON t.sku_id = s.id
            JOIN decisions d ON t.decision_id = d.id
            JOIN claims c ON d.claim_id = c.id
            WHERE t.id = ? AND t.status = 'open'
        ''', (task_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'task_id': result[0],
                'task_type': result[1],
                'description': result[2],
                'sku_id': result[3],
                'decision_id': result[4],
                'sku_code': result[5],
                'sku_name': result[6],
                'claim_id': result[7],
                'claim_text': result[8],
                'decision': result[9],
                'reasoning': result[10]
            }
        
        return None
    
    def _execute_task_action(self, task, action, reasoning, additional_data):
        """Execute the specific action for a task"""
        if action == 'approve':
            return self._approve_claim(task, reasoning)
        elif action == 'reject':
            return self._reject_claim(task, reasoning)
        elif action == 'request_evidence':
            return self._request_evidence(task, reasoning, additional_data)
        elif action == 'modify':
            return self._modify_claim(task, reasoning, additional_data)
        elif action == 'escalate':
            return self._escalate_task(task, reasoning)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def _approve_claim(self, task, reasoning):
        """Approve a claim"""
        # Update decision to PASS
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE decisions 
            SET decision = 'PASS', reasoning = ?
            WHERE id = ?
        ''', (f"Approved by Retail Assistant. {reasoning or ''}", task['decision_id']))
        
        conn.commit()
        conn.close()
        
        return {
            'action': 'approved',
            'claim_text': task['claim_text'],
            'sku_code': task['sku_code'],
            'final_decision': 'PASS'
        }
    
    def _reject_claim(self, task, reasoning):
        """Reject a claim"""
        # Update decision to FAIL
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE decisions 
            SET decision = 'FAIL', reasoning = ?
            WHERE id = ?
        ''', (f"Rejected by Retail Assistant. {reasoning or ''}", task['decision_id']))
        
        conn.commit()
        conn.close()
        
        return {
            'action': 'rejected',
            'claim_text': task['claim_text'],
            'sku_code': task['sku_code'],
            'final_decision': 'FAIL'
        }
    
    def _request_evidence(self, task, reasoning, additional_data):
        """Request additional evidence from supplier"""
        # Create a new task for supplier follow-up
        evidence_requirements = additional_data.get('evidence_requirements', []) if additional_data else []
        
        description = f"Evidence requested for claim '{task['claim_text']}'. "
        if reasoning:
            description += f"Reason: {reasoning}. "
        if evidence_requirements:
            description += f"Required evidence: {', '.join(evidence_requirements)}"
        
        # Create supplier communication task
        supplier_task_id = self.db.create_task(
            task['sku_id'], 
            task['decision_id'], 
            'supplier_communication', 
            description
        )
        
        return {
            'action': 'evidence_requested',
            'claim_text': task['claim_text'],
            'sku_code': task['sku_code'],
            'evidence_requirements': evidence_requirements,
            'supplier_task_id': supplier_task_id
        }
    
    def _modify_claim(self, task, reasoning, additional_data):
        """Modify a claim"""
        new_claim_text = additional_data.get('new_claim_text') if additional_data else None
        
        if new_claim_text:
            # Insert new claim
            new_claim_id = self.db.insert_claim(
                task['sku_id'],
                new_claim_text,
                'retail_assistant_modified',
                1.0
            )
            
            # Mark original claim as superseded
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE decisions 
                SET decision = 'SUPERSEDED', reasoning = ?
                WHERE id = ?
            ''', (f"Modified by Retail Assistant. New claim: {new_claim_text}. {reasoning or ''}", task['decision_id']))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'modified',
                'original_claim': task['claim_text'],
                'new_claim': new_claim_text,
                'sku_code': task['sku_code'],
                'new_claim_id': new_claim_id
            }
        else:
            raise ValueError("New claim text required for modification")
    
    def _escalate_task(self, task, reasoning):
        """Escalate task to higher authority"""
        # Create escalation task
        description = f"Escalated from Retail Assistant. Original claim: '{task['claim_text']}'. "
        if reasoning:
            description += f"Escalation reason: {reasoning}"
        
        escalation_task_id = self.db.create_task(
            task['sku_id'],
            task['decision_id'],
            'escalation',
            description
        )
        
        return {
            'action': 'escalated',
            'claim_text': task['claim_text'],
            'sku_code': task['sku_code'],
            'escalation_task_id': escalation_task_id
        }
    
    def get_task_statistics(self):
        """Get statistics about task processing"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get task counts by status
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM tasks
            GROUP BY status
        ''')
        status_counts = dict(cursor.fetchall())
        
        # Get task counts by type
        cursor.execute('''
            SELECT task_type, COUNT(*) as count
            FROM tasks
            GROUP BY task_type
        ''')
        type_counts = dict(cursor.fetchall())
        
        # Get completion rate
        cursor.execute('''
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
            FROM tasks
        ''')
        result = cursor.fetchone()
        total_tasks = result[0]
        completed_tasks = result[1]
        completion_rate = (completed_tasks / max(total_tasks, 1)) * 100
        
        conn.close()
        
        return {
            'status_counts': status_counts,
            'type_counts': type_counts,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': completion_rate
        }
    
    def bulk_approve_tasks(self, task_ids, reasoning="Bulk approval"):
        """Approve multiple tasks at once"""
        results = []
        
        for task_id in task_ids:
            try:
                result = self.process_task_decision(task_id, 'approve', reasoning)
                results.append({'task_id': task_id, 'success': True, 'result': result})
            except Exception as e:
                results.append({'task_id': task_id, 'success': False, 'error': str(e)})
        
        self.db.log_audit(self.agent_name, "BULK_APPROVAL", None, {
            "task_count": len(task_ids),
            "successful": sum(1 for r in results if r['success']),
            "failed": sum(1 for r in results if not r['success'])
        })
        
        return results
    
    def get_decision_history(self, sku_id=None, limit=100):
        """Get history of decisions made"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                t.id, t.task_type, t.action_taken, t.completed_at,
                s.sku_code, s.name,
                c.claim_text,
                d.decision
            FROM tasks t
            JOIN skus s ON t.sku_id = s.id
            JOIN decisions d ON t.decision_id = d.id
            JOIN claims c ON d.claim_id = c.id
            WHERE t.status = 'completed'
        '''
        
        params = []
        if sku_id:
            query += ' AND t.sku_id = ?'
            params.append(sku_id)
        
        query += ' ORDER BY t.completed_at DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        history = []
        for result in results:
            history.append({
                'task_id': result[0],
                'task_type': result[1],
                'action_taken': result[2],
                'completed_at': result[3],
                'sku_code': result[4],
                'sku_name': result[5],
                'claim_text': result[6],
                'final_decision': result[7]
            })
        
        return history
