"use client"

import { useEffect, useState, useRef } from "react"
import { Loader2 } from "lucide-react"

// Define our code sequences
const CODE_SEQUENCES = [
  {
    status: "Adding the button",
    lines: [
      "function Button({ children, onClick, variant = 'primary' }) {",
      "  return (",
      "    <button",
      "      onClick={onClick}",
      "      className={`btn btn-${variant} rounded-md px-4 py-2`}>",
      "      {children}",
      "    </button>",
      "  );",
      "}",
    ],
  },
  {
    status: "Configuring styles",
    lines: [
      "const buttonStyles = {",
      "  primary: 'bg-blue-600 text-white hover:bg-blue-700',",
      "  secondary: 'bg-gray-200 text-gray-800 hover:bg-gray-300',",
      "  danger: 'bg-red-600 text-white hover:bg-red-700',",
      "  success: 'bg-green-600 text-white hover:bg-green-700',",
      "  outline: 'bg-transparent border border-current hover:bg-gray-100'",
      "}",
    ],
  },
  {
    status: "Setting up event handlers",
    lines: [
      "const handleClick = (event) => {",
      "  if (isLoading) return;",
      "  setIsLoading(true);",
      "  onClick?.(event);",
      "  setTimeout(() => setIsLoading(false), 1000);",
      "  analytics.track('button_clicked', { buttonId });",
      "}",
    ],
  },
]

const SyntaxHighlighter = ({ code }: { code: string }) => {
  const highlighted = code
    .replace(/"(.*?)"/g, '<span class="text-green-300">"$1"</span>')
    .replace(/'(.*?)'/g, "<span class=\"text-green-300\">'$1'</span>")
    .replace(
      /\b(function|return|const|let|var|if|else|export|default|import|from|new|async|await|=>)\b/g,
      '<span class="text-fuchsia-400">$1</span>',
    )
    .replace(/\b([A-Z][a-zA-Z0-9_]+)\b/g, '<span class="text-cyan-300">$1</span>')
    .replace(/({|})/g, '<span class="text-yellow-300">$1</span>')
    .replace(/($$|$$)/g, '<span class="text-purple-300">$1</span>')
    .replace(/(\[|\])/g, '<span class="text-orange-300">$1</span>')
    .replace(/(\w+)=/g, '<span class="text-sky-300">$1</span>=')
    .replace(/\b(\d+)\b/g, '<span class="text-amber-300">$1</span>')
    .replace(/(\/\/.*)/g, '<span class="text-gray-500">$1</span>')

  return <pre className="text-text-primary flex-1" dangerouslySetInnerHTML={{ __html: highlighted }} />
}

export default function LoadingState() {
  const [sequenceIndex, setSequenceIndex] = useState(0)
  const [visibleLines, setVisibleLines] = useState<Array<{ text: string; number: number }>>([])
  const [scrollPosition, setScrollPosition] = useState(0)
  const codeContainerRef = useRef<HTMLDivElement>(null)
  const lineHeight = 24 // Approximate line height in pixels

  const currentSequence = CODE_SEQUENCES[sequenceIndex]
  const totalLines = currentSequence.lines.length

  // Initialize visible lines
  useEffect(() => {
    const initialLines = []
    for (let i = 0; i < Math.min(5, totalLines); i++) {
      initialLines.push({
        text: currentSequence.lines[i],
        number: i + 1,
      })
    }
    setVisibleLines(initialLines)
    setScrollPosition(0)
  }, [sequenceIndex, currentSequence.lines, totalLines])

  // Handle line advancement
  useEffect(() => {
    const advanceTimer = setInterval(() => {
      // Get the current first visible line index
      const firstVisibleLineIndex = Math.floor(scrollPosition / lineHeight)
      const nextLineIndex = (firstVisibleLineIndex + 3) % totalLines

      // If we're about to wrap around, move to next sequence
      if (nextLineIndex < firstVisibleLineIndex && nextLineIndex !== 0) {
        setSequenceIndex((prevIndex) => (prevIndex + 1) % CODE_SEQUENCES.length)
        return
      }

      // Add the next line if needed
      if (nextLineIndex >= visibleLines.length && nextLineIndex < totalLines) {
        setVisibleLines((prevLines) => [
          ...prevLines,
          {
            text: currentSequence.lines[nextLineIndex],
            number: nextLineIndex + 1,
          },
        ])
      }

      // Scroll to the next line
      setScrollPosition((prevPosition) => prevPosition + lineHeight)
    }, 1500)

    return () => clearInterval(advanceTimer)
  }, [scrollPosition, visibleLines, totalLines, sequenceIndex, currentSequence.lines, lineHeight])

  // Apply scroll position
  useEffect(() => {
    if (codeContainerRef.current) {
      codeContainerRef.current.scrollTop = scrollPosition
    }
  }, [scrollPosition])

  return (
    <div className="flex h-full w-full items-center justify-center bg-primary-background">
      <div className="w-full max-w-xl space-y-4 p-4">
        {/* Status line with spinner */}
        <div className="flex items-center space-x-3 font-medium text-text-secondary">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>{currentSequence.status}...</span>
        </div>

        {/* Code display with line numbers */}
        <div className="relative">
          <div
            ref={codeContainerRef}
            className="relative h-[72px] w-full overflow-hidden font-mono text-sm"
            style={{ scrollBehavior: "smooth" }}
          >
            <div>
              {visibleLines.map((line, index) => (
                <div key={index} className="flex h-[24px]">
                  {/* Line number */}
                  <div className="w-8 select-none pr-4 text-right text-text-muted">{line.number}</div>

                  {/* Code content */}
                  <SyntaxHighlighter code={line.text} />
                </div>
              ))}
            </div>
          </div>

          {/* Linear gradient overlay */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "linear-gradient(to bottom, rgba(10, 10, 10, 0.9) 0%, rgba(10, 10, 10, 0.5) 30%, rgba(10, 10, 10, 0) 100%)",
              zIndex: 10,
            }}
          />
        </div>
      </div>
    </div>
  )
}
