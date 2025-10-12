import asyncio
from typing import List, Set, Dict, Any, Optional

from pyrogram import Client, types

from config import BotConfig, ChannelUnitConfig
from channels import SourceChannel, StorageChannel, TargetChannel
from mt5_manager import MT5Client
from formatter import SignalFormatter
from gemini import GeminiClient


class Trade:
    """A Value Object to hold the state of an active trade."""

    def __init__(self, message_id: int, data: Dict[str, Any], current_price: float):
        self.message_id = message_id  # Original Telegram message ID
        self.symbol = data['symbol']
        self.entry = data['entry_price']
        self.sl = data['sl']
        self.tp1 = data.get('tp1')
        self.tp2 = data.get('tp2')
        self.direction = SignalFormatter.determine_direction(self.entry, self.sl)
        self.status = "PENDING_ENTRY"
        self.tp1_hit = False  # Track if TP1 was reached
        self.entry_executed_price: Optional[float] = None  # Price when entry was hit
        self.entry_confirmation_count = 0
        self.signal_price = current_price  # 👈 Market price when signal arrived
        self.waiting_for_pullback = False  # 👇 New flag

        # Determine if price is already past entry
        if self.direction == "BUY (LONG)" and current_price > self.entry:
            self.waiting_for_pullback = True
        elif self.direction == "SELL (SHORT)" and current_price < self.entry:
            self.waiting_for_pullback = True


