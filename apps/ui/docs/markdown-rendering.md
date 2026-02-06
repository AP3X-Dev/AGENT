# Markdown Rendering in Chat

## Overview

Agent messages in the AP3X-UI chat interface are rendered with **full Markdown support**, allowing for rich, formatted responses with emojis, code blocks, lists, tables, and more.

## Features

### ✅ Supported Markdown Elements

#### Text Formatting
- **Bold**: `**text**` or `__text__`
- *Italic*: `*text*` or `_text_`
- ~~Strikethrough~~: `~~text~~` (GFM)
- `Inline code`: `` `code` ``

#### Headings
```markdown
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
```

#### Lists
**Unordered:**
```markdown
- Item 1
- Item 2
  - Nested item
```

**Ordered:**
```markdown
1. First item
2. Second item
3. Third item
```

**Task Lists (GFM):**
```markdown
- [x] Completed task
- [ ] Pending task
```

#### Code Blocks
**Inline code:**
```markdown
Use `const variable = value` for constants
```

**Code blocks:**
````markdown
```javascript
function example() {
  return "Hello, World!"
}
```
````

#### Links & Images
```markdown
[Link text](https://example.com)
![Image alt text](https://example.com/image.png)
```

#### Blockquotes
```markdown
> This is a blockquote
> It can span multiple lines
```

#### Tables (GFM)
```markdown
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
```

#### Horizontal Rules
```markdown
---
```

#### Emojis
Native emoji support: 🎉 ✅ 🚀 💡 ⚡ 🎨 📝 🔧

## Implementation

### Libraries Used
- **react-markdown**: Core markdown rendering
- **remark-gfm**: GitHub Flavored Markdown support
- **rehype-raw**: HTML support in markdown

### Custom Styling

All markdown elements are styled to match the AP3X dark theme:

- **Headings**: Semibold, with appropriate spacing
- **Code blocks**: Dark background with syntax highlighting
- **Inline code**: Blue accent color
- **Links**: Blue with hover effects
- **Lists**: Proper indentation and spacing
- **Tables**: Bordered with alternating row colors
- **Blockquotes**: Left border with italic text

## Usage

### For Agent Responses

Simply return markdown-formatted text from the agent:

```typescript
// Agent response example
const response = `
# Task Complete! ✅

I've successfully updated the following files:

1. **chat-message.tsx** - Added markdown rendering
2. **globals.css** - Added markdown styles

## Features Added

- Full markdown support
- Emoji rendering 🎉
- Code syntax highlighting
- Tables and lists

\`\`\`typescript
// Example code block
const markdown = "works great!"
\`\`\`

> **Note**: All changes are backward compatible
`
```

### For User Messages

User messages are rendered as plain text (no markdown processing) to prevent formatting issues with user input.

## Styling Classes

### Custom Component Styles

```tsx
// Headings
h1: "text-2xl font-semibold mt-6 mb-3"
h2: "text-xl font-semibold mt-5 mb-2"
h3: "text-lg font-semibold mt-4 mb-2"

// Code
inline: "bg-surface-secondary px-1.5 py-0.5 rounded text-sm font-mono text-blue-300"
block: "bg-surface-secondary p-3 rounded-lg text-sm font-mono"

// Lists
ul: "list-disc list-inside mb-3 space-y-1 ml-2"
ol: "list-decimal list-inside mb-3 space-y-1 ml-2"
```

## Best Practices

### ✅ Do's
- Use emojis to make responses more engaging
- Use headings to structure long responses
- Use code blocks for code examples
- Use lists for step-by-step instructions
- Use tables for structured data
- Use blockquotes for important notes

### ❌ Don'ts
- Don't overuse formatting (keep it readable)
- Don't use HTML when markdown suffices
- Don't nest too many levels of lists
- Don't use very long code blocks (truncate if needed)

## Examples

### Example 1: Task Completion
```markdown
✅ **Task Complete!**

I've updated the following:
- Added markdown rendering
- Installed dependencies
- Updated documentation

Next steps:
1. Restart the dev server
2. Test the new features
3. Deploy to production
```

### Example 2: Code Explanation
```markdown
## Function Overview

The `renderMarkdown` function processes markdown:

\`\`\`typescript
function renderMarkdown(content: string) {
  return <ReactMarkdown>{content}</ReactMarkdown>
}
\`\`\`

**Key features:**
- GFM support
- Custom styling
- Emoji rendering
```

