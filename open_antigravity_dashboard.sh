#!/bin/bash
echo "Opening Antigravity Dashboard..."
# Try xdg-open (Linux), open (Mac), or start (Windows)
if command -v xdg-open &> /dev/null; then
    xdg-open output/antigravity_dashboard.html
elif command -v open &> /dev/null; then
    open output/antigravity_dashboard.html
else
    echo "Could not detect browser opener. Please open 'output/antigravity_dashboard.html' manually."
fi
