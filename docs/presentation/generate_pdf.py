#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate PDF from HTML presentation files using Chromium.
This script creates a temporary HTML file with all slides visible for PDF generation.
"""

import sys
import subprocess
import shutil
import re
from pathlib import Path
import tempfile


def prepare_html_for_pdf(html_path):
    """Create a modified HTML with all slides visible for PDF export."""
    
    html_content = html_path.read_text()
    
    # Inject CSS and JavaScript to show all slides for PDF
    pdf_styles = """
    <style id="pdf-export-styles">
        /* PDF Export Styles */
        @page {
            size: 11in 8.5in; /* Landscape Letter */
            margin: 0;
        }
        
        body {
            overflow: visible !important;
            margin: 0;
            padding: 0;
        }
        
        .slideshow-container {
            height: auto !important;
            overflow: visible !important;
            position: relative !important;
        }
        
        .slide {
            display: flex !important;
            position: relative !important;
            page-break-after: always !important;
            page-break-inside: avoid !important;
            page-break-before: auto !important;
            height: 8.5in !important;
            width: 11in !important;
            min-height: 8.5in !important;
            max-height: 8.5in !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        
        .slide:last-child {
            page-break-after: auto !important;
        }
        
        /* Hide navigation elements */
        .nav-buttons,
        .slide-menu,
        .menu-toggle {
            display: none !important;
        }
        
        /* Ensure backgrounds are visible */
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            color-adjust: exact !important;
        }
    </style>
    """
    
    # Add PDF styles before </head>
    html_content = html_content.replace('</head>', pdf_styles + '\n</head>')
    
    # Add script to show all slides after body loads
    pdf_script = """
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Show all slides
            const slides = document.querySelectorAll('.slide');
            slides.forEach(slide => {
                slide.classList.add('active');
                slide.style.display = 'flex';
            });
            
            console.log('Prepared ' + slides.length + ' slides for PDF export');
        });
    </script>
    """
    
    # Add script before </body>
    html_content = html_content.replace('</body>', pdf_script + '\n</body>')
    
    return html_content


def generate_pdf(html_file, output_file=None):
    """Generate PDF from HTML presentation using Chromium."""
    
    html_path = Path(html_file)
    if not html_path.exists():
        print(f"Error: HTML file not found: {html_file}")
        sys.exit(1)

    if output_file is None:
        output_file = html_path.with_suffix('.pdf')
    else:
        output_file = Path(output_file)

    # Find chromium or chrome
    chromium = shutil.which('chromium-browser') or shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('chrome')
    
    if not chromium:
        print("Error: Chromium/Chrome not found.")
        print("Please install chromium-browser or google-chrome.")
        sys.exit(1)

    print(f"Converting {html_path} to PDF...")
    print(f"Output: {output_file}")
    print(f"Using browser: {chromium}")

    # Create temporary HTML file with all slides visible
    print("Preparing HTML for PDF export...")
    pdf_html_content = prepare_html_for_pdf(html_path)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
        tmp_file.write(pdf_html_content)
        tmp_html_path = Path(tmp_file.name)
    
    try:
        # Chromium command line options for PDF generation
        cmd = [
            chromium,
            '--headless',
            '--disable-gpu',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--print-to-pdf=' + str(output_file.absolute()),
            '--no-pdf-header-footer',
            '--print-to-pdf-no-header',
            '--virtual-time-budget=10000',  # Give time for rendering
            'file://' + str(tmp_html_path.absolute())
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"Error generating PDF:")
            print(result.stderr)
            sys.exit(1)
            
        if output_file.exists():
            print(f"✅ PDF generated successfully: {output_file}")
            print(f"   Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("Error: PDF file was not created.")
            sys.exit(1)
            
    except subprocess.TimeoutExpired:
        print("Error: PDF generation timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Clean up temporary file
        if tmp_html_path.exists():
            tmp_html_path.unlink()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_pdf.py <html_file> [output_pdf]")
        print("Example: python generate_pdf.py m2l.html m2l.pdf")
        sys.exit(1)
    
    html_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    generate_pdf(html_file, output_file)
