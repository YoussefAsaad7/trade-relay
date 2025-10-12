import asyncio
from typing import Optional, Dict
import MetaTrader5 as mt5


class MT5Client:
    """
    Asynchronous wrapper for MetaTrader 5 price polling.
    Handles connection and synchronous price retrieval in a thread pool.
    """

    def __init__(self):
        # Synchronous initialization
        if not mt5.initialize():
            print(f"FATAL: MT5 initialization failed. Error code: {mt5.last_error()}")
            # In a real app, you might raise an error or set a flag to disable MT5 features
            self._is_initialized = False
        else:
            print("MT5 Client initialized successfully.")
            self._is_initialized = True
            account_info = mt5.account_info()
            if account_info is None:
                print("⚠️ MT5 is running but no broker account is logged in.")
            else:
                print(f"✅ Connected to account {account_info.login} ({account_info.name})")

    def _get_symbol_price_sync(self, symbol: str) -> Optional[float]:
        """Synchronous call to get the current ask price for a symbol."""
        if not self._is_initialized:
            return None

        try:
            if not mt5.symbol_select(symbol, True):
                print(f"⚠️ Symbol {symbol} not found or unavailable.")
                return None

            tick = mt5.symbol_info_tick(symbol)
            if tick is None or tick.ask == 0.0:
                print(f"⚠️ No valid tick data for {symbol}.")
                return None

            return tick.ask

        except Exception as e:
            print(f"⚠️ MT5 error while fetching {symbol}: {e}")
            self._is_initialized = False
            return None

    async def get_symbol_price(self, symbol: str) -> Optional[float]:
        """
        Asynchronously fetches the symbol price using a thread executor.
        """
        if not self._is_initialized:
            return None

        loop = asyncio.get_running_loop()
        try:
            price = await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                self._get_symbol_price_sync,
                symbol
            )
            return price
        except Exception as e:
            print(f"Error polling MT5 price for {symbol}: {e}")
            return None