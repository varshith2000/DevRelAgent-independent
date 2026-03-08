"""
Known Error Database (KeDB) Store — Long-term error knowledge

Vector store for resolved issues with FAISS indexing.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
import numpy as np
import faiss
from datetime import datetime
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class KeDBStore:
    """Vector store for known errors with FAISS indexing."""
    
    def __init__(self, store_path: str = "data/kedb"):
        self.store_path = store_path
        self.index_path = os.path.join(store_path, "kedb.index")
        self.metadata_path = os.path.join(store_path, "kedb_metadata.json")
        
        # Ensure directory exists
        os.makedirs(store_path, exist_ok=True)
        
        # Initialize FAISS index
        self.dimension = 384  # all-MiniLM-L6-v2 embedding dimension
        self.index = None
        self.metadata = []
        
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """Load existing index or create new one."""
        try:
            if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
                # Load existing index
                self.index = faiss.read_index(self.index_path)
                
                with open(self.metadata_path, 'r') as f:
                    self.metadata = json.load(f)
                
                logger.info(f"Loaded KeDB index with {len(self.metadata)} errors")
            else:
                # Create new index
                self.index = faiss.IndexFlatIP(self.dimension)  # Inner product for cosine similarity
                self.metadata = []
                logger.info("Created new KeDB index")
                
        except Exception as e:
            logger.error(f"Error loading KeDB index: {e}")
            # Fallback to new index
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []
    
    def _save_index(self):
        """Save index and metadata to disk."""
        try:
            faiss.write_index(self.index, self.index_path)
            
            with open(self.metadata_path, 'w') as f:
                json.dump(self.metadata, f, indent=2)
                
            logger.debug("Saved KeDB index to disk")
            
        except Exception as e:
            logger.error(f"Error saving KeDB index: {e}")
    
    async def add_error(self, known_error, embedding: np.ndarray) -> bool:
        """
        Add a known error to the store.
        
        Args:
            known_error: KnownError object
            embedding: Error signature embedding
            
        Returns:
            True if successfully added
        """
        try:
            # Normalize embedding for cosine similarity
            embedding = embedding / np.linalg.norm(embedding)
            
            # Add to FAISS index
            self.index.add(embedding.reshape(1, -1).astype('float32'))
            
            # Add metadata
            error_dict = {
                "id": known_error.id,
                "error_signature": known_error.error_signature,
                "root_cause": known_error.root_cause,
                "solution": known_error.solution,
                "service_name": known_error.service_name,
                "severity": known_error.severity,
                "tags": known_error.tags,
                "created_at": known_error.created_at,
                "resolved_at": known_error.resolved_at,
                "resolution_time_minutes": known_error.resolution_time_minutes,
                "similar_count": known_error.similar_count
            }
            
            self.metadata.append(error_dict)
            
            # Save to disk
            self._save_index()
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding error to KeDB: {e}")
            return False
    
    async def search_similar(
        self, 
        query_embedding: np.ndarray, 
        threshold: float = 0.7, 
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar errors.
        
        Args:
            query_embedding: Query embedding
            threshold: Similarity threshold
            max_results: Maximum number of results
            
        Returns:
            List of similar errors with similarity scores
        """
        try:
            if self.index.ntotal == 0:
                return []
            
            # Normalize query embedding
            query_embedding = query_embedding / np.linalg.norm(query_embedding)
            
            # Search
            scores, indices = self.index.search(
                query_embedding.reshape(1, -1).astype('float32'), 
                min(max_results, self.index.ntotal)
            )
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and score >= threshold:
                    error_data = self.metadata[idx].copy()
                    error_data['similarity'] = float(score)
                    results.append(error_data)
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x['similarity'], reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar errors: {e}")
            return []
    
    async def increment_similar_count(self, error_id: str) -> bool:
        """Increment the similar count for an error."""
        try:
            for error in self.metadata:
                if error['id'] == error_id:
                    error['similar_count'] = error.get('similar_count', 0) + 1
                    self._save_index()
                    return True
            return False
            
        except Exception as e:
            logger.error(f"Error incrementing similar count: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the KeDB."""
        try:
            if not self.metadata:
                return {
                    "total_errors": 0,
                    "by_severity": {},
                    "by_service": {},
                    "most_common_tags": [],
                    "avg_resolution_time": 0
                }
            
            # Count by severity
            severity_counts = Counter(error.get('severity', 'unknown') for error in self.metadata)
            
            # Count by service
            service_counts = Counter(error.get('service_name', 'unknown') for error in self.metadata)
            
            # Most common tags
            all_tags = []
            for error in self.metadata:
                all_tags.extend(error.get('tags', []))
            tag_counts = Counter(all_tags)
            
            # Average resolution time
            resolution_times = [
                error.get('resolution_time_minutes', 0) 
                for error in self.metadata 
                if error.get('resolution_time_minutes', 0) > 0
            ]
            avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0
            
            return {
                "total_errors": len(self.metadata),
                "by_severity": dict(severity_counts),
                "by_service": dict(service_counts),
                "most_common_tags": [tag for tag, count in tag_counts.most_common(10)],
                "avg_resolution_time": round(avg_resolution_time, 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting KeDB stats: {e}")
            return {}
    
    async def search_by_tags(self, tags: List[str], max_results: int = 5) -> List[Dict[str, Any]]:
        """Search errors by tags."""
        try:
            results = []
            
            for error in self.metadata:
                error_tags = error.get('tags', [])
                # Check if any of the search tags match error tags
                if any(tag.lower() in [t.lower() for t in error_tags] for tag in tags):
                    results.append(error)
            
            # Sort by similar_count (most referenced first)
            results.sort(key=lambda x: x.get('similar_count', 0), reverse=True)
            
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"Error searching by tags: {e}")
            return []
    
    async def get_error_by_id(self, error_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific error by ID."""
        try:
            for error in self.metadata:
                if error['id'] == error_id:
                    return error
            return None
            
        except Exception as e:
            logger.error(f"Error getting error by ID: {e}")
            return None
