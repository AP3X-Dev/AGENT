# Scrollbar Styling

## Overview

The AP3X-UI features sleek, thin scrollbars that provide a modern, unobtrusive scrolling experience throughout the application.

## Design Specifications

### Dimensions
- **Width/Height**: 6px (thin and minimal)
- **Border radius**: 3px (rounded for smooth appearance)

### Colors

#### Dark Mode (Default)
- **Track**: Transparent (invisible)
- **Thumb (default)**: `rgba(255, 255, 255, 0.2)` - 20% white
- **Thumb (hover)**: `rgba(255, 255, 255, 0.3)` - 30% white
- **Thumb (active)**: `rgba(255, 255, 255, 0.4)` - 40% white

#### Light Mode
- **Track**: Transparent (invisible)
- **Thumb (default)**: `rgba(0, 0, 0, 0.2)` - 20% black
- **Thumb (hover)**: `rgba(0, 0, 0, 0.3)` - 30% black
- **Thumb (active)**: `rgba(0, 0, 0, 0.4)` - 40% black

### Transitions
- **Smooth color transitions**: 0.2s ease on hover/active states
- **Subtle appearance**: Only visible when needed

## Browser Support

### Firefox
Uses standard `scrollbar-width` and `scrollbar-color` properties:
```css
scrollbar-width: thin;
scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
```

### Webkit Browsers (Chrome, Safari, Edge)
Uses `-webkit-scrollbar` pseudo-elements:
```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.2); }
```

## Implementation

### Global Styles
Located in `app/globals.css`:
- Applied to all scrollable elements via `*` selector
- Automatic dark/light mode switching
- Smooth transitions on interaction

### ScrollArea Component
Located in `components/ui/scroll-area.tsx`:
- Radix UI ScrollArea primitive
- Custom thumb styling: `bg-white/20 hover:bg-white/30`
- Reduced width from `w-2.5` (10px) to `w-1.5` (6px)
- Smooth color transitions

## Features

✅ **Minimal footprint** - Only 6px wide, doesn't intrude on content
✅ **Transparent track** - Blends seamlessly with background
✅ **Hover feedback** - Brightens on hover for better visibility
✅ **Active state** - Further brightens when dragging
✅ **Smooth transitions** - 0.2s ease for polished feel
✅ **Auto-hiding** - Only visible when scrolling or hovering
✅ **Cross-browser** - Works in all modern browsers

## Usage

Scrollbars are automatically styled throughout the application. No additional classes or configuration needed.

### Standard Scrollable Elements
```jsx
// Any element with overflow will have styled scrollbars
<div className="overflow-y-auto">
  {/* Content */}
</div>
```

### ScrollArea Component
```jsx
import { ScrollArea } from '@/components/ui/scroll-area'

<ScrollArea className="h-[400px]">
  {/* Content */}
</ScrollArea>
```

## Customization

To override scrollbar styles for specific elements:

```css
.custom-scrollbar::-webkit-scrollbar {
  width: 8px; /* Wider scrollbar */
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 255, 136, 0.3); /* Custom color */
}
```

## Accessibility

- **Keyboard navigation**: Unaffected by custom scrollbar styling
- **Screen readers**: Standard scrolling behavior maintained
- **Touch devices**: Native touch scrolling preserved
- **High contrast**: Scrollbars remain visible in high contrast modes

## Performance

- **CSS-only**: No JavaScript overhead
- **Hardware accelerated**: Smooth scrolling on all devices
- **Minimal repaints**: Transitions use GPU acceleration

## Comparison

### Before
- Default browser scrollbars (12-16px wide)
- Inconsistent across browsers
- Visually heavy and distracting

### After
- Thin, consistent 6px scrollbars
- Unified appearance across browsers
- Subtle, modern aesthetic
- Better use of screen space

## Best Practices

1. **Don't override globally** - The default styling works for most cases
2. **Test on multiple browsers** - Ensure consistency
3. **Consider touch devices** - Thin scrollbars are harder to grab on mobile
4. **Maintain contrast** - Ensure scrollbars are visible when needed

## Resources

- [MDN: CSS Scrollbars](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Scrollbars)
- [Webkit Scrollbar Styling](https://webkit.org/blog/363/styling-scrollbars/)
- [Radix UI ScrollArea](https://www.radix-ui.com/primitives/docs/components/scroll-area)

