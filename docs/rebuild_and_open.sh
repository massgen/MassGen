#!/bin/bash
cd "$(dirname "$0")"
echo "Installing documentation dependencies..."
uv pip install -r requirements-docs.txt
echo "Cleaning and rebuilding documentation..."
rm -rf build/*
echo "Build directory cleaned."
uv run sphinx-build -M html source build
echo "Opening documentation in browser..."
open build/html/index.html
