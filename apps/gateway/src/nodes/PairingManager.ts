/**
 * PairingManager - Manages pairing codes for companion node authentication
 */

export interface PairingCode {
  code: string;
  createdAt: Date;
  expiresAt: Date;
  used: boolean;
}

export interface ApprovedNode {
  nodeId: string;
  name: string;
  approvedAt: Date;
  sharedSecret?: string;
}

export class PairingManager {
  private activeCodes: Map<string, PairingCode> = new Map();
  private approvedNodes: Map<string, ApprovedNode> = new Map();
  private readonly CODE_LENGTH = 6;
  private readonly CODE_EXPIRY_MS = 5 * 60 * 1000; // 5 minutes

  /**
   * Generate a new pairing code
   */
  generatePairingCode(): string {
    // Generate 6-digit numeric code
    const code = Math.floor(100000 + Math.random() * 900000).toString();

    const pairingCode: PairingCode = {
      code,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + this.CODE_EXPIRY_MS),
      used: false,
    };

    this.activeCodes.set(code, pairingCode);

    // Clean up expired codes
    this.cleanupExpiredCodes();

    console.log(`[PairingManager] Generated pairing code: ${code}`);
    return code;
  }

  /**
   * Validate a pairing code
   */
  validatePairingCode(code: string): boolean {
    const pairingCode = this.activeCodes.get(code);

    if (!pairingCode) {
      console.log(`[PairingManager] Invalid pairing code: ${code}`);
      return false;
    }

    if (pairingCode.used) {
      console.log(`[PairingManager] Pairing code already used: ${code}`);
      return false;
    }

    if (new Date() > pairingCode.expiresAt) {
      console.log(`[PairingManager] Pairing code expired: ${code}`);
      this.activeCodes.delete(code);
      return false;
    }

    // Mark as used
    pairingCode.used = true;
    console.log(`[PairingManager] Pairing code validated: ${code}`);

    return true;
  }

  /**
   * Validate a shared secret (for pre-approved nodes)
   */
  validateSharedSecret(secret: string): boolean {
    // Check if any approved node has this shared secret
    for (const node of this.approvedNodes.values()) {
      if (node.sharedSecret === secret) {
        console.log(`[PairingManager] Shared secret validated for node: ${node.nodeId}`);
        return true;
      }
    }

    console.log(`[PairingManager] Invalid shared secret`);
    return false;
  }

  /**
   * Approve a node (after pairing code validation)
   */
  approveNode(nodeId: string, name: string, sharedSecret?: string): void {
    const approvedNode: ApprovedNode = {
      nodeId,
      name,
      approvedAt: new Date(),
      sharedSecret,
    };

    this.approvedNodes.set(nodeId, approvedNode);
    console.log(`[PairingManager] Node approved: ${name} (${nodeId})`);
  }

  /**
   * Remove approval for a node
   */
  removeApproval(nodeId: string): void {
    this.approvedNodes.delete(nodeId);
    console.log(`[PairingManager] Node approval removed: ${nodeId}`);
  }

  /**
   * Check if a node is approved
   */
  isNodeApproved(nodeId: string): boolean {
    return this.approvedNodes.has(nodeId);
  }

  /**
   * Get all approved nodes
   */
  getApprovedNodes(): ApprovedNode[] {
    return Array.from(this.approvedNodes.values());
  }

  /**
   * Get active pairing code (if any)
   */
  getActivePairingCode(): string | null {
    // Return the first non-expired, non-used code
    for (const [code, pairingCode] of this.activeCodes.entries()) {
      if (!pairingCode.used && new Date() < pairingCode.expiresAt) {
        return code;
      }
    }
    return null;
  }

  /**
   * Clean up expired pairing codes
   */
  private cleanupExpiredCodes(): void {
    const now = new Date();
    for (const [code, pairingCode] of this.activeCodes.entries()) {
      if (now > pairingCode.expiresAt || pairingCode.used) {
        this.activeCodes.delete(code);
      }
    }
  }

  /**
   * Load approved nodes from persistence (for future use)
   */
  loadApprovedNodes(nodes: ApprovedNode[]): void {
    for (const node of nodes) {
      this.approvedNodes.set(node.nodeId, node);
    }
    console.log(`[PairingManager] Loaded ${nodes.length} approved nodes`);
  }

  /**
   * Get approved nodes for persistence (for future use)
   */
  getApprovedNodesForPersistence(): ApprovedNode[] {
    return this.getApprovedNodes();
  }
}

