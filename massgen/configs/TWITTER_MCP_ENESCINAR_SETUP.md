# Twitter MCP Server Setup Guide (EnesCinr/twitter-mcp)

## Overview
This guide explains how to set up the EnesCinr Twitter MCP server for use with MassGen and Claude Code.

## Prerequisites

### 1. Twitter Developer Account
1. Go to https://developer.twitter.com/
2. Sign up for a developer account if you don't have one
3. Create a new app in the developer portal
4. Generate your API credentials

### 2. Required API Credentials
You'll need four credentials from Twitter:
- **API Key**: Your app's API key
- **API Secret Key**: Your app's API secret key  
- **Access Token**: User access token for your app
- **Access Token Secret**: User access token secret

## Configuration

### 1. Update the Configuration File
Edit `claude_code_twitter_enescinar.yaml` and replace the placeholder values with your actual credentials:

```yaml
env:
  API_KEY: "your_actual_api_key"
  API_SECRET_KEY: "your_actual_api_secret_key"
  ACCESS_TOKEN: "your_actual_access_token"
  ACCESS_TOKEN_SECRET: "your_actual_access_token_secret"
```

### 2. Security Best Practices
- **Never commit credentials to Git**: Add the config file to `.gitignore` if it contains real credentials
- **Use environment variables**: Consider using system environment variables instead of hardcoding
- **Rotate keys regularly**: Regenerate your API keys periodically for security

## Available Features

### 1. Post Tweet
- Tool name: `mcp__twitter__post_tweet`
- Functionality: Post a new tweet to your Twitter account
- Parameters: Tweet text content

### 2. Search Tweets
- Tool name: `mcp__twitter__search_tweets`
- Functionality: Search for tweets based on a query
- Parameters: Search query string

## Usage with MassGen

To use this configuration with MassGen:

```bash
# Run with the EnesCinr Twitter MCP configuration
python -m massgen.api --config massgen/configs/claude_code_twitter_enescinar.yaml
```

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify all four credentials are correct
   - Check if your app has the necessary permissions (read/write)
   - Ensure your developer account is active

2. **Rate Limiting**
   - Twitter API has rate limits
   - Basic tier allows limited requests per 15-minute window
   - Consider upgrading your Twitter API access tier if needed

3. **MCP Server Not Found**
   - The server will be automatically downloaded via npx
   - Ensure you have Node.js and npm installed
   - Check internet connectivity

### Logs
Check MCP server logs for debugging:
- macOS: `~/Library/Logs/Claude/mcp-server-twitter.log`
- Windows: `%APPDATA%\Claude\logs\mcp-server-twitter.log`

## API Limits

### Free Tier (Essential)
- 500,000 tweets per month (read)
- 1,500 tweets per month (post)
- Rate limits apply

### Paid Tiers
- Basic: $100/month - Higher limits
- Pro: Custom pricing - Enterprise features

## References
- GitHub Repository: https://github.com/EnesCinr/twitter-mcp
- Twitter Developer Portal: https://developer.twitter.com/
- Twitter API Documentation: https://developer.twitter.com/en/docs