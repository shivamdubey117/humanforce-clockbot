#!/bin/bash
# Cloudflare Pages build script
# Creates config.js with GitHub token from environment variable

echo "window.GITHUB_TOKEN = '$GITHUB_TOKEN';" > config.js
echo "✅ config.js created with GitHub token"
