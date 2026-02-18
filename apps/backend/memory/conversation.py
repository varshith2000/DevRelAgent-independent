"""
Conversation Memory — Short-term chat history management

TODO: Phase 1 implementation
"""

from typing import List, Dict, Optional
from datetime import datetime


class ConversationMemory:
    """
    Manages short-term conversation history within a session.
    
    TODO: Implement with sliding window and summary compression.
    """

    def __init__(self, max_messages: int = 50):
        self.messages: List[Dict[str, str]] = []
        self.max_messages = max_messages

    def add(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_recent(self, n: int = 10) -> List[Dict[str, str]]:
        return self.messages[-n:]

    def clear(self):
        self.messages = []
