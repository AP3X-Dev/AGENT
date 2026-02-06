# AP3X UI Style Guide

> A high-quality, sleek, modern dark UI inspired by VS Code's dark theme, adapted for an AI agent interface.

## Core Principles

### 1. **Dark-First Design (VS Code Theme)**
- Primary background: `#1E1E1E` (editor/main canvas)
- Secondary background: `#181818` (sidebar, activity bar, terminal)
- Surface/Title bar: `#1F1F1F`
- Elevated surfaces: `#2A2A2A` to `#2B2B2B`
- **Never use transparent/semi-transparent colored cards or tiles**

### 2. **VS Code-Inspired Aesthetics**
- Clean, minimal layouts with generous spacing
- Subtle borders and dividers (`#2A2A2A` to `#333333`)
- Smooth transitions and hover states
- Focus on content hierarchy, not decorative elements
- Blue accent for message bubbles (`#122E4E`)

### 3. **Typography**
- **Primary font**: Sora + system font fallback (clean, readable)
- **Monospace**: JetBrains Mono for code, file paths, thread IDs
- **Sizes**:
  - Large headings: `text-lg` (18px)
  - Body text: `text-sm` (14px)
  - Small text: `text-xs` (12px)
- **Weights**: Regular (400), Medium (500), Semibold (600)

## Color Palette

### Backgrounds
```css
--bg-primary: #111111;        /* Main background - unified dark */
--bg-surface: #111111;        /* Tab bar, toolbars - unified */
--bg-header: #111111;         /* Header/top bar - unified */
--bg-sidebar: #111111;        /* Sidebar - unified */
--bg-elevated: #1E1E1E;       /* Elevated cards, hover states */
--bg-input: #181818;          /* Input fields - slightly lighter */
--bg-card: #1E1E1E;           /* Task row cards */
--bg-accent: #122E4E;         /* Message bubble (blue) */
```

### Borders & Dividers
```css
--border-subtle: #2A2A2A;     /* Default borders */
--border-interactive: #333333; /* Hover borders */
```

### Text
```css
--text-primary: #F5F5F5;      /* Main text */
--text-secondary: #A0A0A0;    /* Secondary text */
--text-muted: #666666;        /* Disabled, placeholder */
--text-accent: #4FC3F7;       /* Accent text (light blue) */
```

### Accent Colors
```css
--accent-blue: #4FC3F7;       /* Primary accent (light blue) */
--accent-success: #4EC9B0;    /* Success states (VS Code teal-green) */
--accent-warning: #DCDCAA;    /* Warnings (VS Code yellow) */
--accent-error: #F14C4C;      /* Errors, destructive actions */
--accent-info: #4FC3F7;       /* Info states (light blue) */
```

## Component Patterns

### Buttons

#### Primary Button
```tsx
className="px-4 py-2 bg-[#4FC3F7] text-[#1E1E1E] rounded-md hover:bg-[#67D4FF] transition-colors font-medium"
```

#### Secondary Button
```tsx
className="px-3 py-1.5 bg-[#1E1E1E] border border-[#2A2A2A] text-text-secondary
           hover:bg-[#2A2A2A] hover:border-[#333333] hover:text-text-primary
           transition-colors rounded-md"
```

#### Danger Button
```tsx
className="px-3 py-1.5 bg-[#2A1A1A] border border-[#4A2A2A] text-[#F14C4C]
           hover:bg-[#3A1A1A] hover:border-[#5A2A2A] transition-colors rounded-md"
```

### Cards & Containers

**❌ NEVER DO THIS:**
```tsx
// NO transparent backgrounds, NO colored overlays
className="bg-blue-500/20 backdrop-blur-sm"  // ❌ WRONG
className="bg-gradient-to-r from-purple-500/30" // ❌ WRONG
```

**✅ ALWAYS DO THIS:**
```tsx
// Solid backgrounds with subtle borders
className="bg-[#1E1E1E] border border-[#2A2A2A] rounded-lg"
// Or for message bubbles with accent
className="bg-[#122E4E] rounded-lg"
```

### Input Fields
```tsx
className="w-full px-3 py-2 bg-[#1A1A1A] border border-[#2A2A2A]
           text-text-primary rounded-md
           focus:outline-none focus:ring-1 focus:ring-[#4FC3F7] focus:border-[#4FC3F7]
           placeholder:text-text-muted"
```

### Status Indicators

#### Thinking/Loading
```tsx
className="flex items-center gap-2 px-3 py-2 bg-[#1E1E1E] border border-[#2A2A2A] rounded-lg"
// Icon with animate-pulse
```

#### Approval Required
```tsx
className="bg-[#2A2A1E] border border-[#4A4A2A] rounded-lg"
// Warm, subtle yellow tint for warnings
```

## Layout Guidelines

### Spacing
- **Tight**: `gap-1` (4px) - Icon + text
- **Normal**: `gap-2` to `gap-3` (8-12px) - Related elements
- **Comfortable**: `gap-4` (16px) - Sections
- **Generous**: `gap-6` to `gap-8` (24-32px) - Major sections

### Borders & Dividers
- Use `border-[#2A2A2A]` for subtle separation
- Avoid heavy borders - keep them thin (`border` = 1px)
- Use dividers sparingly

### Rounded Corners
- **Small elements**: `rounded-md` (6px) - Buttons, inputs
- **Cards**: `rounded-lg` (8px) - Containers, modals
- **Large surfaces**: `rounded-xl` (12px) - Major panels

