from datetime import datetime

class TaskBrief:
    def __init__(self, task_description, role, context=None):
        self.task_description = task_description
        self.role = role
        self.context = context or {}
        self.created_at = datetime.now().isoformat()
        
    def to_string(self):
        return f"""
---
## TASK BRIEF
**Role needed**: {self.role}
**Objective**: {self.task_description}
**Context**: {self.context}
**Timestamp**: {self.created_at}
---
"""
