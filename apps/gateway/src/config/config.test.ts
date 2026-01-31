import { describe, it, expect } from 'vitest';
import { loadConfig } from './loadConfig.js';

describe('Config Module', () => {
  it('should load config successfully', async () => {
    const config = await loadConfig();

    expect(config).toBeDefined();
    // Config structure is validated by the schema, so just check it loads
  });
});