## Interactive States

### Hover
```tsx
hover:bg-[#2A2A2A]           // Background lightens slightly
hover:border-[#333333]       // Border becomes more visible
hover:text-text-primary      // Text becomes more prominent
```

### Active/Selected
```tsx
bg-[#2A2A2A]                 // Slightly elevated
border-[#4FC3F7]             // Accent border (light blue)
text-text-primary            // Full brightness
```

### Disabled
```tsx
opacity-50                   // Reduced opacity
cursor-not-allowed          // Visual feedback
pointer-events-none         // No interaction
```

## Animation & Transitions

### Standard Transition
```tsx
transition-colors duration-200
```

### Smooth Animations
- Use `animate-pulse` for loading states
- Use `animate-bounce` sparingly (only for attention-grabbing elements)
- Prefer subtle fade-ins over slide animations

## Icons

- Use **Lucide React** icons consistently
- Size: `h-4 w-4` (16px) for inline, `h-5 w-5` (20px) for standalone
- Color: Match text color (`text-text-secondary`, `text-text-primary`)

## Examples from Codebase

### Thread Header (Good Example)
```tsx
<div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2A2A2A] bg-[#1F1F1F]">
  <span className="text-xs text-text-muted font-mono">Thread: abc123...</span>
  <button className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs
                     bg-[#1E1E1E] border border-[#2A2A2A] text-text-secondary
                     hover:bg-[#2A2A2A] hover:border-[#333333] hover:text-text-primary">
    <Plus className="h-3.5 w-3.5" />
    <span>New</span>
  </button>
</div>
```

### Agent Status (Good Example)
```tsx
<div className="flex items-center gap-2 px-3 py-2 rounded-lg border
                bg-[#1E1E1E] border-[#2A2A2A]">
  <Brain className="h-4 w-4 text-[#A0A0A0] animate-pulse" />
  <span className="text-sm font-medium text-[#A0A0A0]">Thinking...</span>
</div>
```

### Message Bubble (Good Example - Blue Accent)
```tsx
<div className="bg-[#122E4E] rounded-lg p-3">
  <span className="text-sm text-[#F5F5F5]">AI response message...</span>
</div>
```

## Anti-Patterns to Avoid

❌ **Transparent colored backgrounds**
```tsx
bg-blue-500/20 backdrop-blur  // NO!
```

❌ **Gradients on cards**
```tsx
bg-gradient-to-br from-purple-500/30 to-blue-500/30  // NO!
```

❌ **Heavy shadows**
```tsx
shadow-2xl shadow-purple-500/50  // NO!
```

❌ **Neon/bright colors**
```tsx
text-cyan-400 border-pink-500  // NO! (unless for specific accent)
```

✅ **Use instead:**
- Solid backgrounds (`#1E1E1E`, `#1F1F1F`, `#181818`)
- Subtle borders (`#2A2A2A`)
- Muted text colors (`#A0A0A0`, `#666666`)
- Minimal, purposeful accents (`#4FC3F7`, `#4EC9B0`)

## Specific Component Guidelines

### Chat Messages
- User messages: Align right, `bg-[#1E1E1E]`, subtle border
- Assistant messages: Align left, `bg-[#122E4E]` (blue accent), no border
- System messages: Full width, `bg-[#1E1E1E]`, yellow accent for warnings

### Code Blocks
- Background: `bg-[#181818]`
- Border: `border-[#2A2A2A]`
- Syntax highlighting: Use muted colors (not neon)
- Font: JetBrains Mono, `text-sm`

### Modals & Overlays
- Backdrop: `bg-black/60` (only exception for transparency - for dimming)
- Modal: `bg-[#1E1E1E]` with `border-[#2A2A2A]`
- Max width: `max-w-2xl` for readability
- Padding: `p-6` for comfortable spacing

### Scrollbars
```css
/* Custom scrollbar styling */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
```

## Accessibility

- Maintain contrast ratio of at least 4.5:1 for text
- Use `focus:ring-1 focus:ring-[#4FC3F7]` for keyboard navigation
- Provide hover states for all interactive elements
- Use semantic HTML (`<button>`, `<nav>`, `<aside>`)

## Responsive Design

- Mobile: Single column, full width
- Tablet: Sidebar + main content
- Desktop: Full layout with generous spacing
- Breakpoints: Use Tailwind defaults (`sm:`, `md:`, `lg:`, `xl:`)

## File Organization

```
components/
├── features/
│   ├── chat/           # Chat-specific components
│   ├── editor/         # Code editor components
│   └── settings/       # Settings components
├── ui/                 # Reusable UI primitives
└── layout/            # Layout components
```

## Design Checklist

Before committing a new component, verify:

- [ ] Uses solid backgrounds (no transparent colors)
- [ ] Borders are `#2A2A2A` or `#333333`
- [ ] Text colors are from the palette (`text-primary`, `text-secondary`, `text-muted`)
- [ ] Hover states are defined
- [ ] Spacing is consistent with the guide
- [ ] Rounded corners use standard values (`rounded-md`, `rounded-lg`)
- [ ] Transitions are smooth (`transition-colors`)
- [ ] Component works in dark mode (our only mode)
- [ ] No gradients or glows on cards/containers
- [ ] Icons are from Lucide React

---

**Remember**: Less is more. VS Code's dark theme is clean, focused, and doesn't distract from the content. Our UI should do the same for the AI agent's output.

**When in doubt**: Look at VS Code's dark theme. If it doesn't fit, reconsider.
