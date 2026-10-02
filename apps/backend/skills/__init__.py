"""
Skills Framework — Composable multi-tool workflows

Skills chain multiple tools together to accomplish complex tasks.
"""

from .base import Skill, SkillRegistry, SkillResult, get_skill_registry, skill
from .diagnose_error import DiagnoseErrorSkill
from .search_docs import SearchDocsSkill

# Initialize skills
_diagnose_error_skill = DiagnoseErrorSkill()
_search_docs_skill = SearchDocsSkill()

# Register skills
registry = get_skill_registry()
registry.register(_diagnose_error_skill)
registry.register(_search_docs_skill)

__all__ = [
    'Skill',
    'SkillResult', 
    'SkillRegistry',
    'get_skill_registry',
    'skill',
    'DiagnoseErrorSkill',
    'SearchDocsSkill'
]
