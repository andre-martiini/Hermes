---
name: Hermes Productivity Suite
colors:
  surface: '#ffffff'
  surface-dim: '#d3daea'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f3ff'
  surface-container: '#e7eefe'
  surface-container-high: '#e2e8f8'
  surface-container-highest: '#dce2f3'
  on-surface: '#151c27'
  on-surface-variant: '#4d4354'
  inverse-surface: '#2a313d'
  inverse-on-surface: '#ebf1ff'
  outline: '#7e7386'
  outline-variant: '#cfc2d7'
  surface-tint: '#861fdd'
  primary: '#7800ce'
  on-primary: '#ffffff'
  primary-container: '#9333ea'
  on-primary-container: '#f6e6ff'
  inverse-primary: '#ddb8ff'
  secondary: '#0058be'
  on-secondary: '#ffffff'
  secondary-container: '#2170e4'
  on-secondary-container: '#fefcff'
  tertiary: '#784700'
  on-tertiary: '#ffffff'
  tertiary-container: '#9a5c00'
  on-tertiary-container: '#ffe8d4'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#f0dbff'
  primary-fixed-dim: '#ddb8ff'
  on-primary-fixed: '#2c0051'
  on-primary-fixed-variant: '#6800b4'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffdcbc'
  tertiary-fixed-dim: '#ffb86b'
  on-tertiary-fixed: '#2c1700'
  on-tertiary-fixed-variant: '#683d00'
  background: '#f9fafb'
  on-background: '#151c27'
  surface-variant: '#dce2f3'
  border-subtle: '#f3f4f6'
  border-standard: '#e5e7eb'
  status-progress: '#9333ea'
  status-active: '#10b981'
  ai-accent: '#dbeafe'
  ai-text: '#2563eb'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  section-title:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.025em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-padding: 1.5rem
  column-gap: 1.5rem
  stack-gap-sm: 1rem
  stack-gap-md: 1.5rem
  header-height: 5rem
  sidebar-width: 20rem
---

## Brand & Style

The Hermes Productivity Suite is a high-performance workspace designed for legal and administrative professionals who manage complex, high-stakes workflows. The brand personality is **efficient, authoritative, and intelligent**. It balances a corporate foundation with the "spark" of AI-driven assistance.

The design style is **Corporate Modern**, characterized by a rigorous attention to hierarchy, a subdued but functional color palette, and a focus on clarity. It leverages a clean, structured multi-column layout to reduce cognitive load during information-heavy tasks. Subtle animations and high-fidelity typography lend the interface a premium, responsive feel.

## Colors

The palette is built on a "Soft Slate" foundation to prevent eye fatigue during long sessions. 

- **Primary (Purple):** Used for focus states, primary progress indicators, and interactive brand elements. It signifies action and momentum.
- **Secondary (Blue):** Reserved for AI-driven insights and strategic suggestions, differentiating machine logic from human input.
- **Neutral (Gray):** A sophisticated range of grays manages the information hierarchy, with `#f9fafb` acting as the canvas and `#111827` providing deep contrast for text.
- **Success (Emerald):** Used sparingly to denote system health and "Active" states.

## Typography

The system utilizes **Inter** exclusively for its utilitarian clarity and excellent legibility at small sizes. 

- **Hierarchy:** We use high-contrast weight changes (e.g., Bold for headers vs. Regular for body) rather than dramatic size changes to maintain a dense, information-rich environment.
- **Data Labels:** Small, uppercase labels with increased letter spacing are used for metadata and secondary categorization to keep the interface scannable.
- **Interactive Text:** Body text within interactive cards uses a 14px base for optimal readability.

## Layout & Spacing

The interface employs a **Fixed-Column Fluid Layout**. The dashboard is divided into three functional zones:
1.  **Context/Planning (320px Fixed):** Left-aligned utility panel.
2.  **Working Area (Flexible):** Central focus for primary content entry and viewing.
3.  **Assistance (320px Fixed):** Right-aligned AI-copilot and secondary information.

A rigorous **4px/8px grid** governs all internal element spacing. Standard section padding is 20px (`p-5`), creating enough internal whitespace to offset the high density of data.

## Elevation & Depth

Hierarchy is established through **Tonal Layering** and **Soft Ambient Shadows**.

- **Level 0 (Background):** `#f9fafb` creates the base canvas.
- **Level 1 (Cards/Panels):** Pure white (`#ffffff`) surfaces with a 1px border of `#f3f4f6`.
- **Shadows:** A signature `shadow-card` is used, utilizing two layers: a very soft, broad 6px blur with 5% opacity and a tighter 4px blur with 3% opacity. This makes panels feel grounded rather than floating.
- **Active Focus:** Elements currently being interacted with (like a focused input) utilize a subtle 1px ring in the primary color rather than increased shadow depth.

## Shapes

The shape language is **Modern Rounded**. 

- **Primary Panels:** Use `1rem` (rounded-2xl) to soften the rigid grid and make the application feel more approachable.
- **Component Level:** Buttons and input fields use `0.5rem` (rounded-lg) for a balanced, professional look.
- **Status Pills:** Use fully rounded (rounded-full) corners to clearly distinguish them from interactive buttons or cards.

## Components

### Buttons
- **Primary:** Solid background (`#9333ea`) with white text.
- **Ghost/Tertiary:** Bordered (`#e5e7eb`) with gray text, shifting to a soft gray background on hover.
- **AI Action:** Lavender background (`#f5f3ff`) with purple text and a subtle border.

### Input Fields
- Backgrounds use a slight off-white tint (`#f9fafb`) to separate from the white card surface.
- Labels are positioned above the field in uppercase `10px` semi-bold text.

### Progress Indicators
- Linear bars use a `6px` height with a gray-100 track and a primary purple fill.

### Checkboxes
- Custom `16px` squares with `4px` corner radius. When checked, they fill with the primary color and display a white checkmark.

### Cards
- Standard containers have `20px` internal padding, a 1px light gray border, and the signature ambient shadow.