# Cloudflare Pages Deployment Setup

## Environment Variables

Add the following environment variable in Cloudflare Pages:

1. Go to your Cloudflare Pages project dashboard
2. Navigate to **Settings** → **Environment variables**
3. Add:
   - **Variable name:** `GITHUB_TOKEN`
   - **Value:** Your GitHub Personal Access Token (stored in GitHub Secrets as `TOKEN_FOR_TEAM`)
   - **Environment:** Production and Preview

## Build Configuration

In your Cloudflare Pages project settings:

- **Build command:** `./build.sh`
- **Build output directory:** `/` (root directory)

This will generate `config.js` during build time with your GitHub token.

## Security Note

The `config.js` file is generated at build time and is NOT committed to the repository. The GitHub token is only exposed in the deployed site, not in source control.
