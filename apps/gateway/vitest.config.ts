import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts', 'test/**/*.test.ts'],
    exclude: ['node_modules', 'dist', 'src/integration/**/*.test.ts'],

    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      exclude: [
        'node_modules/**',
        'dist/**',
        'test/**',
        '**/*.test.ts',
        '**/*.config.ts',
        '**/*.d.ts',
        '**/types/**',
        '**/types.ts',
        'src/index.ts',
        'src/cli.ts',
        'src/ui/**',
        '**/index.ts',
      ],
      thresholds: {
        // Sprint 2 target: 55%
        lines: 55,
        functions: 55,
        branches: 55,
        statements: 55,
      },
    },

    // Setup file for global mocks
    setupFiles: ['./test/setup.ts'],

    // Timeouts
    testTimeout: 10000,
    hookTimeout: 10000,

    // Enable type checking in tests
    typecheck: {
      enabled: true,
      tsconfig: './tsconfig.json',
    },

    // Pool configuration for parallel execution
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});

