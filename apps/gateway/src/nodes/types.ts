/**
 * Node types and interfaces for AG3NT multi-node architecture.
 *
 * Nodes represent devices that can execute actions for the agent.
 * Each node has a set of capabilities that determine what actions it can perform.
 */

/**
 * Node capabilities - what actions a node can perform.
 * Used for routing requests to the appropriate node.
 */
export type NodeCapability =
  | "file_management" // Open files, reveal in explorer, file search
  | "application_control" // Launch apps, open URLs
  | "system_info" // CPU, RAM, disk, battery info
  | "code_execution" // Run scripts and commands
  | "camera" // Take photos/video
  | "microphone" // Audio recording
  | "audio_output" // Text-to-speech, play sounds
  | "notifications" // System notifications
  | "home_automation" // Smart home control
  | "clipboard" // Clipboard access
  | "screen_capture"; // Screenshot/screen recording

/**
 * Node type - primary (main Gateway device) or companion (remote device).
 */
export type NodeType = "primary" | "companion";

/**
 * Node connection status.
 */
export type NodeStatus = "online" | "offline" | "connecting";

/**
 * Platform/OS information for a node.
 */
export interface NodePlatform {
  /** Operating system: "windows", "darwin" (macOS), "linux", "ios", "android" */
  os: string;
  /** OS version */
  version?: string;
  /** Architecture: "x64", "arm64", etc. */
  arch?: string;
}

/**
 * Node information - represents a connected device.
 */
export interface NodeInfo {
  /** Unique node identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Node type */
  type: NodeType;
  /** Current status */
  status: NodeStatus;
  /** Available capabilities */
  capabilities: NodeCapability[];
  /** Platform information */
  platform: NodePlatform;
  /** When the node connected */
  connectedAt?: Date;
  /** Last heartbeat from the node */
  lastSeen?: Date;
  /** WebSocket connection ID (for companion nodes) */
  connectionId?: string;
}

/**
 * Node configuration from config file.
 */
export interface NodeConfig {
  /** Node name */
  name: string;
  /** Node type */
  type: NodeType;
  /** Capabilities this node provides */
  capabilities: NodeCapability[];
}

/**
 * Request to execute an action on a node.
 */
export interface NodeActionRequest {
  /** Target node ID (or "any" to find a capable node) */
  nodeId: string | "any";
  /** Required capability for this action */
  capability: NodeCapability;
  /** Action name */
  action: string;
  /** Action parameters */
  params: Record<string, unknown>;
  /** Request ID for tracking */
  requestId: string;
}

/**
 * Response from a node action.
 */
export interface NodeActionResponse {
  /** Request ID */
  requestId: string;
  /** Node that executed the action */
  nodeId: string;
  /** Whether the action succeeded */
  success: boolean;
  /** Result data */
  result?: unknown;
  /** Error message if failed */
  error?: string;
}

/**
 * Event emitted when a node connects or disconnects.
 */
export interface NodeEvent {
  type: "connected" | "disconnected" | "capabilities_changed";
  nodeId: string;
  node?: NodeInfo;
  timestamp: Date;
}

/**
 * Callback for node events.
 */
export type NodeEventHandler = (event: NodeEvent) => void;

