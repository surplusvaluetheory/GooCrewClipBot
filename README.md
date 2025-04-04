# GooCrewClipBot

A Twitch bot that automatically creates clips when chat reactions reach a threshold. Perfect for capturing funny moments during streams without requiring manual clip creation.

## Features

- **Automatic Clip Creation**: Creates clips when chat reactions reach a configurable threshold
- **Reaction Monitoring**: Detects keywords like "lol", "lmao", "+2", etc. in chat messages
- **Stream Timestamp**: Includes the stream uptime in clip titles and chat messages
- **Silent Mode**: Option to create clips without sending messages to chat
- **Configurable Settings**: Customize reaction keywords, thresholds, cooldown periods, and more
- **Channel-Specific Settings**: Configure different behavior for different channels

## Requirements

- Python 3.7+
- A Twitch account for the bot
- Twitch Developer Application credentials

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/surplusvaluetheory/GooCrewClipBot.git
   cd GooCrewClipBot
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration or rename `sample.env` to `.env`:
   ```
   TWITCH_CLIENT_ID=your_client_id
   TWITCH_CLIENT_SECRET=your_client_secret
   TWITCH_CHANNELS=channel1,channel2
   SILENT_CHANNELS=channel3,channel4
   REACTION_KEYWORDS=lol,lmao,+2,lmfao,haha,rofl
   REACTION_WINDOW=30
   REACTION_THRESHOLD=10
   COOLDOWN_PERIOD=120
   ```

## Twitch Setup

1. Create a Twitch Developer Application at [dev.twitch.tv](https://dev.twitch.tv/console/apps)
  
2. Note your Client ID and Client Secret
  
3. Generate tokens using Twitch Token Generator:
  
     - Visit [Twitch Token Generator](https://twitchtokengenerator.com/) - Select "Custom Scope Token"
    
     - Select the following scopes:
    
          - `chat:read`
    
          - `chat:edit`
    
          - `clips:edit`
    
          - `channel:read:subscriptions`
    
     - Generate the token
    
     - Copy the Access Token and Refresh Token
    
4. Create a file named `twitch_tokens.json` with the following structure:
  
```JSON
{
    "access_token": "your_access_token",
    "refresh_token": "your_refresh_token",
    "expires_at": 1743926400.0
}
```
  

Note: The `expires_at` value should be a timestamp in the future (the example is for approximately 1 month from now)

5. Add your Client ID and Client Secret to your `.env` file

## Configuration Options

| Environment Variable | Description | Default |
| --- | --- | --- |
| `TWITCH_CLIENT_ID` | Your Twitch application client ID | Required |
| `TWITCH_CLIENT_SECRET` | Your Twitch application client secret | Required |
| `TWITCH_CHANNELS` | Comma-separated list of channels to monitor | Required |
| `SILENT_CHANNELS` | Channels where clips are created but no messages are sent | Empty |
| `REACTION_KEYWORDS` | Keywords that count as reactions | lol,lmao,+2,lmfao |
| `REACTION_WINDOW` | Time window (in seconds) to count reactions | 30  |
| `REACTION_THRESHOLD` | Number of reactions needed to trigger a clip | 10  |
| `COOLDOWN_PERIOD` | Minimum time (in seconds) between clips | 120 |

## Usage

1. Run the bot:
  
  ```Bash
  python GooCrewClipBot.py
  ```
2. The bot will use the tokens from your `twitch_tokens.json` file to authenticate.
  
3. The bot will join the specified channels and start monitoring chat for reactions.
  
4. When enough reactions are detected within the time window, the bot will create a clip and share the link in chat (unless the channel is in silent mode).
  

## Commands

- `!silence` - Silences the bot in the current channel until restart (can only be used by the channel owner or moderators)

## How It Works

1. The bot monitors chat messages in the specified channels.
2. When it detects a message containing one of the reaction keywords, it adds a timestamp to that channel's reaction list.
3. If enough reactions are detected within the configured time window, the bot checks if the channel is live.
4. If the channel is live, the bot waits 5 seconds (to capture the moment that caused the reactions) and then creates a clip.
5. Unless the channel is in silent mode, the bot sends a message to chat with the clip URL and the timestamp in the stream when it was created.

## Deployment

For 24/7 operation, consider running the bot on a server or using a service like:

- A Raspberry Pi
- AWS, Google Cloud, or Azure
- Heroku or similar PaaS

You can use tools like `systemd`, `supervisor`, or `pm2` to keep the bot running and restart it if it crashes.

## Troubleshooting

- **Authentication Issues**: If your tokens expire, you can either:
- Delete the `twitch_tokens.json` file and let the bot authenticate through the browser
- Generate new tokens using Twitch Token Generator and update your `twitch_tokens.json` file
- **Rate Limiting**: If you're monitoring many channels, you might hit Twitch API rate limits. Consider increasing cooldown periods.
- **Clip Creation Failures**: Ensure the bot account has proper permissions. Some channels may have clip creation restricted.

## License

MIT License

## Acknowledgements

- Built with [twitchAPI](https://github.com/Teekeks/pyTwitchAPI)
- Inspired by [libtron](https://twitch.tv/libtron) and the rest of the [Goo Crew community](https://www.twitch.tv/team/goocrew)

---

Feel free to contribute to this project by submitting issues or pull requests!
