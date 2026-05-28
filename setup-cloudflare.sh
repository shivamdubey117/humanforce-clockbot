#!/bin/bash

# Cloudflare Pages Setup Script
# This script will configure your Cloudflare Pages deployment

echo "🚀 Cloudflare Pages Configuration Helper"
echo "========================================"
echo ""

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "⚠️  Wrangler CLI is not installed."
    echo "📦 Installing Wrangler CLI..."
    npm install -g wrangler
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install Wrangler. Please install manually:"
        echo "   npm install -g wrangler"
        exit 1
    fi
fi

echo "✅ Wrangler CLI is available"
echo ""

# Login to Cloudflare
echo "🔐 Logging into Cloudflare..."
echo "   (This will open a browser window for authentication)"
wrangler login

if [ $? -ne 0 ]; then
    echo "❌ Login failed. Please try again."
    exit 1
fi

echo ""
echo "✅ Logged in to Cloudflare"
echo ""

# Set environment variable
echo "🔧 Setting GITHUB_TOKEN environment variable..."
echo ""
read -sp "Enter your GitHub Personal Access Token: " GITHUB_TOKEN
echo ""

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ No token provided. Exiting."
    exit 1
fi

# Set for production
echo "Setting token for production environment..."
echo "$GITHUB_TOKEN" | wrangler pages secret put GITHUB_TOKEN --project-name=humanforce-clockbot

if [ $? -eq 0 ]; then
    echo "✅ Production environment variable set"
else
    echo "⚠️  Could not set production environment variable automatically"
    echo "   Please set it manually in Cloudflare dashboard"
fi

echo ""
echo "✅ Configuration complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Go to https://dash.cloudflare.com/"
echo "   2. Navigate to Pages → humanforce-clockbot → Settings → Builds & deployments"
echo "   3. Set Build command to: ./build.sh"
echo "   4. Click 'Save'"
echo "   5. Go to Deployments tab and click 'Retry deployment'"
echo ""
echo "🎉 Done! Your site should work after redeployment."