class TradeMonitor:
    """Manages active trades, polls MT5, and checks price conditions."""

    def __init__(self, mt5_client: MT5Client, target_channel: TargetChannel):
        # Target channel is injected here for sending update replies
        self._mt5 = mt5_client
        self._target_channel = target_channel
        self.active_trades: Dict[str, Trade] = {}  # Key: symbol, Value: Trade object

    def add_trade(self, trade: Trade):
        """Adds a new trade to be monitored."""
        self.active_trades[trade.symbol] = trade
        print(f"Trade Monitor: Added new trade for {trade.symbol} (ID: {trade.message_id})")

    async def run_monitoring_cycle(self):
        """Polls prices for all active trades and checks conditions."""

        trades_to_remove = []

        for symbol, trade in list(self.active_trades.items()):
            price = await self._mt5.get_symbol_price(symbol)

            if price is None:
                continue

            # Check logic based on current trade status
            if trade.status == "PENDING_ENTRY":
                if self._check_entry_hit(trade, price):
                    await self._send_update(trade, "EXECUTED", price)
                    trade.status = "ACTIVE"
                    trade.entry_executed_price = price
                    print(f"[{symbol}] Trade Executed at {price}")

            elif trade.status == "ACTIVE":
                status, target_price = self._check_exit_hit(trade, price)

                if status == "SL":
                    await self._send_update(trade, "SL", price)
                    trades_to_remove.append(symbol)
                    print(f"[{symbol}] SL Hit at {price}")
                elif status == "TP1":
                    # TP1 hit but not final — keep trade active for TP2/breakeven
                    await self._send_update(trade, "TP1", price)
                    print(f"[{symbol}] TP1 Hit at {price}")
                elif status == "TP1_FINAL":
                    # Only TP1 defined — this is final target
                    await self._send_update(trade, "TP1", price)
                    trades_to_remove.append(symbol)
                    print(f"[{symbol}] Final TP (TP1) Hit at {price}")
                elif status == "TP2":
                    await self._send_update(trade, "TP2", price)
                    trades_to_remove.append(symbol)
                    print(f"[{symbol}] TP2 Hit at {price}")
                elif status == "BREAKEVEN":
                    await self._send_update(trade, "BREAKEVEN", price)
                    trades_to_remove.append(symbol)

        for symbol in trades_to_remove:
            del self.active_trades[symbol]

    def _get_price_tolerance(self, symbol: str) -> float:
        """Convert entry tolerance in pips to price units."""
        pip_value = BotConfig.SYMBOL_PIP_VALUES.get(symbol.upper(), 0.0001)
        return BotConfig.ENTRY_TOLERANCE_PIPS * pip_value

    def _check_entry_hit(self, trade: Trade, price: float) -> bool:
        """Check if entry is hit correctly, considering direction and signal context."""
        tolerance = self._get_price_tolerance(trade.symbol)

        if trade.direction == "BUY (LONG)":
            if trade.waiting_for_pullback:
                # Wait until price returns *down* to entry zone
                if price <= trade.entry + tolerance:
                    trade.waiting_for_pullback = False  # reset flag
                    trade.entry_confirmation_count += 1
                else:
                    trade.entry_confirmation_count = 0
            else:
                # Normal case: wait until price rises *up* to entry zone
                if price >= trade.entry - tolerance:
                    trade.entry_confirmation_count += 1
                else:
                    trade.entry_confirmation_count = 0

        elif trade.direction == "SELL (SHORT)":
            if trade.waiting_for_pullback:
                # Wait until price returns *up* to entry zone
                if price >= trade.entry - tolerance:
                    trade.waiting_for_pullback = False
                    trade.entry_confirmation_count += 1
                else:
                    trade.entry_confirmation_count = 0
            else:
                # Normal case: wait until price drops *down* to entry
                if price <= trade.entry + tolerance:
                    trade.entry_confirmation_count += 1
                else:
                    trade.entry_confirmation_count = 0

        # Confirm entry only after stable confirmation
        return trade.entry_confirmation_count >= BotConfig.ENTRY_CONFIRM_TICKS

    def _check_exit_hit(self, trade: Trade, price: float) -> tuple[str, float] | tuple[None, None]:
        """Checks for SL/TP hits, with breakeven logic after TP1."""

        has_tp2 = trade.tp2 is not None

        # BUY trades
        if trade.direction == "BUY (LONG)":
            # 1️⃣ Stop loss (only if TP1 not yet hit)
            if not trade.tp1_hit and price <= trade.sl:
                return "SL", trade.sl

            # 2️⃣ TP2 hit (final target)
            if trade.tp2 and price >= trade.tp2:
                return "TP2", trade.tp2

            # 3️⃣ TP1 hit (can be final if no TP2)
            if trade.tp1 and price >= trade.tp1 and not trade.tp1_hit:
                trade.tp1_hit = True
                if has_tp2:
                    return "TP1", trade.tp1
                else:
                    return "TP1_FINAL", trade.tp1  # mark final TP if no TP2

            # 4️⃣ Breakeven (after TP1)
            if has_tp2 and trade.tp1_hit and price <= trade.entry:
                return "BREAKEVEN", trade.entry

        # SELL trades
        elif trade.direction == "SELL (SHORT)":
            if not trade.tp1_hit and price >= trade.sl:
                return "SL", trade.sl

            if trade.tp2 and price <= trade.tp2:
                return "TP2", trade.tp2

            if trade.tp1 and price <= trade.tp1 and not trade.tp1_hit:
                trade.tp1_hit = True
                if has_tp2:
                    return "TP1", trade.tp1
                else:
                    return "TP1_FINAL", trade.tp1

            if has_tp2 and trade.tp1_hit and price >= trade.entry:
                return "BREAKEVEN", trade.entry

        return None, None

    async def _send_update(self, trade: Trade, status: str, price: float):
        """Formats and sends the status update as a reply."""

        # Use the original entry price for P&L calculation
        entry_for_pips = trade.entry_executed_price if trade.entry_executed_price else trade.entry

        pip_diff = (price - entry_for_pips) if trade.direction == "BUY (LONG)" else (entry_for_pips - price)
        pips = SignalFormatter.calculate_pips(trade.symbol, pip_diff)

        message = SignalFormatter.format_trade_update_ar(
            symbol=trade.symbol,
            status=status,
            original_entry=entry_for_pips,
            current_price=price,
            trade_direction=trade.direction,
            pips=pips
        )
        await self.reply_to_trade_message(trade.message_id, message)

    async def get_symbol_price(self, symbol: str) -> float:
        return await self._mt5.get_symbol_price(symbol)

    async def reply_to_trade_message(self, message_id: int, text: str):
        """
        Public helper to reply to a message in the target channel.
        """
        if not hasattr(self, "_target_channel") or self._target_channel is None:
            raise RuntimeError("Target channel is not configured for TradeMonitor.")
        await self._target_channel.reply_to_message(message_id, text)


# ----------------------------------------------------
# 2. THE REFACTORED PROCESSOR CLASS
# ----------------------------------------------------

