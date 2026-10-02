"""
GitHub Tool — GitHub Issue and PR Management

Enables the agent to draft GitHub issues and PRs based on analysis.
All write operations require mandatory HITL approval (enforced automatically by registry).
"""

import asyncio
import logging
from typing import Any, Dict, List, Literal, Optional

import httpx
from config.settings import get_settings

from tools.registry import ToolCategory, tool

logger = logging.getLogger(__name__)

GITHUB_TOKEN = get_settings().github_token
GITHUB_API_BASE = "https://api.github.com"


@tool(
    name="draft_github_issue",
    description="Draft a GitHub issue after approval (requires HITL approval). Creates an issue with title, body, labels, and assignees.",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="github_issue",
    read_only=False,
    risk_level="medium",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in format 'owner/repo'"
        },
        "title": {
            "type": "string",
            "description": "Issue title"
        },
        "body": {
            "type": "string",
            "description": "Issue body/description in markdown"
        },
        "labels": {
            "type": "array",
            "description": "List of labels to add"
        },
        "assignees": {
            "type": "array",
            "description": "List of usernames to assign"
        }
    }
)
async def draft_github_issue(
    repo: str,
    title: str,
    body: str,
    labels: List[str] = [],
    assignees: List[str] = []
) -> Dict[str, Any]:
    """
    Draft and create a GitHub issue after approval.

    Note: Approval is automatically requested by the tool registry.

    Args:
        repo: Repository in format 'owner/repo'
        title: Issue title
        body: Issue body/description in markdown
        labels: List of labels to add
        assignees: List of usernames to assign

    Returns:
        Dictionary with success status and issue URL
    """
    if not GITHUB_TOKEN:
        return {
            "success": False,
            "error": "GITHUB_TOKEN environment variable not set"
        }

    # Create issue via GitHub API
    try:
        url = f"{GITHUB_API_BASE}/repos/{repo}/issues"

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

        payload = {
            "title": title,
            "body": body,
            "labels": labels,
            "assignees": assignees
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)

            if response.status_code == 201:
                data = response.json()
                logger.info(f"✅ GitHub issue created: {data['html_url']}")
                return {
                    "success": True,
                    "issue_url": data["html_url"],
                    "issue_number": data["number"],
                    "repo": repo
                }
            else:
                logger.error(f"❌ GitHub API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"GitHub API error: {response.status_code} - {response.text}"
                }

    except Exception as e:
        logger.error(f"Failed to create GitHub issue: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@tool(
    name="draft_github_pr",
    description="Create a branch, commit changes, and open a PR (requires HITL approval). Full PR workflow from analysis to pull request.",
    category=ToolCategory.API,
    requires_approval=True,
    approval_action_type="github_pr",
    read_only=False,
    risk_level="high",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in format 'owner/repo'"
        },
        "branch_name": {
            "type": "string",
            "description": "Name for the new branch"
        },
        "commit_message": {
            "type": "string",
            "description": "Commit message"
        },
        "file_changes": {
            "type": "object",
            "description": "File paths and their new contents"
        },
        "pr_title": {
            "type": "string",
            "description": "Pull request title"
        },
        "pr_body": {
            "type": "string",
            "description": "Pull request body in markdown"
        },
        "base_branch": {
            "type": "string",
            "description": "Base branch (default: repository default branch)",
            "required": False
        }
    }
)
async def draft_github_pr(
    repo: str,
    branch_name: str,
    commit_message: str,
    file_changes: Dict[str, str],
    pr_title: str,
    pr_body: str,
    base_branch: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a complete PR with changes using GitHub API.

    Full workflow:
    1. Get repository info and default branch
    2. Get base commit SHA
    3. Create new branch
    4. Create blobs for each file
    5. Create tree with blobs
    6. Create commit with tree
    7. Update branch reference
    8. Create PR

    Note: Approval is automatically requested by the tool registry.

    Args:
        repo: Repository in format 'owner/repo'
        branch_name: Name for the new branch
        commit_message: Commit message
        file_changes: Dictionary of file_path -> content
        pr_title: Pull request title
        pr_body: Pull request body in markdown
        base_branch: Base branch (default: repository default branch)

    Returns:
        Dictionary with success status and PR URL
    """
    if not GITHUB_TOKEN:
        return {
            "success": False,
            "error": "GITHUB_TOKEN environment variable not set"
        }

    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Get repository info
            repo_url = f"{GITHUB_API_BASE}/repos/{repo}"
            repo_resp = await client.get(repo_url, headers=headers)

            if repo_resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Repository not found or access denied: {repo} (status: {repo_resp.status_code})"
                }

            repo_data = repo_resp.json()
            default_branch = base_branch or repo_data["default_branch"]

            # 2. Get base commit SHA
            ref_url = f"{GITHUB_API_BASE}/repos/{repo}/git/refs/heads/{default_branch}"
            ref_resp = await client.get(ref_url, headers=headers)

            if ref_resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get base branch '{default_branch}': {ref_resp.text}"
                }

            base_sha = ref_resp.json()["object"]["sha"]
            logger.info(f"Base branch: {default_branch}, SHA: {base_sha[:8]}")

            # 3. Create new branch
            branch_url = f"{GITHUB_API_BASE}/repos/{repo}/git/refs"
            branch_data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha
            }
            branch_resp = await client.post(branch_url, headers=headers, json=branch_data)

            if branch_resp.status_code not in [200, 201]:
                error_msg = branch_resp.text
                if "already exists" in error_msg:
                    return {
                        "success": False,
                        "error": f"Branch '{branch_name}' already exists in repository"
                    }
                return {
                    "success": False,
                    "error": f"Failed to create branch: {error_msg}"
                }

            logger.info(f"Created branch: {branch_name}")

            # 4. Create blobs for each file
            blob_shas = {}
            for file_path, content in file_changes.items():
                blob_url = f"{GITHUB_API_BASE}/repos/{repo}/git/blobs"
                blob_data = {
                    "content": content,
                    "encoding": "utf-8"
                }
                blob_resp = await client.post(blob_url, headers=headers, json=blob_data)

                if blob_resp.status_code not in [200, 201]:
                    return {
                        "success": False,
                        "error": f"Failed to create blob for {file_path}: {blob_resp.text}"
                    }

                blob_shas[file_path] = blob_resp.json()["sha"]
                logger.info(f"Created blob: {file_path}")

            # 5. Create tree with blobs
            tree_url = f"{GITHUB_API_BASE}/repos/{repo}/git/trees"
            tree_items = [
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": sha
                }
                for path, sha in blob_shas.items()
            ]
            tree_data = {
                "base_tree": base_sha,
                "tree": tree_items
            }
            tree_resp = await client.post(tree_url, headers=headers, json=tree_data)

            if tree_resp.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"Failed to create tree: {tree_resp.text}"
                }

            tree_sha = tree_resp.json()["sha"]
            logger.info(f"Created tree with {len(tree_items)} item(s)")

            # 6. Create commit
            commit_url = f"{GITHUB_API_BASE}/repos/{repo}/git/commits"
            commit_data = {
                "message": commit_message,
                "parents": [base_sha],
                "tree": tree_sha
            }
            commit_resp = await client.post(commit_url, headers=headers, json=commit_data)

            if commit_resp.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"Failed to create commit: {commit_resp.text}"
                }

            commit_sha = commit_resp.json()["sha"]
            logger.info(f"Created commit: {commit_sha[:8]}")

            # 7. Update branch reference to point to new commit
            update_ref_url = f"{GITHUB_API_BASE}/repos/{repo}/git/refs/heads/{branch_name}"
            update_ref_data = {"sha": commit_sha, "force": False}
            update_ref_resp = await client.patch(update_ref_url, headers=headers, json=update_ref_data)

            if update_ref_resp.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"Failed to update branch reference: {update_ref_resp.text}"
                }

            logger.info(f"Updated branch {branch_name} to commit {commit_sha[:8]}")

            # 8. Create PR
            pr_url = f"{GITHUB_API_BASE}/repos/{repo}/pulls"
            pr_data = {
                "title": pr_title,
                "body": pr_body,
                "head": branch_name,
                "base": default_branch
            }
            pr_resp = await client.post(pr_url, headers=headers, json=pr_data)

            if pr_resp.status_code == 201:
                pr_data_result = pr_resp.json()
                pr_number = pr_data_result["number"]
                pr_html_url = pr_data_result["html_url"]

                logger.info(f"✅ GitHub PR created: {pr_html_url}")

                return {
                    "success": True,
                    "pr_url": pr_html_url,
                    "pr_number": pr_number,
                    "branch": branch_name,
                    "base_branch": default_branch,
                    "commit_sha": commit_sha,
                    "repo": repo,
                    "files_changed": len(file_changes),
                    "state": "open"
                }
            else:
                return {
                    "success": False,
                    "error": f"PR creation failed: {pr_resp.text}"
                }

    except httpx.TimeoutException:
        logger.error("GitHub API request timed out")
        return {
            "success": False,
            "error": "GitHub API request timed out. Please try again."
        }
    except Exception as e:
        logger.error(f"Failed to create GitHub PR: {e}")
        return {
            "success": False,
            "error": f"PR creation failed: {str(e)}"
        }


@tool(
    name="search_github_issues",
    description="Search GitHub issues in a repository (read-only, no approval required).",
    category=ToolCategory.API,
    read_only=True,
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in format 'owner/repo'"
        },
        "query": {
            "type": "string",
            "description": "Search query"
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed", "all"],
            "description": "Issue state filter"
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results (default: 10)"
        }
    }
)
async def search_github_issues(
    repo: str,
    query: str = "",
    state: str = "open",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search GitHub issues (read-only, no approval required).

    Args:
        repo: Repository in format 'owner/repo'
        query: Search query
        state: Issue state filter (open/closed/all)
        limit: Maximum number of results

    Returns:
        Dictionary with search results
    """
    if not GITHUB_TOKEN:
        return {
            "success": False,
            "error": "GITHUB_TOKEN environment variable not set"
        }

    try:
        url = f"{GITHUB_API_BASE}/repos/{repo}/issues"

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        params = {
            "state": state,
            "per_page": min(limit, 100)
        }

        if query:
            params["q"] = query

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)

            if response.status_code == 200:
                issues = response.json()
                return {
                    "success": True,
                    "issues": [
                        {
                            "number": issue["number"],
                            "title": issue["title"],
                            "state": issue["state"],
                            "html_url": issue["html_url"],
                            "user": issue["user"]["login"],
                            "created_at": issue["created_at"]
                        }
                        for issue in issues
                    ],
                    "total": len(issues)
                }
            else:
                return {
                    "success": False,
                    "error": f"GitHub API error: {response.status_code}"
                }

    except Exception as e:
        logger.error(f"Failed to search GitHub issues: {e}")
        return {
            "success": False,
            "error": str(e)
        }
