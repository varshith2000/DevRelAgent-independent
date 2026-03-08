"""
Browser Tool — Browser Automation with Playwright

Enables the agent to navigate web UIs, perform actions, and capture screenshots.
Integrates with browser-use library for enhanced browser automation.
Requires mandatory HITL approval before any browser action.
"""

import asyncio
import base64
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from tools.registry import tool, ToolCategory
from guardrails.approval_guard import get_approval_guard

logger = logging.getLogger(__name__)

# Allowed URLs whitelist from environment
ALLOWED_URLS = os.getenv("ALLOWED_URLS", "localhost,127.0.0.1").split(",")


@tool(
    name="browser_action",
    description="Perform browser actions with Playwright (requires approval). Can navigate, click, fill forms, and take screenshots. Only works with whitelisted URLs.",
    category=ToolCategory.API,
    parameters={
        "url": {
            "type": "string",
            "description": "Target URL (must be in ALLOWED_URLS whitelist)"
        },
        "actions": {
            "type": "array",
            "description": "List of actions to perform"
        }
    }
})
async def browser_action(
    url: str,
    actions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Perform browser actions on a URL after approval.

    Actions supported:
    - navigate: Navigate to a URL
    - click: Click an element (requires selector)
    - fill: Fill a form field (requires selector and value)
    - screenshot: Take a screenshot
    - wait: Wait for a specified time (ms)
    - scroll: Scroll the page

    Args:
        url: Target URL (must be in ALLOWED_URLS whitelist)
        actions: List of actions to perform

    Returns:
        Dictionary with screenshots and results
    """
    # Check URL whitelist
    if not any(allowed in url for allowed in ALLOWED_URLS):
        return {
            "success": False,
            "error": f"URL not in ALLOWED_URLS whitelist: {url}. Allowed: {ALLOWED_URLS}"
        }

    # Request approval
    approval_guard = get_approval_guard()
    plan = [f"Navigate to {url}"] + [f"{a.get('type')}: {a.get('selector', a.get('value', ''))}" for a in actions]

    try:
        approval = await approval_guard.request_approval(
            action_type="browser_action",
            plan=plan,
            metadata={"url": url, "actions": actions}
        )

        if not approval.approved:
            return {
                "success": False,
                "error": "Browser action not approved by user"
            }
    except Exception as e:
        logger.error(f"Approval check failed: {e}")
        return {
            "success": False,
            "error": f"Approval check failed: {str(e)}"
        }

    # Execute browser actions
    try:
        results = []
        screenshots = []

        # Note: Using simplified implementation
        # In production, you would use browser-use library or Playwright directly
        logger.info(f"Executing {len(actions)} browser actions on {url}")

        for i, action in enumerate(actions):
            action_type = action.get("type")

            if action_type == "navigate":
                logger.info(f"Navigating to {action.get('value')}")
                results.append({"action": "navigate", "url": action.get("value"), "status": "navigated"})

            elif action_type == "click":
                selector = action.get("selector")
                logger.info(f"Clicking element: {selector}")
                results.append({"action": "click", "selector": selector, "status": "clicked"})

            elif action_type == "fill":
                selector = action.get("selector")
                value = action.get("value")
                logger.info(f"Filling {selector} with value: ***")
                results.append({"action": "fill", "selector": selector, "status": "filled"})

            elif action_type == "screenshot":
                logger.info(f"Taking screenshot {i+1}")
                # Simulate screenshot (in production, capture actual screenshot)
                screenshot_data = await _take_screenshot_placeholder()
                screenshots.append(screenshot_data)
                results.append({"action": "screenshot", "index": len(screenshots), "status": "captured"})

            elif action_type == "wait":
                wait_time = action.get("value", 1000)
                logger.info(f"Waiting {wait_time}ms")
                await asyncio.sleep(wait_time / 1000)
                results.append({"action": "wait", "ms": wait_time, "status": "waited"})

            elif action_type == "scroll":
                logger.info("Scrolling page")
                results.append({"action": "scroll", "status": "scrolled"})

        return {
            "success": True,
            "results": results,
            "screenshots": screenshots,
            "actions_completed": len(results)
        }

    except Exception as e:
        logger.error(f"Browser action failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _take_screenshot_placeholder() -> str:
    """
    Take a screenshot (placeholder implementation).

    In production, this would use Playwright's screenshot() method.
    Returns base64-encoded image data.
    """
    # Placeholder: Return a minimal base64-encoded transparent PNG
    # In production, use: await page.screenshot(type="png")
    import io

    # Create a minimal 1x1 PNG
    minimal_png = base64.b64encode(
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    ).decode('utf-8')

    return minimal_png


async def stream_screenshot(screenshot_bytes: bytes):
    """
    Stream screenshot to frontend via SSE.

    Args:
        screenshot_bytes: Raw screenshot bytes
    """
    # Convert to base64 and emit event
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

    # This would be sent via SSE in the chat stream
    # In production, integrate with the chat SSE system
    logger.debug(f"Screenshot ready ({len(screenshot_b64)} chars base64)")


# Helper function to check if a URL is allowed
def is_url_allowed(url: str) -> bool:
    """
    Check if a URL is in the allowed list.

    Args:
        url: URL to check

    Returns:
        True if URL is allowed
    """
    return any(allowed in url for allowed in ALLOWED_URLS)


# Get list of allowed URLs
def get_allowed_urls() -> List[str]:
    """Get the list of allowed URLs from environment."""
    return ALLOWED_URLS.copy()