class ProcessingUnit:
    """Encapsulates all components required to process one channel unit."""

    def __init__(self, config: ChannelUnitConfig, app: Client, parser: GeminiClient, trade_monitor: TradeMonitor):
        # ⬅️ FIX: TradeMonitor is now injected here
        self.config = config
        self.source_channel = SourceChannel(app, config.source_channel)
        self.storage_channel = StorageChannel(app, config.storage_channel)
        self.target_channel = TargetChannel(app, config.target_channel)
        self.gemini_parser = parser
        self.trade_monitor = trade_monitor  # ⬅️ Store injected monitor
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
            await self._handle_single_message(message)  # Calls the main logic below

    async def _handle_single_message(self, message: types.Message):
        """
        Handles the logic pipeline for a single message, including trade monitoring setup.
        """
        parsed_data = await self.gemini_parser.parse_signal_message(message.text)

        if parsed_data and parsed_data.get("is_signal"):
            symbol = parsed_data.get("symbol")
            print(f"[{self.config.source_channel}] ✨ Signal detected ID {message.id}: {symbol}")

            # --- ✅ Check for existing active trade ---
            existing_trade = self.trade_monitor.active_trades.get(symbol)
            if existing_trade:
                if existing_trade.status == "PENDING_ENTRY":
                    # 1️⃣ Cancel the old pending trade
                    cancel_msg = (
                        f"**⚠️ الغاء الأمر**"
                    )
                    await self.trade_monitor.reply_to_trade_message(
                        existing_trade.message_id, cancel_msg
                    )

                    # 2️⃣ Remove it from active trades
                    del self.trade_monitor.active_trades[symbol]
                    print(f"[{symbol}] Cancelled old pending trade due to new signal.")
                else:
                    # If the old one is active (executed), skip the new signal entirely
                    print(f"[{symbol}] ⚠️ Skipping new signal — trade already active.")
                    await self.storage_channel.save_message(str(message.id))
                    self.processed_ids.add(message.id)
                    return

            # --- ✅ Proceed with the new signal ---
            sent_message = await self.target_channel.save_message(parsed_data)

            if isinstance(sent_message, types.Message) and sent_message.id:
                price_now = await self.trade_monitor.get_symbol_price(symbol=symbol)
                trade = Trade(message_id=sent_message.id, data=parsed_data, current_price=price_now)
                self.trade_monitor.add_trade(trade)
            else:
                print(f"Warning: Target channel send failed to return Message object for ID {message.id}.")

            # Mark source message as processed
            await self.storage_channel.save_message(str(message.id))
            self.processed_ids.add(message.id)

        else:
            print(f"[{self.config.source_channel}] ➖ Message ID {message.id} is not a valid signal.")
            await self.storage_channel.save_message(str(message.id))
            self.processed_ids.add(message.id)


class SignalProcessor:
    """
    The central orchestrator, managing a list of independent ProcessingUnits.
    """

    def __init__(self, app: Client, gemini_parser: GeminiClient, mt5_client: MT5Client, channel_unit_configs: List[ChannelUnitConfig]):
        self.app = app
        # The parser can be shared across all units (it's stateless)
        self.shared_parser = gemini_parser
        self.mt5_client = mt5_client
        self.channel_unit_configs = channel_unit_configs
        # ⬅️ FIX: Initialize Trade Monitor FIRST with the necessary target channel.
        # Use the target channel from the FIRST unit for simplicity, as planned.
        if not channel_unit_configs:
            raise ValueError("Channel unit configuration list cannot be empty.")

        first_unit_config = channel_unit_configs[0]
        global_target_channel = TargetChannel(app, first_unit_config.target_channel)

        self.trade_monitor = TradeMonitor(mt5_client, global_target_channel)
        # Initialize a list of ProcessingUnit objects
        # ⬅️ FIX: Inject the TradeMonitor into each ProcessingUnit
        self.units: List[ProcessingUnit] = [
            ProcessingUnit(config, app, gemini_parser, self.trade_monitor)
            for config in channel_unit_configs
        ]


    async def start(self):
        await self.app.start()
        print(f"Telegram Client Started successfully with session: {BotConfig.SESSION_NAME}")

        # Initialize state for all units concurrently
        init_tasks = [unit.initialize_state() for unit in self.units]
        await asyncio.gather(*init_tasks)  # Use asyncio.gather for parallel state loading

        asyncio.create_task(self._polling_loop())
        asyncio.create_task(self._mt5_polling_loop())  # ⬅️ New: Start MT5 monitoring loop

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

    async def _mt5_polling_loop(self):
        """Dedicated loop for price monitoring."""
        # ⬅️ FIX: Added safeguard for missing config variable
        mt5_interval = getattr(BotConfig, 'MT5_POLLING_INTERVAL_SECONDS', BotConfig.POLLING_INTERVAL_SECONDS)

        while True:
            if self.trade_monitor.active_trades:
                print(f"MT5 Monitor: Checking {len(self.trade_monitor.active_trades)} active trades.")

            await self.trade_monitor.run_monitoring_cycle()
            await asyncio.sleep(mt5_interval)




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
        return  # Use return instead of exit() in async main

    # 2. Setup Pyrogram Client
    pyrogram_client = Client(
        BotConfig.SESSION_NAME,
        api_id=BotConfig.API_ID,
        api_hash=BotConfig.API_HASH,
    )

    # 3. Setup Dependencies
    gemini_parser = GeminiClient(model_name=BotConfig.GEMINI_MODEL, broker_symbols=BotConfig.BROKER_SYMBOLS)  # Pass model from config
    channel_unit_configs = BotConfig.load_channel_units()
    mt5_client = MT5Client()

    # 4. Instantiate Processor by Injecting Dependencies
    processor = SignalProcessor(
        app=pyrogram_client,
        gemini_parser=gemini_parser,
        mt5_client=mt5_client,  # ⬅️ Injection
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
