from typing import Dict, Any, Optional


class SignalFormatter:
    """
    Dedicated class responsible for formatting the parsed signal data
    into a Markdown string ready for Telegram display.
    """

    @staticmethod
    def determine_direction(entry_price: Optional[float], stop_loss: Optional[float]) -> str:
        """
        Calculates the trade direction based on entry price and stop loss.
        """
        if entry_price is not None and stop_loss is not None:
            # BUY (LONG): Entry is higher than Stop Loss (SL below entry)
            if entry_price > stop_loss:
                return "BUY (LONG)"

            # SELL (SHORT): Entry is lower than Stop Loss (SL above entry)
            elif entry_price < stop_loss:
                return "SELL (SHORT)"

        return "UNKNOWN"

    @staticmethod
    def format_signal_message(signal_data: Dict[str, Any]) -> str:
        """
        Takes the parsed dictionary and returns the final formatted message string.
        """

        entry_price = signal_data.get('entry_price')
        stop_loss = signal_data.get('sl')
        current_price = signal_data.get('current_price')

        # 1. Determine Direction
        trade_direction = SignalFormatter.determine_direction(entry_price, stop_loss)

        # 2. Build the Message Structure

        # Base Structure
        formatted_message = (
            f"🚨 **NEW TRADING SIGNAL** 🚨\n\n"
            f"📊 **DIRECTION:** `{trade_direction}`\n"
            f"📈 **Asset:** `{signal_data.get('symbol', 'N/A')}`\n"
        )

        # Conditional Current Price inclusion (only if different from Entry Price)
        if (current_price is not None and entry_price is not None and
                current_price != entry_price):
            formatted_message += f"💵 **Current Price:** `${current_price}`\n"

        # Core Prices
        formatted_message += (
            f"✅ **Entry Price:** `${entry_price or 'N/A'}`\n"
            f"❌ **Stop Loss (SL):** `${stop_loss or 'N/A'}`\n"
        )

        # Optional Take Profit Targets
        if signal_data.get('tp1'):
            formatted_message += f"🎯 **Take Profit 1 (TP1):** `${signal_data['tp1']}`\n"
        if signal_data.get('tp2'):
            formatted_message += f"🎯 **Take Profit 2 (TP2):** `${signal_data['tp2']}`\n"

        return formatted_message