import os
import asyncio
from typing import List, Set

from pyrogram import Client, types
from dotenv import load_dotenv

# ⬅️ IMPORT the new channel classes
from channels import SourceChannel, StorageChannel, TargetChannel
# ⬅️ IMPORT the Gemini client
from gemini import GeminiClient

# ----------------------------------------------------
# 1. CONFIGURATION AND INITIALIZATION
# ----------------------------------------------------
load_dotenv()

# Pyrogram Client setup
API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = str(os.getenv("TELEGRAM_API_HASH", ""))
SESSION_NAME = str(os.getenv("SESSION_NAME", "user_session"))

# Channel Configuration
SOURCE_CHANNEL_ID = os.getenv("SOURCE_CHANNEL", "")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL", "")
STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL", "")

# Polling Configuration
MAX_MESSAGES_TO_POLL = 5
POLLING_INTERVAL_SECONDS = 60 * 1  # 1 minute

# ----------------------------------------------------
# 2. THE REFACTORED PROCESSOR CLASS
# ----------------------------------------------------


class SignalProcessor:
    """
    The central orchestrator. It manages connections and delegates all
    specific tasks (I/O, Parsing) to specialized classes.
    """

    def __init__(self):

        # 1. Initialize Pyrogram Client
        self.app = Client(
            SESSION_NAME,
            api_id=API_ID,
            api_hash=API_HASH,
        )

        # 2. Initialize the specialized components (Dependency Injection)
        self.gemini_parser = GeminiClient()
        self.source_channel = SourceChannel(self.app, SOURCE_CHANNEL_ID)
        self.storage_channel = StorageChannel(self.app, STORAGE_CHANNEL_ID)
        self.target_channel = TargetChannel(self.app, TARGET_CHANNEL_ID)

        # 3. State tracking (set of processed message IDs)
        self.processed_ids: Set[int] = set()

    async def start(self):
        """Starts the Pyrogram client and loads initial state."""
        await self.app.start()
        print(f"Telegram Client Started successfully with session: {SESSION_NAME}")

        # Load state from the dedicated StorageChannel class
        self.processed_ids = await self.storage_channel.get_latest_messages()
        print(f"Loaded {len(self.processed_ids)} processed IDs.")

        # Start the continuous polling loop
        asyncio.create_task(self._polling_loop())

    async def stop(self):
        """Stops the Pyrogram client."""
        await self.app.stop()
        print("Telegram Client Stopped.")

    # --- Orchestration Logic ---

    async def _polling_loop(self):
        """Controls the timing and execution of the main processing loop."""
        while True:
            try:
                await self._process_new_messages()
            except Exception as ex:
                print(f"Error in polling loop: {ex}")

            await asyncio.sleep(POLLING_INTERVAL_SECONDS)

    async def _process_new_messages(self):
        """Fetches new messages and passes them to the handler."""
        print(f"Polling {SOURCE_CHANNEL_ID} for new messages...")

        # Delegation: The SourceChannel handles fetching and preliminary filtering
        raw_messages: List[types.Message] = await self.source_channel.get_latest_messages(
            limit=MAX_MESSAGES_TO_POLL
        )

        new_messages = [
            msg for msg in raw_messages
            if msg.id not in self.processed_ids
        ]

        # Process from oldest to newest
        for message in reversed(new_messages):
            await self._handle_message(message)

    async def _handle_message(self, message: types.Message):
        """
        Main pipeline: Parse -> Send -> Store ID.
        """

        # 1. Parse the message using the dedicated GeminiClient
        parsed_data = await self.gemini_parser.parse_signal_message(message.text)

        if parsed_data:
            message_id_str = str(message.id)

            if parsed_data.get("is_signal"):
                print(f"✨ Signal detected from ID {message.id}: {parsed_data.get('symbol')}")

                # 2. Send the signal using the dedicated TargetChannel
                await self.target_channel.save_message(parsed_data)

            else:
                print(f"➖ Message ID {message.id} is not a valid signal (is_signal=False).")

            # 3. Save the message ID using the dedicated StorageChannel
            await self.storage_channel.save_message(message_id_str)
            self.processed_ids.add(message.id)


# ----------------------------------------------------
# 3. MAIN ENTRY POINT
# ----------------------------------------------------
async def main():
    """
    The main asynchronous function that handles the entire bot lifecycle.
    """
    processor = SignalProcessor()

    try:
        print("Starting Signal Processor...")
        await processor.start()  # Await start, which launches the polling task

        # This is the correct way to keep the main task running indefinitely.
        # It waits for all other tasks (like the polling loop) to finish.
        # We create a sentinel Future that can be cancelled externally (e.g., by KeyboardInterrupt)
        # We don't need run_forever() on the loop itself.
        await asyncio.Future()

    except asyncio.CancelledError:
        # This is expected when the loop is shut down by Ctrl+C
        print("\nInterrupt received (CancelledError). Stopping gracefully...")
    except Exception as e:
        print(f"\nA fatal error occurred during runtime: {e}")
    finally:
        # This cleanup code runs within the same event loop context
        await processor.stop()
        print("Signal Processor stopped.")


if __name__ == "__main__":
    # Simplified setup for demonstration (Requires a .env file and Pyrogram setup)
    if not all([API_ID, API_HASH, SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID, STORAGE_CHANNEL_ID]):
        print("FATAL: Please set all required TELEGRAM and CHANNEL variables in your .env file.")
        exit()

    # asyncio.run() sets up the loop, runs the main() coroutine, and shuts down the loop.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This specifically catches Ctrl+C outside the loop's context
        # but the main() function's internal handling is usually cleaner.
        pass
