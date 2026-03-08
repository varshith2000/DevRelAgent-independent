"""
SearchDocsSkill — Multi-source documentation search

Searches across multiple documentation sources and provides comprehensive answers.
"""

from typing import Dict, Any, Optional, List
import logging
from .base import Skill, SkillResult
from tools.registry import get_registry

logger = logging.getLogger(__name__)


class SearchDocsSkill(Skill):
    """Skill for comprehensive documentation search across multiple sources."""
    
    def __init__(self):
        super().__init__(
            name="search_docs",
            description="Search documentation across multiple sources and provide comprehensive answers",
            required_tools=["rag_search", "web_search"]
        )
    
    async def execute(self, context: Dict[str, Any], **kwargs) -> SkillResult:
        """
        Execute multi-source documentation search.
        
        Args:
            context: Execution context with tool registry, session info, etc.
            query: Search query
            sources: Optional list of sources to search ['docs', 'web', 'api']
            max_results: Maximum number of results per source
        """
        self.clear_steps()
        
        query = kwargs.get('query', '')
        sources = kwargs.get('sources', ['docs', 'web'])
        max_results = kwargs.get('max_results', 3)
        
        if not query:
            return SkillResult(
                success=False,
                result=None,
                steps=self.steps,
                error="Search query is required"
            )
        
        try:
            registry = context.get('tool_registry') or get_registry()
            
            results = {}
            
            # Step 1: Search local documentation
            if 'docs' in sources:
                docs_result = await self._search_local_docs(registry, query, max_results)
                results['docs'] = docs_result
            
            # Step 2: Search web/external sources
            if 'web' in sources:
                web_result = await self._search_web_docs(registry, query, max_results)
                results['web'] = web_result
            
            # Step 3: Search API documentation
            if 'api' in sources:
                api_result = await self._search_api_docs(registry, query, max_results)
                results['api'] = api_result
            
            # Step 4: Synthesize comprehensive answer
            answer = await self._synthesize_answer(query, results)
            
            return SkillResult(
                success=True,
                result=answer,
                steps=self.steps,
                metadata={
                    "sources_searched": sources,
                    "total_results": sum(len(r.get('results', [])) for r in results.values() if r)
                }
            )
            
        except Exception as e:
            logger.error(f"Error in SearchDocsSkill: {e}")
            return SkillResult(
                success=False,
                result=None,
                steps=self.steps,
                error=str(e)
            )
    
    async def _search_local_docs(self, registry, query: str, max_results: int) -> Optional[Dict[str, Any]]:
        """Search local documentation using RAG."""
        try:
            rag_tool = registry.get("rag_search") or registry.get("doc_search")
            if not rag_tool:
                self.log_step("Local Docs Search", "RAG tool not available")
                return None
            
            result = await rag_tool.execute(query=query, max_results=max_results)
            self.log_step("Local Docs Search", f"Searched local docs for: {query[:50]}...")
            
            if result.success and result.result:
                return {
                    "source": "local_docs",
                    "results": result.result.get('documents', []),
                    "answer": result.result.get('answer', ''),
                    "citations": result.result.get('citations', [])
                }
            
            return {"source": "local_docs", "results": [], "answer": ""}
            
        except Exception as e:
            self.log_step("Local Docs Search", f"Error: {e}")
            return None
    
    async def _search_web_docs(self, registry, query: str, max_results: int) -> Optional[Dict[str, Any]]:
        """Search web documentation sources."""
        try:
            web_tool = registry.get("web_search")
            if not web_tool:
                self.log_step("Web Docs Search", "Web search tool not available")
                return None
            
            # Enhance query for documentation search
            doc_query = f"{query} documentation tutorial guide"
            
            result = await web_tool.execute(query=doc_query, max_results=max_results)
            self.log_step("Web Docs Search", f"Searched web for: {doc_query[:50]}...")
            
            if result.success and result.result:
                return {
                    "source": "web_docs",
                    "results": result.result.get('results', []),
                    "summary": result.result.get('summary', '')
                }
            
            return {"source": "web_docs", "results": [], "summary": ""}
            
        except Exception as e:
            self.log_step("Web Docs Search", f"Error: {e}")
            return None
    
    async def _search_api_docs(self, registry, query: str, max_results: int) -> Optional[Dict[str, Any]]:
        """Search API documentation (Swagger/OpenAPI)."""
        try:
            # This would use a specialized API docs tool if available
            api_tool = registry.get("api_search") or registry.get("swagger_search")
            if not api_tool:
                self.log_step("API Docs Search", "API docs tool not available")
                return None
            
            result = await api_tool.execute(query=query, max_results=max_results)
            self.log_step("API Docs Search", f"Searched API docs for: {query[:50]}...")
            
            if result.success and result.result:
                return {
                    "source": "api_docs",
                    "results": result.result.get('endpoints', []),
                    "schemas": result.result.get('schemas', [])
                }
            
            return {"source": "api_docs", "results": [], "schemas": []}
            
        except Exception as e:
            self.log_step("API Docs Search", f"Error: {e}")
            return None
    
    async def _synthesize_answer(self, query: str, results: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize comprehensive answer from multiple sources."""
        
        answer = {
            "query": query,
            "comprehensive_answer": "",
            "sources": [],
            "confidence": "medium",
            "related_topics": [],
            "next_steps": []
        }
        
        all_results = []
        
        # Collect results from all sources
        for source_name, source_data in results.items():
            if not source_data:
                continue
                
            source_info = {
                "source": source_name,
                "found_results": len(source_data.get('results', [])),
                "has_answer": bool(source_data.get('answer') or source_data.get('summary'))
            }
            answer["sources"].append(source_info)
            
            # Add results to comprehensive list
            if source_data.get('results'):
                all_results.extend(source_data['results'])
        
        # Build comprehensive answer
        answer_parts = []
        
        # Start with local docs answer if available
        if results.get('docs') and results['docs'].get('answer'):
            answer_parts.append("From local documentation:")
            answer_parts.append(results['docs']['answer'])
            answer["confidence"] = "high"
        
        # Add web search insights
        if results.get('web') and results['web'].get('summary'):
            answer_parts.append("\nFrom web sources:")
            answer_parts.append(results['web']['summary'])
        
        # Add API documentation
        if results.get('api') and results['api'].get('results'):
            api_results = results['api']['results']
            if api_results:
                answer_parts.append(f"\nFound {len(api_results)} relevant API endpoints:")
                for endpoint in api_results[:2]:  # Show top 2
                    if isinstance(endpoint, dict):
                        method = endpoint.get('method', 'GET')
                        path = endpoint.get('path', '')
                        answer_parts.append(f"- {method} {path}")
        
        # Combine all parts
        if answer_parts:
            answer["comprehensive_answer"] = "\n".join(answer_parts)
        else:
            answer["comprehensive_answer"] = f"No specific documentation found for '{query}'. Consider checking official documentation or community resources."
            answer["confidence"] = "low"
        
        # Generate related topics and next steps
        if all_results:
            # Extract related topics from result titles/descriptions
            topics = set()
            for result in all_results[:5]:  # Top 5 results
                if isinstance(result, dict):
                    title = result.get('title', '')
                    if title:
                        # Simple topic extraction
                        words = title.lower().split()
                        for word in words:
                            if len(word) > 4 and word not in ['documentation', 'guide', 'tutorial']:
                                topics.add(word.capitalize())
            
            answer["related_topics"] = list(topics)[:5]
        
        # Generate next steps
        if answer["confidence"] == "high":
            answer["next_steps"] = [
                "Review the provided documentation",
                "Try the suggested examples or code snippets"
            ]
        elif answer["confidence"] == "medium":
            answer["next_steps"] = [
                "Check official documentation for more details",
                "Look for community examples and tutorials"
            ]
        else:
            answer["next_steps"] = [
                "Refine your search query with more specific terms",
                "Check if the feature or topic exists in the current version",
                "Consider asking in community forums or support channels"
            ]
        
        self.log_step("Answer Synthesis", f"Generated comprehensive answer with {answer['confidence']} confidence")
        
        return answer