# -*- coding: utf-8 -*-
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from datetime import datetime

# Add project root to Python path
sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "MassGen"
copyright = f"{datetime.now().year}, MassGen Team"
author = "MassGen Team"
release = "0.1.0"
version = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
]

# Add optional extensions if available
try:
    extensions.append("myst_parser")
except ImportError:
    print("Warning: myst_parser not installed. Markdown support disabled.")

try:
    extensions.append("sphinx_copybutton")
except ImportError:
    print("Warning: sphinx_copybutton not installed.")

try:
    extensions.append("sphinx_design")
except ImportError:
    print("Warning: sphinx_design not installed. Grid support disabled.")

try:
    extensions.append("hoverxref.extension")
except ImportError:
    print("Warning: sphinx-hoverxref not installed. Glossary tooltips disabled.")

# MyST parser configuration
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    # "linkify",  # Requires linkify-it-py package
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]

# Auto-generate heading anchors for deep linking
myst_heading_anchors = 3

# Configure heading slug generation to handle emojis better
myst_heading_slug_func = None  # Use default slugification

# Suppress duplicate label warnings for auto-generated TOC links
suppress_warnings = ["myst.header"]

# Configure MyST to parse markdown files
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
# Suppress MyST warnings for missing cross-references in markdown files
suppress_warnings = [
    "myst.xref_missing",  # Suppress missing cross-reference warnings in MyST
]

templates_path = ["_templates"]
exclude_patterns = []

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Try to use sphinx_book_theme, fall back to alabaster if not available
try:
    html_theme = "sphinx_book_theme"
except ImportError:
    html_theme = "alabaster"
    print("Warning: sphinx_book_theme not installed. Using alabaster theme.")
html_static_path = ["_static"]

# Custom CSS files
html_css_files = [
    "css/theme-images.css",
]

# Theme options
html_theme_options = {
    "logo": {
        "image_light": "_static/images/logo.png",
        "image_dark": "_static/images/logo-dark.png",
    },
    "logo_only": False,
    "display_version": True,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "style_nav_header_background": "#2980B9",
    # TOC options
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

# Logo and favicon (fallback if theme doesn't support logo dict)
# html_logo = "../../assets/logo.png"
# html_favicon = "../../assets/logo.png"
html_favicon = "../../assets/favicon.ico"

# Additional HTML context
html_context = {
    "display_github": True,
    "github_user": "Leezekun",
    "github_repo": "MassGen",
    "github_version": "main",
    "conf_py_path": "/docs/source/",
}

# Copy button configuration
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}

# Show todo notes
todo_include_todos = True

# Hoverxref configuration for glossary tooltips
hoverxref_auto_ref = True
hoverxref_domains = ["std"]
hoverxref_role_types = {
    "term": "tooltip",  # Show glossary terms as tooltips on hover
}
hoverxref_tooltip_maxwidth = 600
hoverxref_tooltip_theme = "tooltipster-shadow"
