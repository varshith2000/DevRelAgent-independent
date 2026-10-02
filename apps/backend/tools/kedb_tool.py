"""
KeDB Tool — Known Error Database

Vector store for resolved issues: error_signature → root_cause → solution
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from memory.kedb_store import KeDBStore
from sentence_transformers import SentenceTransformer

from tools.registry import ToolCategory, tool

logger = logging.getLogger(__name__)


@dataclass
class KnownError:
    """Represents a known error in the database."""
    id: str
    error_signature: str
    root_cause: str
    solution: str
    service_name: str
    severity: str  # low, medium, high, critical
    tags: List[str]
    created_at: str
    resolved_at: str
    resolution_time_minutes: int
    similar_count: int = 0  # How many times this error was matched


class KeDBTool:
    """Tool for interacting with the Known Error Database."""
    
    def __init__(self, store_path: str = "data/kedb"):
        self.store_path = store_path
        self.store = KeDBStore(store_path)
        self.model = None
        self._ensure_model()
    
    def _ensure_model(self):
        """Ensure the sentence transformer model is loaded."""
        if self.model is None:
            try:
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence transformer model for KeDB")
            except Exception as e:
                logger.error(f"Failed to load sentence transformer: {e}")
                self.model = None
    
    async def lookup_similar_error(self, error_description: str, threshold: float = 0.7) -> Optional[Dict[str, Any]]:
        """
        Look up similar errors in the KeDB.
        
        Args:
            error_description: Description of the error to search for
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            Dict with similar error info or None if not found
        """
        try:
            if not self.model:
                return None
            
            # Get embedding for the error description
            query_embedding = self.model.encode([error_description])
            
            # Search in the store
            similar_errors = await self.store.search_similar(
                query_embedding[0], 
                threshold=threshold,
                max_results=3
            )
            
            if similar_errors:
                best_match = similar_errors[0]
                
                # Update similar count
                await self.store.increment_similar_count(best_match['id'])
                
                return {
                    "found": True,
                    "similarity": best_match['similarity'],
                    "error": best_match,
                    "solution": best_match['solution'],
                    "root_cause": best_match['root_cause'],
                    "service_name": best_match['service_name'],
                    "tags": best_match['tags']
                }
            
            return {"found": False}
            
        except Exception as e:
            logger.error(f"Error looking up similar error: {e}")
            return None
    
    async def add_resolved_error(
        self,
        error_signature: str,
        root_cause: str,
        solution: str,
        service_name: str = "",
        severity: str = "medium",
        tags: List[str] = None,
        resolution_time_minutes: int = 0
    ) -> bool:
        """
        Add a resolved error to the KeDB.
        
        Args:
            error_signature: Unique signature/description of the error
            root_cause: Root cause analysis
            solution: Solution that resolved the error
            service_name: Name of the affected service
            severity: Error severity level
            tags: List of tags for categorization
            resolution_time_minutes: Time taken to resolve in minutes
            
        Returns:
            True if successfully added, False otherwise
        """
        try:
            if not self.model:
                return False
            
            # Generate embedding
            embedding = self.model.encode([error_signature])[0]
            
            # Create known error object
            known_error = KnownError(
                id=f"ke_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                error_signature=error_signature,
                root_cause=root_cause,
                solution=solution,
                service_name=service_name,
                severity=severity,
                tags=tags or [],
                created_at=datetime.now().isoformat(),
                resolved_at=datetime.now().isoformat(),
                resolution_time_minutes=resolution_time_minutes
            )
            
            # Store in KeDB
            success = await self.store.add_error(known_error, embedding)
            
            if success:
                logger.info(f"Added resolved error to KeDB: {error_signature[:50]}...")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding resolved error: {e}")
            return False
    
    async def get_error_stats(self) -> Dict[str, Any]:
        """Get statistics about the KeDB."""
        try:
            stats = await self.store.get_stats()
            return {
                "total_errors": stats.get("total_errors", 0),
                "by_severity": stats.get("by_severity", {}),
                "by_service": stats.get("by_service", {}),
                "most_common_tags": stats.get("most_common_tags", []),
                "avg_resolution_time": stats.get("avg_resolution_time", 0)
            }
        except Exception as e:
            logger.error(f"Error getting KeDB stats: {e}")
            return {}
    
    async def search_by_tags(self, tags: List[str], max_results: int = 5) -> List[Dict[str, Any]]:
        """Search errors by tags."""
        try:
            return await self.store.search_by_tags(tags, max_results)
        except Exception as e:
            logger.error(f"Error searching by tags: {e}")
            return []


# Global KeDB tool instance
_kedb_tool = None


def get_kedb_tool() -> KeDBTool:
    """Get the global KeDB tool instance."""
    global _kedb_tool
    if _kedb_tool is None:
        _kedb_tool = KeDBTool()
    return _kedb_tool


@tool(
    name="kedb_lookup",
    description="Look up similar errors in the Known Error Database (KeDB)",
    category=ToolCategory.MEMORY
)
async def kedb_lookup(query: str, threshold: float = 0.7) -> Dict[str, Any]:
    """
    Look up similar errors in the Known Error Database.
    
    Args:
        query: Error description or signature to search for
        threshold: Similarity threshold (0.0 to 1.0, default 0.7)
        
    Returns:
        Dict with similar error information or empty if not found
    """
    kedb = get_kedb_tool()
    result = await kedb.lookup_similar_error(query, threshold)
    
    if result and result.get("found"):
        return {
            "found_solution": True,
            "similarity": result["similarity"],
            "solution": result["solution"],
            "root_cause": result["root_cause"],
            "service_name": result["service_name"],
            "tags": result["tags"],
            "error_id": result["error"]["id"]
        }
    
    return {
        "found_solution": False,
        "message": "No similar errors found in KeDB"
    }


@tool(
    name="kedb_add_error",
    description="Add a resolved error to the Known Error Database",
    category=ToolCategory.MEMORY
)
async def kedb_add_error(
    error_signature: str,
    root_cause: str,
    solution: str,
    service_name: str = "",
    severity: str = "medium",
    tags: str = "",
    resolution_time_minutes: int = 0
) -> Dict[str, Any]:
    """
    Add a resolved error to the KeDB.
    
    Args:
        error_signature: Unique description of the error
        root_cause: Root cause analysis
        solution: Solution that resolved the error
        service_name: Name of the affected service
        severity: Error severity (low, medium, high, critical)
        tags: Comma-separated tags for categorization
        resolution_time_minutes: Time taken to resolve in minutes
        
    Returns:
        Dict with success status and message
    """
    kedb = get_kedb_tool()
    
    # Parse tags
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
    
    success = await kedb.add_resolved_error(
        error_signature=error_signature,
        root_cause=root_cause,
        solution=solution,
        service_name=service_name,
        severity=severity,
        tags=tag_list,
        resolution_time_minutes=resolution_time_minutes
    )
    
    if success:
        return {
            "success": True,
            "message": "Error successfully added to KeDB",
            "error_signature": error_signature[:50] + "..." if len(error_signature) > 50 else error_signature
        }
    
    return {
        "success": False,
        "message": "Failed to add error to KeDB"
    }


@tool(
    name="kedb_stats",
    description="Get statistics about the Known Error Database",
    category=ToolCategory.MEMORY
)
async def kedb_stats() -> Dict[str, Any]:
    """
    Get statistics about the KeDB.
    
    Returns:
        Dict with KeDB statistics
    """
    kedb = get_kedb_tool()
    stats = await kedb.get_error_stats()
    
    return {
        "kedb_statistics": stats,
        "summary": f"KeDB contains {stats.get('total_errors', 0)} resolved errors"
    }