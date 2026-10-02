"""
Investigation Store — Persistence for Agent Investigations

Saves and loads investigation state and observations.
Provides learning memory from past investigations.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from models.schemas import AgentObservation, InvestigationState, LearningMemory

logger = logging.getLogger(__name__)

# Storage paths (single source of truth: config.settings)
_settings = get_settings()
INVESTIGATION_STORAGE_PATH = _settings.investigation_storage_path
LEARNING_MEMORY_PATH = _settings.learning_memory_path


class InvestigationStore:
    """Manages persistence for investigations and learning memory."""

    def __init__(self):
        """Initialize the investigation store."""
        # Ensure storage directories exist
        Path(INVESTIGATION_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        Path(LEARNING_MEMORY_PATH).parent.mkdir(parents=True, exist_ok=True)

    # ============== Investigation Management ==============

    def save_investigation(self, investigation: InvestigationState) -> bool:
        """
        Save investigation to storage.

        Args:
            investigation: Investigation state to save

        Returns:
            True if saved successfully
        """
        try:
            file_path = os.path.join(INVESTIGATION_STORAGE_PATH, f"{investigation.investigation_id}.json")

            # Update timestamp
            investigation.updated_at = datetime.now().isoformat()

            # Convert to dict and save
            with open(file_path, 'w') as f:
                json.dump(investigation.dict(), f, indent=2, default=str)

            logger.info(f"Saved investigation: {investigation.investigation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save investigation {investigation.investigation_id}: {e}")
            return False

    def load_investigation(self, investigation_id: str) -> Optional[InvestigationState]:
        """
        Load investigation from storage.

        Args:
            investigation_id: Investigation ID to load

        Returns:
            Investigation state or None if not found
        """
        try:
            file_path = os.path.join(INVESTIGATION_STORAGE_PATH, f"{investigation_id}.json")

            if not os.path.exists(file_path):
                logger.warning(f"Investigation not found: {investigation_id}")
                return None

            with open(file_path, 'r') as f:
                data = json.load(f)

            investigation = InvestigationState(**data)
            logger.info(f"Loaded investigation: {investigation_id}")
            return investigation

        except Exception as e:
            logger.error(f"Failed to load investigation {investigation_id}: {e}")
            return None

    def list_investigations(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all investigations with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum number to return

        Returns:
            List of investigation summaries
        """
        try:
            investigations = []

            for file_path in Path(INVESTIGATION_STORAGE_PATH).glob("*.json"):
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)

                    # Filter by status
                    if status and data.get("status") != status:
                        continue

                    # Create summary
                    investigations.append({
                        "investigation_id": data.get("investigation_id"),
                        "title": data.get("title"),
                        "status": data.get("status"),
                        "priority": data.get("priority"),
                        "started_at": data.get("started_at"),
                        "updated_at": data.get("updated_at"),
                        "total_observations": data.get("total_observations", 0),
                        "confidence_score": data.get("confidence_score", 0.0)
                    })

                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")
                    continue

            # Sort by updated_at desc
            investigations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

            return investigations[:limit]

        except Exception as e:
            logger.error(f"Failed to list investigations: {e}")
            return []

    def delete_investigation(self, investigation_id: str) -> bool:
        """
        Delete investigation from storage.

        Args:
            investigation_id: Investigation ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            file_path = os.path.join(INVESTIGATION_STORAGE_PATH, f"{investigation_id}.json")

            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted investigation: {investigation_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete investigation {investigation_id}: {e}")
            return False

    # ============== Observation Management ==============

    def add_observation_to_investigation(
        self,
        investigation_id: str,
        observation: AgentObservation
    ) -> bool:
        """
        Add observation to existing investigation.

        Args:
            investigation_id: Investigation ID
            observation: Observation to add

        Returns:
            True if added successfully
        """
        try:
            investigation = self.load_investigation(investigation_id)
            if not investigation:
                logger.error(f"Investigation not found: {investigation_id}")
                return False

            # Add observation
            investigation.observations.append(observation)
            investigation.total_observations = len(investigation.observations)
            investigation.updated_at = datetime.now().isoformat()

            # Save updated investigation
            return self.save_investigation(investigation)

        except Exception as e:
            logger.error(f"Failed to add observation to {investigation_id}: {e}")
            return False

    # ============== Learning Memory ==============

    def save_learning_memory(self, memory: LearningMemory) -> bool:
        """
        Save learning memory entry.

        Args:
            memory: Learning memory to save

        Returns:
            True if saved successfully
        """
        try:
            # Load existing memories
            memories = self.load_all_learning_memories()

            # Add new memory
            memories.append(memory.dict())

            # Save to file
            with open(LEARNING_MEMORY_PATH, 'w') as f:
                json.dump(memories, f, indent=2, default=str)

            logger.info(f"Saved learning memory: {memory.memory_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save learning memory: {e}")
            return False

    def load_all_learning_memories(self) -> List[Dict[str, Any]]:
        """
        Load all learning memories.

        Returns:
            List of learning memory entries
        """
        try:
            if not os.path.exists(LEARNING_MEMORY_PATH):
                return []

            with open(LEARNING_MEMORY_PATH, 'r') as f:
                memories = json.load(f)

            return memories

        except Exception as e:
            logger.error(f"Failed to load learning memories: {e}")
            return []

    def find_relevant_memories(
        self,
        query: str,
        pattern_type: Optional[str] = None,
        services: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find relevant learning memories based on query.

        Args:
            query: Search query
            pattern_type: Filter by pattern type
            services: Filter by applicable services
            limit: Maximum number to return

        Returns:
            List of relevant learning memories
        """
        try:
            memories = self.load_all_learning_memories()
            query_lower = query.lower()

            relevant = []
            for memory in memories:
                # Filter by pattern type
                if pattern_type and memory.get("pattern_type") != pattern_type:
                    continue

                # Filter by services
                if services:
                    applicable_services = memory.get("applicable_services", [])
                    if not any(s in applicable_services for s in services):
                        continue

                # Search in text fields
                search_text = (
                    memory.get("pattern_name", "") + " " +
                    memory.get("pattern_description", "") + " " +
                    memory.get("solution", "")
                ).lower()

                if any(word in search_text for word in query_lower.split()):
                    # Calculate relevance score
                    score = self._calculate_relevance_score(query, memory)
                    memory["relevance_score"] = score
                    relevant.append(memory)

            # Sort by relevance and success rate
            relevant.sort(
                key=lambda m: (
                    m.get("relevance_score", 0),
                    m.get("success_rate", 0)
                ),
                reverse=True
            )

            return relevant[:limit]

        except Exception as e:
            logger.error(f"Failed to find relevant memories: {e}")
            return []

    def _calculate_relevance_score(self, query: str, memory: Dict[str, Any]) -> float:
        """Calculate relevance score for memory."""
        score = 0.0
        query_lower = query.lower()

        # Check pattern name
        if query_lower in memory.get("pattern_name", "").lower():
            score += 0.5

        # Check description
        description = memory.get("pattern_description", "").lower()
        query_words = query_lower.split()
        matches = sum(1 for word in query_words if word in description)
        score += matches * 0.1

        # Boost by success rate
        score += memory.get("success_rate", 0) * 0.2

        # Boost by times applied
        times_applied = memory.get("times_applied", 0)
        if times_applied > 5:
            score += 0.1

        return min(score, 1.0)

    def update_memory_success(
        self,
        memory_id: str,
        successful: bool
    ) -> bool:
        """
        Update memory success statistics.

        Args:
            memory_id: Memory ID to update
            successful: Whether application was successful

        Returns:
            True if updated successfully
        """
        try:
            memories = self.load_all_learning_memories()

            for memory in memories:
                if memory.get("memory_id") == memory_id:
                    memory["times_applied"] = memory.get("times_applied", 0) + 1
                    if successful:
                        memory["times_successful"] = memory.get("times_successful", 0) + 1

                    # Recalculate success rate
                    times_applied = memory["times_applied"]
                    times_successful = memory["times_successful"]
                    memory["success_rate"] = times_successful / times_applied if times_applied > 0 else 0.0

                    # Save updated memories
                    with open(LEARNING_MEMORY_PATH, 'w') as f:
                        json.dump(memories, f, indent=2, default=str)

                    logger.info(f"Updated memory success: {memory_id}")
                    return True

            logger.warning(f"Memory not found: {memory_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to update memory success: {e}")
            return False

    # ============== Analytics ==============

    def get_investigation_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all investigations.

        Returns:
            Investigation statistics
        """
        try:
            investigations = self.list_investigations(limit=10000)

            stats = {
                "total": len(investigations),
                "by_status": {},
                "by_priority": {},
                "average_confidence": 0.0,
                "average_observations": 0.0,
                "resolved_count": 0
            }

            if not investigations:
                return stats

            # Count by status
            for inv in investigations:
                status = inv.get("status", "unknown")
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

                priority = inv.get("priority", "unknown")
                stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

                if status == "completed" or status == "closed":
                    stats["resolved_count"] += 1

            # Calculate averages
            total_confidence = sum(inv.get("confidence_score", 0) for inv in investigations)
            total_observations = sum(inv.get("total_observations", 0) for inv in investigations)

            stats["average_confidence"] = round(total_confidence / len(investigations), 2)
            stats["average_observations"] = round(total_observations / len(investigations), 2)

            return stats

        except Exception as e:
            logger.error(f"Failed to get investigation stats: {e}")
            return {"error": str(e)}


# Global singleton
_investigation_store: Optional[InvestigationStore] = None


def get_investigation_store() -> InvestigationStore:
    """Get the global investigation store instance."""
    global _investigation_store
    if _investigation_store is None:
        _investigation_store = InvestigationStore()
    return _investigation_store
