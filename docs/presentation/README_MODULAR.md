# MassGen Modular Presentation System

## Overview

The presentation files have been modularized into reusable components to make maintenance easier and enable content reuse across different presentation formats (Columbia, M2L, AI Builders, etc.).

**Status: COMPLETE** - All 24 slides extracted from working presentations into modular components with presentation-specific variants and proper build system.

## Directory Structure

```
docs/presentation/
├── components/               # Modular slide components (24 slides + head + nav)
│   ├── head.html            # CSS styles and HTML head
│   ├── navigation.html      # Interactive navigation system  
│   ├── slide-title-m2l.html           # M2L-specific title
│   ├── slide-title-columbia.html      # Columbia-specific title
│   ├── slide-title-aibuilders.html    # AI Builders-specific title
│   ├── slide-the-problem.html         # Single-agent limitations
│   ├── slide-the-solution-multi-agent-collaboration.html
│   ├── slide-ag2-research-foundation.html
│   ├── slide-evidence-performance-gains.html
│   ├── slide-architecture.html
│   ├── slide-key-features-capabilities.html
│   ├── slide-tech-deep-dive-*.html    # 3 technical slides
│   ├── slide-context-sharing-*.html   # 3 context sharing slides
│   ├── slide-benchmarking-results.html
│   ├── slide-case-study-*.html        # 2 case study slides
│   ├── slide-coordination-strategy-research.html
│   ├── slide-evolution-from-v001.html
│   ├── slide-early-adopters.html
│   ├── slide-live-demo-examples.html
│   ├── slide-applications.html                       # Generic applications
│   ├── slide-columbia-research-applications.html     # Columbia-specific  
│   ├── slide-getting-started.html
│   ├── slide-roadmap-vision.html
│   ├── slide-call-to-action-m2l.html         # "Thank you M2L!"
│   ├── slide-call-to-action-columbia.html    # "Thank you Columbia DAPLab!"
│   └── slide-call-to-action-aibuilders.html  # "Thank you Arize & GitHub!"
├── build_presentation.py    # Build script
├── generate_pdf.py          # PDF export script
├── columbia.html           # Generated from components
├── m2l.html               # Generated from components  
├── m2l.pdf                # PDF export of m2l presentation
├── aibuilders.html        # Generated from components
└── README_MODULAR.md      # This file
```

## Usage

### Building a Presentation

```bash
cd docs/presentation
python build_presentation.py aibuilders
python build_presentation.py columbia
python build_presentation.py m2l
```

### Generating PDF Exports

Convert any HTML presentation to PDF format:

```bash
cd docs/presentation
python generate_pdf.py m2l.html          # Creates m2l.pdf
python generate_pdf.py m2l.html custom.pdf  # Custom output name
```

**Requirements**: The script uses Chromium/Chrome for PDF generation. It automatically:
- Shows all slides in the PDF
- Removes navigation elements
- Maintains all styling and backgrounds
- Creates landscape-oriented pages

### Creating New Components

1. Extract slide HTML into a new file in `components/`
2. Follow naming convention: `slide-[name].html`
3. Ensure proper HTML structure and styling
4. Update slide configuration in `build_presentation.py`

### Adding New Presentations

1. Create presentation-specific title slide: `slide-title-[name].html`
2. Add slide configuration to `build_presentation.py`
3. Build with: `python build_presentation.py [name]`

## Features

### ✅ Completed Components

- **Head component**: Complete CSS styling system
- **Navigation**: Interactive slide navigation with menu
- **Core slides**: Problem, Solution, AG2 Foundation, Evidence, Evolution
- **Title slides**: Columbia, M2L, AI Builders specific
- **Version updates**: All slides reflect v0.0.15 release

### 🔧 Component Features

- **Responsive design**: Mobile-friendly layouts
- **Interactive navigation**: Keyboard shortcuts, slide menu, progress bar
- **Dynamic content**: JavaScript auto-detects slide titles
- **Consistent styling**: Shared CSS across all presentations
- **Easy maintenance**: Update version info once in `slide-evolution.html`

### 🚀 Benefits Achieved

1. **Content Reuse**: Share common slides across presentations
2. **Easy Updates**: Change version info in one place  
3. **Better Git**: Smaller, focused diffs for changes
4. **Maintainable**: Each component is manageable size
5. **Flexible**: Mix and match slides per presentation

## Build Script Details

The `build_presentation.py` script:
- Loads components from `components/` directory
- Assembles them in presentation-specific order
- Uses placeholder for missing components
- Generates complete HTML with navigation
- Updates total slide count automatically

## Key Lessons & Patterns

### Component Naming Convention
- Use descriptive names: `slide-the-problem.html` not `slide-problem.html`
- Presentation-specific variants: `slide-title-m2l.html`, `slide-title-columbia.html`
- Event-specific endings: `slide-call-to-action-m2l.html` with "Thank you M2L!"

### Content Accuracy
- Extract from working presentations, never fabricate content
- Use accurate event details (M2L is in Split, Sep 11, 2025)
- Avoid made-up descriptions like "Data Science and AI Research"

### Build System
- `build_presentation.py` handles component assembly and navigation injection
- Presentation-specific slide configs define order and component variants
- Dynamic slide titles for navigation menu

## Example Component

```html
<!-- components/slide-example.html -->
<div class="slide">
    <div class="icon">🎯</div>
    <h2>Example Slide Title</h2>
    <p>Slide content here...</p>
</div>
```

The modular system is now ready for full deployment and extension!