import os
import time
import logging
from datetime import datetime, timedelta
import asyncio
import json
import aiohttp
import csv
from rapidfuzz import process, fuzz
from twitchAPI.twitch import Twitch
# Updated imports for newer twitchAPI versions
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage
from twitchAPI.helper import first
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("goocrew_clipbot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('GooCrewClipBot')

# Load environment variables
load_dotenv()
# Get credentials from environment
APP_ID = os.getenv('TWITCH_CLIENT_ID')
APP_SECRET = os.getenv('TWITCH_CLIENT_SECRET')  # We need this for the API initialization
ACCESS_TOKEN = os.getenv('TWITCH_ACCESS_TOKEN')
REFRESH_TOKEN = os.getenv('TWITCH_REFRESH_TOKEN')

USER_SCOPE = [
    AuthScope.CHAT_READ,
    AuthScope.CLIPS_EDIT,
    AuthScope.CHANNEL_READ_SUBSCRIPTIONS,
    AuthScope.CHAT_EDIT
]

# Get channels from environment (comma-separated list)
CHANNELS = [channel.strip().lower() for channel in os.getenv('TWITCH_CHANNELS', '').split(',') if channel.strip()]
if not CHANNELS:
    logger.error("No channels specified in TWITCH_CHANNELS environment variable")
    exit(1)

# Get silent channels from environment (comma-separated list)
SILENT_CHANNELS = [channel.strip().lower() for channel in os.getenv('SILENT_CHANNELS', '').split(',') if channel.strip()]
logger.info(f"Monitoring channels: {', '.join(CHANNELS)}")
logger.info(f"Silent channels (no chat messages): {', '.join(SILENT_CHANNELS)}")

# Combine all channels to monitor
ALL_CHANNELS = list(set(CHANNELS + SILENT_CHANNELS))

# Get reaction keywords from environment (comma-separated list)
REACTION_KEYWORDS = [keyword.strip().lower() for keyword in os.getenv('REACTION_KEYWORDS', 'lol,lmao,+2,lmfao').split(',')]
logger.info(f"Monitoring for reaction keywords: {', '.join(REACTION_KEYWORDS)}")

# Reaction tracking settings
REACTION_WINDOW = int(os.getenv('REACTION_WINDOW', '30'))  # seconds to count reactions
REACTION_THRESHOLD = int(os.getenv('REACTION_THRESHOLD', '10'))  # number of reactions needed to trigger a clip
COOLDOWN_PERIOD = int(os.getenv('COOLDOWN_PERIOD', '120'))  # seconds between clips to avoid spam
CLIP_DELAY = 5  # seconds to wait before creating a clip after threshold is reached

# Load settlements database
settlements = []

def load_settlements():
    """Load settlement data from CSV file"""
    global settlements
    try:
        with open('database.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            settlements = [{'label': row['settlementLabel'], 'link': row['wikiLink']} for row in reader]
        logger.info(f"✅ CSV loaded with {len(settlements)} settlements")
    except Exception as e:
        logger.error(f"Failed to load settlements database: {str(e)}")

# Load the database on startup
load_settlements()

def search_village(query):
    """Search for a village using fuzzy matching"""
    if not settlements:
        return None

    # Extract just the labels for searching
    labels = [s['label'] for s in settlements]

    # Use fuzzy matching to find best match
    result = process.extractOne(query, labels, scorer=fuzz.WRatio, score_cutoff=50)

    if result:
        matched_label, score, _ = result
        # Find the full settlement data
        for settlement in settlements:
            if settlement['label'] == matched_label:
                return settlement

    return None

# Channel-specific reaction tracking
class ChannelState:
    def __init__(self, is_silent=False):
        self.reaction_times = []
        self.last_clip_time = datetime.now() - timedelta(seconds=COOLDOWN_PERIOD)
        self.silence_mode = is_silent  # Whether to suppress chat messages

# Dictionary to track state for each channel
channel_states = {}
for channel in CHANNELS:
    channel_states[channel] = ChannelState(is_silent=False)
for channel in SILENT_CHANNELS:
    channel_states[channel] = ChannelState(is_silent=True)

# Global variables
twitch = None
chat = None
last_token_refresh = datetime.now()
# Track when the refresh token was last used with TwitchTokenGenerator
# Initialize with a date 30 days ago to ensure we refresh within 30 days
last_ttg_refresh = datetime.now() - timedelta(days=30)

def update_env_file(access_token, refresh_token):
    """Update the .env file with new tokens"""
    try:
        # Read the current .env file
        with open('.env', 'r') as f:
            lines = f.readlines()

        # Update the token lines
        new_lines = []
        for line in lines:
            if line.startswith('TWITCH_ACCESS_TOKEN='):
                new_lines.append(f'TWITCH_ACCESS_TOKEN={access_token}\n')
            elif line.startswith('TWITCH_REFRESH_TOKEN='):
                new_lines.append(f'TWITCH_REFRESH_TOKEN={refresh_token}\n')
            else:
                new_lines.append(line)

        # Write the updated content back to the .env file
        with open('.env', 'w') as f:
            f.writelines(new_lines)

        logger.info("Updated .env file with new tokens")
        return True
    except Exception as e:
        logger.error(f"Failed to update .env file: {str(e)}")
        return False

async def check_token_validity():
    """Check if the provided tokens are valid and get expiration info"""
    try:
        # Initialize a temporary Twitch instance to validate tokens
        temp_twitch = await Twitch(APP_ID, APP_SECRET)
        temp_twitch.auto_refresh_auth = False  # Disable auto refresh

        # Set the authentication with the tokens
        await temp_twitch.set_user_authentication(ACCESS_TOKEN, USER_SCOPE, REFRESH_TOKEN)

        # Try to make a simple API call to validate the token
        user = await first(temp_twitch.get_users())

        if user:
            # Token is valid, now get expiration info
            # We'll use the validate endpoint to get token info
            headers = {
                'Authorization': f'OAuth {ACCESS_TOKEN}'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get('https://id.twitch.tv/oauth2/validate', headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Extract expiration info
                        if 'expires_in' in data:
                            expires_in_seconds = data['expires_in']
                            expiration_date = datetime.now() + timedelta(seconds=expires_in_seconds)

                            # Format expiration date
                            formatted_date = expiration_date.strftime('%Y-%m-%d %H:%M:%S')
                            logger.info(f"Token is valid! Expires on: {formatted_date} (in {expires_in_seconds//86400} days, {(expires_in_seconds%86400)//3600} hours)")

                            # Also log the scopes
                            if 'scopes' in data:
                                logger.info(f"Token scopes: {', '.join(data['scopes'])}")

                            # Return both validity and expiration time
                            return True, expires_in_seconds
                        else:
                            logger.info("Token is valid, but couldn't determine expiration time")
                            return True, None
                    else:
                        logger.error(f"Failed to validate token: {response.status}")
                        return False, None

        await temp_twitch.close()
        return False, None
    except Exception as e:
        logger.error(f"Error checking token validity: {str(e)}")
        return False, None

async def refresh_with_twitchtokengenerator():
    """Refresh the token using TwitchTokenGenerator's refresh API"""
    global ACCESS_TOKEN, REFRESH_TOKEN, last_token_refresh, last_ttg_refresh

    try:
        logger.info("Refreshing token using TwitchTokenGenerator...")

        # Use TwitchTokenGenerator's refresh API
        refresh_url = f"https://twitchtokengenerator.com/api/refresh/{REFRESH_TOKEN}"

        async with aiohttp.ClientSession() as session:
            async with session.get(refresh_url) as response:
                if response.status == 200:
                    result = await response.json()

                    # Check if the refresh was successful
                    if result.get('success') == True:
                        # Extract the new tokens
                        token_data = result.get('token', {})
                        new_access_token = token_data.get('access_token')
                        new_refresh_token = token_data.get('refresh_token')

                        if new_access_token and new_refresh_token:
                            # Update global variables
                            ACCESS_TOKEN = new_access_token
                            REFRESH_TOKEN = new_refresh_token
                            last_token_refresh = datetime.now()
                            last_ttg_refresh = datetime.now()  # Update the TTG refresh timestamp

                            # Update the .env file
                            update_env_file(new_access_token, new_refresh_token)

                            # Update the twitch instance with the new tokens
                            if twitch:  # Only if twitch instance exists
                                await twitch.set_user_authentication(ACCESS_TOKEN, USER_SCOPE, REFRESH_TOKEN)

                            logger.info(f"Token refreshed with TwitchTokenGenerator at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            logger.info("Access token refreshed and refresh token updated with TwitchTokenGenerator")
                            return True
                        else:
                            logger.error("Failed to extract new tokens from TwitchTokenGenerator response")
                    else:
                        error_msg = result.get('message', 'Unknown error')
                        logger.error(f"TwitchTokenGenerator refresh failed: {error_msg}")
                else:
                    error_text = await response.text()
                    logger.error(f"TwitchTokenGenerator refresh failed: {response.status} - {error_text}")

                return False
    except Exception as e:
        logger.error(f"Error refreshing token with TwitchTokenGenerator: {str(e)}")
        return False

async def refresh_with_twitch_api():
    """Refresh the token directly using Twitch's OAuth API"""
    global ACCESS_TOKEN, REFRESH_TOKEN, last_token_refresh

    try:
        logger.info("Attempting to refresh token directly with Twitch API...")

        # Use the Twitch OAuth API to refresh the token
        async with aiohttp.ClientSession() as session:
            data = {
                'client_id': APP_ID,
                'client_secret': APP_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': REFRESH_TOKEN
            }

            async with session.post('https://id.twitch.tv/oauth2/token', data=data) as response:
                if response.status == 200:
                    result = await response.json()

                    # Update the tokens
                    new_access_token = result.get('access_token')
                    new_refresh_token = result.get('refresh_token')

                    if new_access_token and new_refresh_token:
                        # Update global variables
                        ACCESS_TOKEN = new_access_token
                        REFRESH_TOKEN = new_refresh_token
                        last_token_refresh = datetime.now()

                        # Update the .env file
                        update_env_file(new_access_token, new_refresh_token)

                        # Update the twitch instance with the new tokens
                        if twitch:  # Only if twitch instance exists
                            await twitch.set_user_authentication(ACCESS_TOKEN, USER_SCOPE, REFRESH_TOKEN)

                        logger.info(f"Token refreshed directly with Twitch API at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        logger.info("Access token refreshed and refresh token updated with Twitch API")
                        return True
                    else:
                        logger.error("Failed to get new tokens from Twitch API response")
                        return False
                else:
                    error_text = await response.text()
                    logger.error(f"Twitch API token refresh failed: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Error refreshing token with Twitch API: {str(e)}")
        return False

def print_token_renewal_instructions():
    """Print instructions for manually renewing tokens"""
    logger.error("===== TOKEN RENEWAL REQUIRED =====")
    logger.error("Your Twitch tokens have expired and automatic refresh failed.")
    logger.error("Please follow these steps to generate new tokens:")
    logger.error("")
    logger.error("1. Visit https://twitchtokengenerator.com/")
    logger.error("2. Select 'Custom Scope Token'")
    logger.error("3. Enter your Client ID and Client Secret")
    logger.error("4. Select the following scopes:")
    logger.error("   - chat:read")
    logger.error("   - chat:edit")
    logger.error("   - clips:edit")
    logger.error("   - channel:read:subscriptions")
    logger.error("5. Generate the token")
    logger.error("6. Copy the Access Token and Refresh Token")
    logger.error("7. Update your .env file with the new tokens")
    logger.error("")
    logger.error("After updating the .env file, restart the bot.")
    logger.error("=====================================")

async def scheduled_token_refresh():
    """Periodically refresh the token to ensure it never expires"""
    while True:
        try:
            # Wait for 1 hour between checks
            await asyncio.sleep(3600)  # 3600 seconds = 1 hour

            current_time = datetime.now()

            # Check if the access token is close to expiring
            headers = {
                'Authorization': f'OAuth {ACCESS_TOKEN}'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get('https://id.twitch.tv/oauth2/validate', headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Extract expiration info
                        if 'expires_in' in data:
                            expires_in_seconds = data['expires_in']

                            # If less than 2 hours left, refresh the token
                            if expires_in_seconds < 7200:  # 7200 seconds = 2 hours
                                logger.info(f"Token expires in {expires_in_seconds} seconds, refreshing...")
                                # Try direct Twitch API refresh first
                                twitch_api_success = await refresh_with_twitch_api()

                                # If direct refresh fails, try TwitchTokenGenerator as fallback
                                if not twitch_api_success:
                                    logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
                                    await refresh_with_twitchtokengenerator()
                            else:
                                logger.info(f"Token still valid for {expires_in_seconds//3600} hours, no refresh needed")
                    else:
                        # If validation fails, try direct Twitch API refresh first
                        logger.warning(f"Token validation failed, attempting direct refresh with Twitch API...")
                        twitch_api_success = await refresh_with_twitch_api()

                        # If direct refresh fails, try TwitchTokenGenerator as fallback
                        if not twitch_api_success:
                            logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
                            await refresh_with_twitchtokengenerator()

            # Check if it's been more than 30 days since our last refresh token update
            # This ensures we refresh the token at least every 30 days to reset the 60-day countdown
            days_since_last_refresh = (current_time - last_token_refresh).days
            if days_since_last_refresh >= 30:
                logger.info(f"It's been {days_since_last_refresh} days since the last token refresh")
                logger.info("Performing scheduled refresh to reset 60-day countdown")
                # Try direct Twitch API refresh first
                twitch_api_success = await refresh_with_twitch_api()

                # If direct refresh fails, try TwitchTokenGenerator as fallback
                if not twitch_api_success:
                    logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
                    await refresh_with_twitchtokengenerator()

        except Exception as e:
            logger.error(f"Error in scheduled token refresh: {str(e)}")
            # Try to refresh with direct Twitch API if there was an error
            try:
                twitch_api_success = await refresh_with_twitch_api()
                # If direct refresh fails, try TwitchTokenGenerator as fallback
                if not twitch_api_success:
                    logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
                    await refresh_with_twitchtokengenerator()
            except Exception as inner_e:
                logger.error(f"Failed to refresh token after error: {str(inner_e)}")

async def on_ready(ready_event: EventData):
    logger.info(f'Bot is ready!')

    # Join all channels
    for channel in ALL_CHANNELS:
        # Updated method name from join_channel to join_room
        await chat.join_room(channel)
        logger.info(f'Joined channel: {channel}')

async def on_message(msg: ChatMessage):
    try:
        # Get the channel name from the room object
        if hasattr(msg, 'room') and hasattr(msg.room, 'name'):
            channel = msg.room.name
            channel_lower = channel.lower()

            # Check if this is a channel we're monitoring
            if channel_lower in ALL_CHANNELS:
                # Check for silence command (as a regular message)
                if msg.text.lower().strip() == "!silence":
                    # Check if the sender is the channel owner or a moderator
                    if (hasattr(msg, 'author') and 
                        (msg.author.name.lower() == channel_lower or 
                         (hasattr(msg.author, 'is_mod') and msg.author.is_mod))):

                        state = channel_states[channel_lower]
                        was_silenced = state.silence_mode
                        state.silence_mode = True
                        logger.info(f"Silence mode activated for channel {channel}")

                        # Send a message that the bot will be silent
                        if not was_silenced:  # Only send if we weren't already silenced
                            try:
                                await chat.send_message(channel, "I'll be quiet until I'm restarted, but I'll still create clips!")
                            except Exception as e:
                                logger.error(f"Error sending silence message to {channel}: {str(e)}")
                    return

                # Check for !village command
                if msg.text.lower().startswith("!village "):
                    village_query = msg.text[9:].strip()  # Remove "!village " prefix

                    if not village_query:
                        if not channel_states[channel_lower].silence_mode:
                            await chat.send_message(channel, f"@{msg.user.name} Please specify a village name.")
                        return

                    # Search for the village
                    result = search_village(village_query)

                    if result:
                        response = f"@{msg.user.name} {result['label']}: {result['link']}"
                    else:
                        response = f"@{msg.user.name} Place not found."

                    # Send response (unless in silence mode)
                    if not channel_states[channel_lower].silence_mode:
                        try:
                            await chat.send_message(channel, response)
                            logger.info(f"Village lookup in {channel}: '{village_query}' -> {result['label'] if result else 'Not found'}")
                        except Exception as e:
                            logger.error(f"Error sending village response to {channel}: {str(e)}")
                    return

                # Check if message contains any reaction keywords
                message_lower = msg.text.lower()
                for keyword in REACTION_KEYWORDS:
                    if keyword in message_lower:
                        logger.info(f"Reaction detected in {channel}: {msg.text}")
                        await process_reaction(channel_lower)
                        break
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")

async def process_reaction(channel):
    # Get channel state
    state = channel_states[channel]

    current_time = datetime.now()
    state.reaction_times.append(current_time)

    # Remove reactions outside the time window
    state.reaction_times = [t for t in state.reaction_times if (current_time - t).total_seconds() <= REACTION_WINDOW]

    # Log reaction count
    if len(state.reaction_times) % 5 == 0:  # Log every 5 reactions to reduce spam
        logger.info(f'Channel {channel} - Current reaction count: {len(state.reaction_times)}')

    # Check if we should create a clip
    if len(state.reaction_times) >= REACTION_THRESHOLD:
        # Check if we're not in cooldown
        if (current_time - state.last_clip_time).total_seconds() >= COOLDOWN_PERIOD:
            logger.info(f'Channel {channel} - Reaction threshold reached! Checking if channel is live...')

            # Always update the last clip time to prevent spam attempts
            state.last_clip_time = current_time

            # Check if channel is live
            is_live = await check_if_live(channel)
            if is_live:
                logger.info(f'Channel {channel} is live! Waiting {CLIP_DELAY} seconds before creating clip...')

                # Wait for the specified delay before creating the clip
                await asyncio.sleep(CLIP_DELAY)

                logger.info(f'Channel {channel} - Creating clip now...')
                clip_success = await create_clip_and_share(channel)

                # Only reset reaction counter if clip was successful
                if clip_success:
                    state.reaction_times = []
                else:
                    # If clip failed, reduce the cooldown to allow another attempt sooner
                    # Set to 30 seconds instead of the full cooldown
                    state.last_clip_time = current_time - timedelta(seconds=COOLDOWN_PERIOD - 30)
                    logger.info(f"Channel {channel} - Clip creation failed, reducing cooldown to 30 seconds")
            else:
                logger.info(f'Channel {channel} is not live, cannot create clip')

async def check_if_live(channel):
    try:
        # Get user ID from channel name
        user = await first(twitch.get_users(logins=[channel]))
        if not user:
            logger.error(f"Could not find user ID for {channel}")
            return False

        # Check if stream is live - using a more robust approach
        try:
            # Try using first() with get_streams
            stream = await first(twitch.get_streams(user_id=[user.id]))
            return stream is not None
        except Exception as e:
            logger.error(f"Error in get_streams call: {str(e)}")

            # Alternative approach: iterate through the async generator
            is_live = False
            async for stream in twitch.get_streams(user_id=[user.id]):
                is_live = True
                break
            return is_live
    except Exception as e:
        logger.error(f"Error checking if channel {channel} is live: {str(e)}")
        return False

async def get_stream_uptime(channel):
    """Get the current uptime of the stream in HH:MM:SS format"""
    try:
        # Get user ID from channel name
        user = await first(twitch.get_users(logins=[channel]))
        if not user:
            return "Unknown"

        # Get stream info
        stream = await first(twitch.get_streams(user_id=[user.id]))
        if not stream:
            return "Unknown"

        # Calculate uptime
        started_at = stream.started_at
        current_time = datetime.now(started_at.tzinfo)
        uptime = current_time - started_at

        # Format as HH:MM:SS
        hours, remainder = divmod(uptime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    except Exception as e:
        logger.error(f"Error getting stream uptime: {str(e)}")
        return "Unknown"

async def create_clip_and_share(channel):
    try:
        # Get user ID from channel name
        user = await first(twitch.get_users(logins=[channel]))
        if not user:
            logger.error(f"Could not find user ID for {channel}")
            return False

        # Get stream uptime for clip title
        uptime = await get_stream_uptime(channel)
        clip_title = f"{channel} - {uptime}"

        # Create the clip
        try:
            # Create clip with a 60-second duration (the API will use the maximum allowed)
            clip_data = await twitch.create_clip(
                broadcaster_id=user.id,
                has_delay=True  # This adds a delay to capture more recent content
            )

            # Debug the clip data
            logger.debug(f"Clip data: {clip_data}")

            # Check if we got clip data
            if clip_data:
                # Handle different return types from the API
                if isinstance(clip_data, list) and len(clip_data) > 0:
                    clip_id = clip_data[0].id
                elif hasattr(clip_data, 'id'):
                    # If it's a single object with an id attribute
                    clip_id = clip_data.id
                else:
                    # Try to access it as a dictionary
                    clip_id = clip_data['id'] if isinstance(clip_data, dict) and 'id' in clip_data else None

                if not clip_id:
                    logger.error(f"Channel {channel} - Failed to extract clip ID from response: {clip_data}")
                    return False

                clip_url = f"https://clips.twitch.tv/{clip_id}"
                logger.info(f"Channel {channel} - Clip created successfully! ID: {clip_id}")
                logger.info(f"Clip will be available at: {clip_url}")

                # Send clip URL to chat with the timestamp, but only if not in silence mode
                if not channel_states[channel].silence_mode:
                    chat_message = f"Clip created at {uptime} into the stream! Watch it here: {clip_url}"
                    try:
                        await chat.send_message(channel, chat_message)
                    except Exception as e:
                        logger.error(f"Error sending clip message to {channel}: {str(e)}")

                # Twitch needs time to process the clip
                logger.info(f"Channel {channel} - Clip is processing and will be available shortly")
                return True
            else:
                logger.error(f"Channel {channel} - Failed to create clip - no data returned")
                return False
        except Exception as e:
            logger.error(f"Error in create_clip call: {str(e)}")
            # Log the full exception for debugging
            import traceback
            logger.error(traceback.format_exc())
            return False

    except Exception as e:
        logger.error(f"Error creating clip for channel {channel}: {str(e)}")
        return False

async def silence_command(cmd):
    channel = cmd.room.name.lower()
    if channel in channel_states:
        state = channel_states[channel]
        was_silenced = state.silence_mode
        state.silence_mode = True
        logger.info(f"Silence mode activated for channel {channel} via command")

        # Send a message that the bot will be silent
        if not was_silenced:  # Only send if we weren't already silenced
            try:
                await chat.send_message(channel, "I'll be quiet until I'm restarted, but I'll still create clips!")
            except Exception as e:
                logger.error(f"Error sending silence message to {channel}: {str(e)}")

async def main():
    global twitch, chat

    logger.info("Starting GooCrewClipBot...")

    # Validate credentials
    if not APP_ID or not APP_SECRET:
        logger.error("Missing Twitch Client ID or Client Secret. Please check your .env file.")
        return

    if not ACCESS_TOKEN or not REFRESH_TOKEN:
        logger.error("Missing Twitch Access Token or Refresh Token. Please check your .env file.")
        return

    # Check token validity and expiration
    logger.info("Checking token validity...")
    token_valid, expires_in_seconds = await check_token_validity()

    # If token is valid but expires soon (less than 3 hours), refresh it immediately
    if token_valid and expires_in_seconds is not None and expires_in_seconds < 10800:  # 10800 seconds = 3 hours
        logger.info(f"Token expires in {expires_in_seconds} seconds (less than 3 hours), refreshing immediately...")
        twitch_api_success = await refresh_with_twitch_api()

        if not twitch_api_success:
            logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
            await refresh_with_twitchtokengenerator()

        # Verify the token was refreshed successfully
        token_valid, _ = await check_token_validity()

    # If token is not valid, try to refresh it
    if not token_valid:
        logger.warning("Token validation failed, attempting direct refresh with Twitch API...")
        twitch_api_success = await refresh_with_twitch_api()

        # If direct refresh fails, try TwitchTokenGenerator as fallback
        if not twitch_api_success:
            logger.warning("Direct Twitch API refresh failed, trying TwitchTokenGenerator")
            ttg_success = await refresh_with_twitchtokengenerator()

            if not ttg_success:
                logger.error("All token refresh methods failed.")
                print_token_renewal_instructions()
                return

        # Check validity again after refresh
        token_valid, _ = await check_token_validity()
        if not token_valid:
            logger.error("Token still invalid after refresh. Please check your credentials.")
            print_token_renewal_instructions()
            return

    # Initialize Twitch API with client ID and secret
    twitch = await Twitch(APP_ID, APP_SECRET)

    # Define a token refresh callback
    async def token_refresh_callback(token, refresh_token):
        global ACCESS_TOKEN, REFRESH_TOKEN, last_token_refresh
        logger.info(f"Token refreshed by Twitch API at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Update global variables
        ACCESS_TOKEN = token
        REFRESH_TOKEN = refresh_token
        last_token_refresh = datetime.now()

        # Update the .env file with the new tokens
        update_env_file(token, refresh_token)

    # Set the token refresh callback
    twitch.token_refresh_callback = token_refresh_callback

    # Enable auto refresh to keep the token valid
    twitch.auto_refresh_auth = True

    # Set the authentication directly with the tokens
    await twitch.set_user_authentication(ACCESS_TOKEN, USER_SCOPE, REFRESH_TOKEN)

    # Verify authentication worked
    try:
        user = await first(twitch.get_users())
        if user:
            logger.info(f"Authenticated as: {user.display_name}")
        else:
            logger.error("Authentication failed: Could not retrieve user information")
            print_token_renewal_instructions()
            return
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        print_token_renewal_instructions()
        return

    # Initialize chat connection
    chat = await Chat(twitch)

    # Register event handlers
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)

    # Register the silence command
    chat.register_command('silence', silence_command)

    # Start the scheduled token refresh task
    refresh_task = asyncio.create_task(scheduled_token_refresh())

    # Start the bot
    chat.start()

    # Keep the bot running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    finally:
        # Cancel the refresh task
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass

        chat.stop()
        await twitch.close()

if __name__ == "__main__":
    asyncio.run(main())
