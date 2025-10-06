import asyncio
from typing import List, Set

from pyrogram import Client, types

# ⬅️ NEW: Import the config class
from config import BotConfig, ChannelUnitConfig
# ⬅️ IMPORT the new channel classes
from channels import SourceChannel, StorageChannel, TargetChannel
# ⬅️ IMPORT the Gemini client
from gemini import GeminiClient


# ----------------------------------------------------
# 2. THE REFACTORED PROCESSOR CLASS
# ----------------------------------------------------

class ProcessingUnit:
    """Encapsulates all components required to process one channel unit."""

    def __init__(self, config: ChannelUnitConfig, app: Client, parser: GeminiClient):
        self.config = config
        self.source_channel = SourceChannel(app, config.source_channel)
        self.storage_channel = StorageChannel(app, config.storage_channel)
        self.target_channel = TargetChannel(app, config.target_channel)
        self.gemini_parser = parser
        self.processed_ids: Set[int] = set()

    async def initialize_state(self):
        """Loads processed IDs for this specific unit."""
        self.processed_ids = await self.storage_channel.get_latest_messages()
        print(f"[{self.config.source_channel}] Loaded {len(self.processed_ids)} processed IDs.")

    async def process(self):
        """Processes new messages for this unit."""
        print(f"Polling {self.config.source_channel} for new messages...")

        # Fetch, filter, and process messages as before, using self.processed_ids
        raw_messages = await self.source_channel.get_latest_messages(limit=BotConfig.MAX_MESSAGES_TO_POLL)

        new_messages = [msg for msg in raw_messages if msg.id not in self.processed_ids]

        for message in reversed(new_messages):
            # The core logic is delegated to a new method for clarity
            await self._handle_single_message(message)

    async def _handle_single_message(self, message: types.Message):
        """Handles the logic pipeline for a single message."""
        parsed_data = await self.gemini_parser.parse_signal_message(message.text)

        if parsed_data:
            message_id_str = str(message.id)

            if parsed_data.get("is_signal"):
                print(f"[{self.config.source_channel}] ✨ Signal detected ID {message.id}: {parsed_data.get('symbol')}")
                await self.target_channel.save_message(parsed_data)
            else:
                print(f"[{self.config.source_channel}] ➖ Message ID {message.id} is not a valid signal.")

            # Always save the ID to storage channel specific to this unit
            await self.storage_channel.save_message(message_id_str)
            self.processed_ids.add(message.id)


class SignalProcessor:
    """
    The central orchestrator, managing a list of independent ProcessingUnits.
    """

    def __init__(self, app: Client, gemini_parser: GeminiClient, channel_unit_configs: List[ChannelUnitConfig]):
        self.app = app
        # The parser can be shared across all units (it's stateless)
        self.shared_parser = gemini_parser

        # Initialize a list of ProcessingUnit objects
        self.units: List[ProcessingUnit] = [
            ProcessingUnit(config, app, gemini_parser)
            for config in channel_unit_configs
        ]

    async def start(self):
        await self.app.start()
        print(f"Telegram Client Started successfully with session: {BotConfig.SESSION_NAME}")

        # Initialize state for all units concurrently
        init_tasks = [unit.initialize_state() for unit in self.units]
        await asyncio.gather(*init_tasks)  # Use asyncio.gather for parallel state loading

        asyncio.create_task(self._polling_loop())

    async def stop(self):
        """Stops the Pyrogram client."""
        await self.app.stop()
        print("Telegram Client Stopped.")

    # --- Orchestration Logic ---

    async def _polling_loop(self):
        """Polls all processing units concurrently."""
        while True:
            print("-" * 50)
            print(f"Starting concurrent poll cycle for {len(self.units)} units...")

            # Create a task for processing each unit
            processing_tasks = [unit.process() for unit in self.units]

            # Run all tasks in parallel
            await asyncio.gather(*processing_tasks)

            print(f"Cycle complete. Waiting {BotConfig.POLLING_INTERVAL_SECONDS} seconds.")
            await asyncio.sleep(BotConfig.POLLING_INTERVAL_SECONDS)


# ----------------------------------------------------
# 3. MAIN ENTRY POINT
# ----------------------------------------------------
async def main():
    """
    The main asynchronous function that handles the entire bot lifecycle.
    """
    # 1. Validate Configuration
    try:
        BotConfig.validate()
    except EnvironmentError as e:
        print(e)
        exit()

    # 2. Setup Pyrogram Client
    pyrogram_client = Client(
        BotConfig.SESSION_NAME,
        api_id=BotConfig.API_ID,
        api_hash=BotConfig.API_HASH,
    )

    # 3. Setup Dependencies
    gemini_parser = GeminiClient(model_name=BotConfig.GEMINI_MODEL)  # Pass model from config


    channel_unit_configs = BotConfig.load_channel_units()
    # 4. Instantiate Processor by Injecting Dependencies
    processor = SignalProcessor(
        app=pyrogram_client,
        gemini_parser=gemini_parser,
        channel_unit_configs=channel_unit_configs
    )

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

    # asyncio.run() sets up the loop, runs the main() coroutine, and shuts down the loop.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This specifically catches Ctrl+C outside the loop's context
        # but the main() function's internal handling is usually cleaner.
        pass
