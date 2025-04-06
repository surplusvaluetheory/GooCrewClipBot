# GooCrewClipBot

A Twitch bot that automatically creates clips when chat reactions reach a threshold.

## Features

- Monitors multiple Twitch channels simultaneously
- Creates clips when a threshold of reactions is detected in chat
- Posts the clip link in chat
- Configurable reaction keywords, thresholds, and cooldown periods
- Silent mode option for specific channels

## Requirements</u>

- Python 3.8+
- A Twitch account for the bot
- Authentication tokens from TwitchTokenGenerator

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
   # TwitchTokenGenerator credentials
   TWITCH_CLIENT_ID=your_client_id_from_twitchtokengenerator
   TWITCH_CLIENT_SECRET=your_client_secret_from_twitchtokengenerator
   TWITCH_ACCESS_TOKEN=your_access_token_from_twitchtokengenerator
   TWITCH_REFRESH_TOKEN=your_refresh_token_from_twitchtokengenerator
   
   # Bot configuration
   TWITCH_CHANNELS=channel1,channel2,channel3
   SILENT_CHANNELS=channel4,channel5
   REACTION_KEYWORDS=lol,lmao,+2,lmfao,haha,rofl,lul,kekw
   REACTION_WINDOW=30
   REACTION_THRESHOLD=10
   COOLDOWN_PERIOD=120
   
   ```

4. Run the bot:
   ```bash
   python GooCrewClipBot.py
   ```

## Authentication with TwitchTokenGenerator

1. This bot uses TwitchTokenGenerator for authentication:
   
   1. Visit [Twitch Token Generator](https://twitchtokengenerator.com/)
   2. Select "Custom Scope Token"
   3. Select the following scopes:
      - `chat:read`
      - `chat:edit`
      - `clips:edit`
      - `channel:read:subscriptions`
   4. Generate the token
   5. Copy the following information:
      - Client ID (shown at the top of the page)
      - Client Secret (also shown at the top)
      - Access Token
      - Refresh Token
   6. Add these to your `.env` file

## Configuration Options

- `TWITCH_CHANNELS`: Comma-separated list of channels to monitor and post in
- `SILENT_CHANNELS`: Comma-separated list of channels to monitor but not post in
- `REACTION_KEYWORDS`: Comma-separated list of keywords that count as reactions
- `REACTION_WINDOW`: Time window in seconds to count reactions
- `REACTION_THRESHOLD`: Number of reactions needed to trigger a clip
- `COOLDOWN_PERIOD`: Minimum time in seconds between clips for each channel

## Usage

The bot will automatically join the specified channels and monitor chat for reaction keywords. When the threshold of reactions is reached within the specified time window, it will create a clip and share the link in chat.

## Commands

- `!silence` - Silences the bot in the current channel until restart (can only be used by the channel owner or moderators)

## Token Expiration

The bot will check and display token expiration information when it starts. Twitch access tokens typically expire after a few hours, but the bot will automatically refresh them using the refresh token.

## Logging

The bot logs all activity to both the console and a file named `goocrew_clipbot.log`.

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

## License

MIT License

## Acknowledgements

- Built with [twitchAPI](https://github.com/Teekeks/pyTwitchAPI)
- Inspired by [libtron](https://twitch.tv/libtron) and the rest of the [Goo Crew community](https://www.twitch.tv/team/goocrew)
- Vibe coded with modified Claude 3.7 Sonnet model
- running on a Raspberry Pi 5 Model B Rev 1.0 8GB

---

Feel free to contribute to this project by submitting issues or pull requests!
