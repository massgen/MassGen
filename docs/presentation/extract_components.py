#!/usr/bin/env python3
"""
Extract components from working presentations (m2l.html, columbia.html)
"""

import re
from pathlib import Path

def extract_slides_from_file(file_path):
    """Extract individual slides from a presentation file."""
    content = Path(file_path).read_text()
    
    # Find all slide boundaries
    slide_pattern = r'(<!-- Slide \d+: [^>]*>.*?)(?=<!-- Slide \d+:|<!-- Navigation -->|$)'
    slides = re.findall(slide_pattern, content, re.DOTALL)
    
    return slides

def extract_head_section(file_path):
    """Extract head section from presentation file."""
    content = Path(file_path).read_text()
    
    # Extract from <!DOCTYPE html> to end of <head>
    head_pattern = r'(<!DOCTYPE html>.*?</head>)'
    head_match = re.search(head_pattern, content, re.DOTALL)
    
    return head_match.group(1) if head_match else ""

def extract_navigation_section(file_path):
    """Extract navigation section from presentation file."""
    content = Path(file_path).read_text()
    
    # Extract from <!-- Navigation --> to </html>
    nav_pattern = r'(<!-- Navigation -->.*?</html>)'
    nav_match = re.search(nav_pattern, content, re.DOTALL)
    
    return nav_match.group(1) if nav_match else ""

def clean_slide_title(title):
    """Convert slide title to component filename."""
    # Remove HTML comments and clean up
    title = re.sub(r'<!-- Slide \d+: ', '', title)
    title = re.sub(r' -->', '', title)
    
    # Convert to filename
    title = title.lower()
    title = re.sub(r'[^\w\s-]', '', title)  # Remove special chars
    title = re.sub(r'\s+', '-', title)      # Replace spaces with hyphens
    title = re.sub(r'-+', '-', title)       # Remove multiple hyphens
    title = title.strip('-')                # Remove leading/trailing hyphens
    
    return f"slide-{title}"

def main():
    # Create components directory
    components_dir = Path("/Users/wangchi/Code/MassGen/docs/presentation/components")
    components_dir.mkdir(exist_ok=True)
    
    print("Extracting components from working presentations...")
    
    # Extract from m2l.html (this will be our base/generic version)
    m2l_slides = extract_slides_from_file("/Users/wangchi/Code/MassGen/docs/presentation/m2l.html")
    print(f"Found {len(m2l_slides)} slides in m2l.html")
    
    # Extract head and navigation
    head_content = extract_head_section("/Users/wangchi/Code/MassGen/docs/presentation/m2l.html")
    nav_content = extract_navigation_section("/Users/wangchi/Code/MassGen/docs/presentation/m2l.html")
    
    # Save head component (generic)
    (components_dir / "head.html").write_text(head_content)
    print("✅ Saved head.html")
    
    # Save navigation component 
    (components_dir / "navigation.html").write_text(nav_content)
    print("✅ Saved navigation.html")
    
    # Save each slide
    for i, slide in enumerate(m2l_slides, 1):
        # Extract slide title from comment
        title_match = re.search(r'<!-- Slide \d+: ([^>]*) -->', slide)
        if title_match:
            title = title_match.group(1).strip()
            filename = clean_slide_title(title)
        else:
            filename = f"slide-{i:02d}"
        
        # Clean up the slide content (remove extra whitespace)
        slide_content = slide.strip()
        
        # Save slide component
        (components_dir / f"{filename}.html").write_text(f"        {slide_content}")
        print(f"✅ Saved {filename}.html")
    
    print(f"\nExtracted {len(m2l_slides)} slides + head + navigation")
    print("Next: Extract Columbia-specific variants...")

if __name__ == "__main__":
    main()