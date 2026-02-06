"use client"

import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import { cn } from '@/lib/utils'
import { Terminal, Copy, Check } from 'lucide-react'

interface CodeBlockProps {
  code: string
  language?: string
  className?: string
}

export function CodeBlock({ code, language = '', className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Normalize language names
  const lang = language.toLowerCase()
  const langMap: Record<string, string> = {
    // JavaScript/TypeScript
    'ts': 'typescript',
    'tsx': 'tsx',
    'js': 'javascript',
    'jsx': 'jsx',
    // Python
    'py': 'python',
    'python3': 'python',
    // Shell
    'sh': 'bash',
    'shell': 'bash',
    'zsh': 'bash',
    // Web
    'htm': 'html',
    'html': 'markup',
    'xml': 'markup',
    'svg': 'markup',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',
    // Data formats
    'json': 'json',
    'json5': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    // Other common
    'md': 'markdown',
    'markdown': 'markdown',
    'sql': 'sql',
    'graphql': 'graphql',
    'gql': 'graphql',
    'dockerfile': 'docker',
    'docker': 'docker',
    'rust': 'rust',
    'rs': 'rust',
    'go': 'go',
    'golang': 'go',
    'c': 'c',
    'cpp': 'cpp',
    'c++': 'cpp',
    'csharp': 'csharp',
    'cs': 'csharp',
    'java': 'java',
    'rb': 'ruby',
    'ruby': 'ruby',
    'php': 'php',
    'swift': 'swift',
    'kotlin': 'kotlin',
    'kt': 'kotlin',
  }
  const normalizedLang = langMap[lang] || lang

  return (
    <div className={cn("relative group mb-3", className)}>
      {/* Header with language and copy button */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-3 py-2 z-10 bg-[#1a1a1a] rounded-t-lg border-b border-[#252525]">
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-text-muted" />
          {language && (
            <span className="text-[11px] text-text-muted uppercase tracking-wider font-medium">
              {language}
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-text-secondary transition-colors"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-green-500" />
              <span className="text-green-500">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      
      {/* Code content */}
      <div className="bg-[#0d1117] border border-[#252525] rounded-lg pt-10 pb-3 px-3 overflow-x-auto">
        <SyntaxHighlighter
          language={normalizedLang || 'text'}
          style={vscDarkPlus}
          customStyle={{
            background: 'transparent',
            padding: 0,
            margin: 0,
            fontSize: '13px',
            lineHeight: '1.6',
          }}
          codeTagProps={{
            style: {
              fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace',
            }
          }}
        >
          {code.trim()}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}

