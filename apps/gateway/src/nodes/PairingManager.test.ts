/**
 * Tests for PairingManager.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { PairingManager } from './PairingManager.js';

describe('PairingManager', () => {
  let pairingManager: PairingManager;

  beforeEach(() => {
    pairingManager = new PairingManager();
  });

  describe('Pairing Code Generation', () => {
    it('should generate 6-digit pairing code', () => {
      const code = pairingManager.generatePairingCode();

      expect(code).toBeDefined();
      expect(code).toHaveLength(6);
      expect(code).toMatch(/^\d{6}$/);
    });

    it('should generate unique codes', () => {
      const code1 = pairingManager.generatePairingCode();
      const code2 = pairingManager.generatePairingCode();

      // Very unlikely to be the same (1 in 900,000 chance)
      expect(code1).not.toBe(code2);
    });

    it('should return active pairing code', () => {
      const code = pairingManager.generatePairingCode();
      const activeCode = pairingManager.getActivePairingCode();

      expect(activeCode).toBe(code);
    });

    it('should return null when no active pairing code', () => {
      const activeCode = pairingManager.getActivePairingCode();

      expect(activeCode).toBeNull();
    });
  });

  describe('Pairing Code Validation', () => {
    it('should validate correct pairing code', () => {
      const code = pairingManager.generatePairingCode();
      const valid = pairingManager.validatePairingCode(code);

      expect(valid).toBe(true);
    });

    it('should reject invalid pairing code', () => {
      pairingManager.generatePairingCode();
      const valid = pairingManager.validatePairingCode('000000');

      expect(valid).toBe(false);
    });

    it('should reject already used pairing code', () => {
      const code = pairingManager.generatePairingCode();

      // Use it once
      pairingManager.validatePairingCode(code);

      // Try to use again
      const valid = pairingManager.validatePairingCode(code);

      expect(valid).toBe(false);
    });

    it('should reject expired pairing code', () => {
      vi.useFakeTimers();

      const code = pairingManager.generatePairingCode();

      // Advance time past expiry (5 minutes + 1 second)
      vi.advanceTimersByTime(5 * 60 * 1000 + 1000);

      const valid = pairingManager.validatePairingCode(code);

      expect(valid).toBe(false);

      vi.useRealTimers();
    });

    it('should accept code before expiry', () => {
      vi.useFakeTimers();

      const code = pairingManager.generatePairingCode();

      // Advance time but not past expiry (4 minutes)
      vi.advanceTimersByTime(4 * 60 * 1000);

      const valid = pairingManager.validatePairingCode(code);

      expect(valid).toBe(true);

      vi.useRealTimers();
    });
  });

  describe('Node Approval', () => {
    it('should approve node', () => {
      pairingManager.approveNode('node-1', 'Test Node');

      const approvedNodes = pairingManager.getApprovedNodes();

      expect(approvedNodes).toHaveLength(1);
      expect(approvedNodes[0]).toMatchObject({
        nodeId: 'node-1',
        name: 'Test Node',
      });
    });

    it('should approve node with shared secret', () => {
      pairingManager.approveNode('node-1', 'Test Node', 'secret-123');

      const approvedNodes = pairingManager.getApprovedNodes();

      expect(approvedNodes[0].sharedSecret).toBe('secret-123');
    });

    it('should check if node is approved', () => {
      pairingManager.approveNode('node-1', 'Test Node');

      expect(pairingManager.isNodeApproved('node-1')).toBe(true);
      expect(pairingManager.isNodeApproved('node-2')).toBe(false);
    });

    it('should remove node approval', () => {
      pairingManager.approveNode('node-1', 'Test Node');
      pairingManager.removeApproval('node-1');

      expect(pairingManager.isNodeApproved('node-1')).toBe(false);
      expect(pairingManager.getApprovedNodes()).toHaveLength(0);
    });
  });

  describe('Shared Secret Validation', () => {
    it('should validate correct shared secret', () => {
      pairingManager.approveNode('node-1', 'Test Node', 'secret-123');

      const valid = pairingManager.validateSharedSecret('secret-123');

      expect(valid).toBe(true);
    });

    it('should reject invalid shared secret', () => {
      pairingManager.approveNode('node-1', 'Test Node', 'secret-123');

      const valid = pairingManager.validateSharedSecret('wrong-secret');

      expect(valid).toBe(false);
    });

    it('should reject shared secret when no nodes approved', () => {
      const valid = pairingManager.validateSharedSecret('any-secret');

      expect(valid).toBe(false);
    });
  });
});

