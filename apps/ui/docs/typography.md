# Typography System

## Overview

The AP3X-UI uses **Geist** font family by Vercel for a modern, professional tech platform aesthetic. This is the same font used by Vercel, Linear, and other leading tech companies.

## Font Stack

### Sans-Serif (UI Text)
**Primary**: Geist Sans (Variable Font)
- Weight range: 100-900
- Optimized for UI and readability
- Clean, modern geometric design
- Excellent legibility at all sizes

**Fallback chain**:
```
Geist Sans → -apple-system → BlinkMacSystemFont → Segoe UI → Roboto → Helvetica Neue → Arial → sans-serif
```

### Monospace (Code)
**Primary**: Geist Mono (Variable Font)
- Weight range: 100-900
- Designed for code and technical content
- Clear character distinction (0 vs O, 1 vs l vs I)
- Optimized ligatures for programming

**Fallback chain**:
```
Geist Mono → ui-monospace → SFMono-Regular → SF Mono → Menlo → Consolas → Liberation Mono → monospace
```

## Font Features

### OpenType Features Enabled
- `rlig` - Required ligatures
- `calt` - Contextual alternates
- `ss01` - Stylistic set 01

### Rendering Optimizations
- **Antialiasing**: Enabled for smooth rendering
- **Text rendering**: `optimizeLegibility`
- **Font smoothing**: Platform-specific optimizations

## Typography Scale

### Headings
All headings use:
- Font weight: 600 (Semi-bold)
- Letter spacing: -0.02em (tighter for better visual balance)

### Body Text
- Font weight: 400 (Regular)
- Letter spacing: -0.011em (subtle tightening for modern look)

### Code/Monospace
- Ligatures disabled for code clarity
- Contextual alternates disabled

## Usage in Components

### CSS Classes
```css
/* Sans-serif (default) */
.font-sans

/* Monospace */
.font-mono
```

### Tailwind Utilities
```jsx
// Regular text
<p className="font-sans">Regular text</p>

// Code/technical
<code className="font-mono">const example = true</code>

// Headings (automatically optimized)
<h1>Heading</h1>
```

## Font Files

Located in: `public/fonts/`
- `GeistVF.woff2` - Variable font for sans-serif (298KB)
- `GeistMonoVF.woff2` - Variable font for monospace (298KB)

## Benefits

✅ **Modern aesthetic** - Clean, professional look
✅ **Excellent readability** - Optimized for screens
✅ **Variable fonts** - Smooth weight transitions
✅ **Performance** - Only 2 font files, ~600KB total
✅ **Consistency** - Matches leading tech platforms
✅ **Accessibility** - High legibility at all sizes

## Comparison

### Before (Inter + JetBrains Mono)
- Good but generic
- Widely used (less distinctive)
- Heavier file sizes with multiple weights

### After (Geist + Geist Mono)
- Modern, distinctive
- Designed specifically for interfaces
- Single variable font files
- Better rendering at small sizes
- Tighter letter spacing for modern look

## Browser Support

Variable fonts are supported in:
- Chrome 62+
- Firefox 62+
- Safari 11+
- Edge 17+

Fallback fonts ensure compatibility with older browsers.

## Performance

- **WOFF2 format**: Best compression
- **Variable fonts**: Single file per family
- **Font display: swap**: Prevents FOIT (Flash of Invisible Text)
- **Preloaded**: Fonts load with initial page load

## Customization

To adjust font weights in your components:

```jsx
// Light
<p className="font-light">Light text (300)</p>

// Regular (default)
<p className="font-normal">Normal text (400)</p>

// Medium
<p className="font-medium">Medium text (500)</p>

// Semibold
<p className="font-semibold">Semibold text (600)</p>

// Bold
<p className="font-bold">Bold text (700)</p>
```

## Resources

- [Geist Font Repository](https://github.com/vercel/geist-font)
- [Vercel Design System](https://vercel.com/design)
- [Variable Fonts Guide](https://web.dev/variable-fonts/)

