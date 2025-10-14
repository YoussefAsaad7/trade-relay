from typing import Dict, Any, Optional
from config import BotConfig

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
    def calculate_pips(symbol: str, price_diff: float) -> int:
        """
        Calculates pips from a price difference based on the symbol's pip value.
        """
        pip_value = BotConfig.SYMBOL_PIP_VALUES.get(symbol.upper(), 0.0001)
        return int(round(price_diff / pip_value))

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

    @staticmethod
    def format_signal_message_ar(signal_data: Dict[str, Any]) -> str:
        """
        Takes the parsed dictionary and returns the final formatted message string
        in Arabic Telegram style.
        """

        entry_price = signal_data.get('entry_price')
        stop_loss = signal_data.get('sl')
        current_price = signal_data.get('current_price')
        tp1 = signal_data.get('tp1')
        tp2 = signal_data.get('tp2')

        # 1. Determine Direction (keep existing logic)
        trade_direction = SignalFormatter.determine_direction(entry_price, stop_loss)

        # 2. Map symbol to Arabic name
        symbol = signal_data.get('symbol', 'N/A').upper()
        arabic_name = BotConfig.ASSET_NAME_MAP.get(symbol, symbol)

        # 3. Translate direction for display (without changing internal logic)
        if trade_direction == "BUY (LONG)":
            direction_ar = "شراء"
        elif trade_direction == "SELL (SHORT)":
            direction_ar = "بيع"
        else:
            direction_ar = trade_direction  # keep as-is if unknown

        # 4. Build the formatted Arabic message
        formatted_message = f"{arabic_name}♂️\n👁‍🗨{symbol}\n"
        formatted_message += f"أمر {direction_ar} معلق\n"
        formatted_message += f"السعر {entry_price or 'N/A'}\n"

        # Include current price only if different from entry price
        # if current_price is not None and entry_price is not None and current_price != entry_price:
        #     formatted_message += f"السعر الحالي {current_price}\n"

        formatted_message += "\n"

        if tp1:
            if tp2:
                formatted_message += f"الهدف الأول {tp1}\n"
            else:
                formatted_message += f"الهدف {tp1}\n"

        if tp2:
            formatted_message += f"الهدف الثاني {tp2}\n"

        if stop_loss:
            formatted_message += f"\nالوقف {stop_loss}\n\n\n\n."


        return formatted_message.strip()

    @staticmethod
    def format_trade_update(symbol: str, status: str, original_entry: float, current_price: float,
                            trade_direction: str, pips: int) -> str:
        """Formats the trade status update message."""

        # Determine sign and message
        sign = "+" if pips >= 0 else ""

        if status == "EXECUTED":
            return f"🟢 **TRADE EXECUTED**\n\nEntry Price: `{current_price}`"
        elif status == "SL":
            return f"🔴 **STOP LOSS HIT**\n\nProfit/Loss: `{sign}{pips}` pips."
        elif status == "TP1":
            return f"✅ **TAKE PROFIT 1 HIT**\n\nProfit/Loss: `{sign}{pips}` pips."
        elif status == "TP2":
            return f"✅ **TAKE PROFIT 2 HIT**\n\nProfit/Loss: `{sign}{pips}` pips."
        elif status == "BREAKEVEN":
            return f"✅ **EXIT BREAKEVEN**\n\nProfit/Loss: `{sign}{pips}` pips."

        return f"Trade update for {symbol}: {status}"

    @staticmethod
    def format_trade_update_ar(symbol: str, status: str, original_entry: float, current_price: float,
                            trade_direction: str, pips: int) -> str:
        """Formats the trade status update message."""

        # Determine sign and message
        sign = "+" if pips >= 0 else ""

        if status == "EXECUTED":
            return f"🟢 تم التفعيل\n\nالسعر: `{current_price}`"
        elif status == "SL":
            return f"🔴 ستوب {sign}{pips}"
        elif status == "TP1":
            return f"✅ تم ضرب الهدف الأول {sign}{pips}"
        elif status == "TP2":
            return f"✅ تم ضرب الهدف الثاني {sign}{pips}"
        elif status == "BREAKEVEN":
            return f"🟡 تم الخروج على الدخول بعد ضرب الهدف الأول "

        return f"Trade update for {symbol}: {status}"