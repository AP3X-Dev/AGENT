"""
Node Action Tool - Execute actions on companion nodes based on capabilities.

This tool allows the agent to route tasks to specific nodes based on their
advertised capabilities. For example, taking a photo on a mobile device or
controlling a smart home device.
"""

import os
import httpx
from typing import Any, Dict, Optional
from langchain_core.tools import tool

# Gateway URL from environment or default
GATEWAY_URL = os.getenv("AG3NT_GATEWAY_URL", "http://127.0.0.1:18789")


@tool
def execute_node_action(
    capability: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    node_id: Optional[str] = None,
    timeout: int = 30
) -> str:
    """Execute an action on a companion node with a specific capability.
    
    Use this tool to perform actions on remote devices (companion nodes) that have
    specific capabilities. For example:
    - Take a photo on a mobile device (capability: "camera")
    - Play a sound on a device (capability: "audio_output")
    - Send a notification (capability: "notifications")
    - Control smart home devices (capability: "home_automation")
    - Access clipboard (capability: "clipboard")
    - Take a screenshot (capability: "screen_capture")
    
    Args:
        capability: The required capability (e.g., "camera", "audio_output", "notifications")
        action: The action to perform (e.g., "take_photo", "play_sound", "send_notification")
        params: Optional parameters for the action (e.g., {"message": "Hello"})
        node_id: Optional specific node ID to target. If not provided, the best node with the capability will be selected.
        timeout: Timeout in seconds (default: 30)
    
    Returns:
        A string describing the result of the action.
    
    Examples:
        # Take a photo on a mobile device
        execute_node_action(capability="camera", action="take_photo", params={"quality": "high"})
        
        # Send a notification
        execute_node_action(capability="notifications", action="send", params={"message": "Task complete!"})
        
        # Play a sound
        execute_node_action(capability="audio_output", action="play_sound", params={"text": "Hello world"})
    """
    if params is None:
        params = {}
    
    try:
        # Step 1: Find a node with the required capability (if node_id not specified)
        if not node_id:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{GATEWAY_URL}/api/nodes/capability/{capability}")
                response.raise_for_status()
                data = response.json()
                
                if not data.get("ok") or not data.get("hasCapability"):
                    return f"Error: No node found with capability '{capability}'. Available nodes may not have this capability."
                
                nodes = data.get("nodes", [])
                if not nodes:
                    return f"Error: No online nodes with capability '{capability}'"
                
                # Use the first available node (could be enhanced with load balancing)
                node_id = nodes[0]["id"]
                node_name = nodes[0]["name"]
        else:
            node_name = node_id
        
        # Step 2: Send action request to the node via Gateway
        # Note: This endpoint doesn't exist yet in the Gateway, but we'll create it
        with httpx.Client(timeout=float(timeout)) as client:
            response = client.post(
                f"{GATEWAY_URL}/api/nodes/{node_id}/action",
                json={
                    "action": action,
                    "params": params,
                    "timeout": timeout * 1000  # Convert to milliseconds
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("ok"):
                error_msg = data.get("error", "Unknown error")
                return f"Error executing action on node '{node_name}': {error_msg}"
            
            result = data.get("result", {})
            
            # Format the result nicely
            if isinstance(result, dict):
                if "error" in result:
                    return f"Action '{action}' failed on node '{node_name}': {result['error']}"
                elif "message" in result:
                    return f"Action '{action}' completed on node '{node_name}': {result['message']}"
                else:
                    return f"Action '{action}' completed on node '{node_name}'. Result: {result}"
            else:
                return f"Action '{action}' completed on node '{node_name}'. Result: {result}"
    
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout} seconds. The node may be unresponsive."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Node '{node_id}' not found or endpoint not available."
        elif e.response.status_code == 503:
            return f"Error: Node '{node_id}' is offline or unavailable."
        else:
            return f"Error: HTTP {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error executing node action: {str(e)}"


def get_node_action_tool():
    """Get the node action tool for integration into the agent."""
    return execute_node_action

