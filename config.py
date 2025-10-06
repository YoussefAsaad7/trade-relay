import os
import json # New import for loading JSON/List data
from dotenv import load_dotenv
from typing import List
# Load environment variables once
load_dotenv()

class ChannelUnitConfig:
    """A Value Object to hold the configuration for one Source-Storage pair."""
    def __init__(self, source: str, storage: str, target: str):
        self.source_channel = source
        self.storage_channel = storage
        self.target_channel = target

class BotConfig:
    """Centralized configuration class for the bot."""

    # --- Telegram Config ---
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", 0))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "user_session")

    # # --- Channel IDs/Usernames (Fallback to placeholders) ---
    # SOURCE_CHANNEL: str = os.getenv("SOURCE_CHANNEL", "@source_channel_placeholder")
    # TARGET_CHANNEL: str = os.getenv("TARGET_CHANNEL", "@target_channel_placeholder")
    # STORAGE_CHANNEL: str = os.getenv("STORAGE_CHANNEL", "@storage_channel_placeholder")

    # --- Polling and Rate Limits ---
    MAX_MESSAGES_TO_POLL: int = 5
    POLLING_INTERVAL_SECONDS: int = 60  # 1 minute

    # --- Gemini Config (Used in gemini_parser.py) ---
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", 'gemini-2.5-flash')

    # Note: GEMINI_API_KEY is read automatically by the SDK

    # --- Channel Processing Units ---
    # Load a JSON string from the environment that defines multiple channel pairs.
    # Example format in .env:
    # CHANNEL_UNITS='[{"source": "@ChannelA", "storage": "@StorageA", "target": "@TargetA"}, {"source": "@ChannelB", "storage": "@StorageB", "target": "@TargetB"}]'
    CHANNEL_UNITS_RAW: str = os.getenv("CHANNEL_UNITS", "[]")

    @classmethod
    def load_channel_units(cls) -> List[ChannelUnitConfig]:
        """Parses the raw JSON string into a list of config objects."""
        try:
            data = json.loads(cls.CHANNEL_UNITS_RAW)
            if not isinstance(data, list):
                raise ValueError("CHANNEL_UNITS must be a JSON array.")

            return [
                ChannelUnitConfig(
                    source=unit['source'],
                    storage=unit['storage'],
                    target=unit['target']
                )
                for unit in data
            ]
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise EnvironmentError(f"FATAL: Error loading CHANNEL_UNITS configuration: {e}")

    @classmethod
    def validate(cls):
        """Simple validation to ensure critical values are present."""
        critical_vars = {
            "API_ID": cls.API_ID,
            "API_HASH": cls.API_HASH
        }
        missing = [name for name, val in critical_vars.items() if not val]

        if missing:
            raise EnvironmentError(
                f"FATAL: Missing critical configuration variables: {', '.join(missing)}. Check your .env file.")

        units = cls.load_channel_units()
        if not units:
            raise EnvironmentError("FATAL: CHANNEL_UNITS configuration is empty. Define at least one channel unit.")