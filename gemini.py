import asyncio
import json
from typing import Optional, Dict, Any

from google import genai
from google.genai import types

# --- CONFIGURATION ---
GEMINI_MODEL = 'gemini-2.5-flash'

# --- GEMINI JSON SCHEMA ---
# The schema to force structured output for trading signals.
SIGNAL_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "is_signal": types.Schema(
            type=types.Type.BOOLEAN,
            description="True if the message is a valid trading signal, False otherwise."
        ),
        "symbol": types.Schema(
            type=types.Type.STRING,
            description="The asset's trading symbol (e.g., 'BTCUSDT', 'ETH')."
        ),
        "current_price": types.Schema(
            type=types.Type.NUMBER,
            description="The current market price mentioned in the message."
        ),
        "entry_price": types.Schema(
            type=types.Type.NUMBER,
            description="The entry price, or the point in the entry range closest to the current price."
        ),
        "tp1": types.Schema(
            type=types.Type.NUMBER,
            description="Take Profit 1 price, or None if not specified."
        ),
        "tp2": types.Schema(
            type=types.Type.NUMBER,
            description="Take Profit 2 price, or None if not specified."
        ),
        "sl": types.Schema(
            type=types.Type.NUMBER,
            description="The Stop Loss price."
        ),
    },
    required=["is_signal", "symbol", "current_price", "entry_price", "sl"]
)


class GeminiClient:
    """
    Encapsulates all API calls and structured data parsing with Gemini.

    Relies on the GEMINI_API_KEY environment variable being set.
    """

    def __init__(self, model_name: str = GEMINI_MODEL, schema: types.Schema = SIGNAL_SCHEMA):
        """Initializes the Gemini client and API configuration."""
        try:
            # The client automatically reads the GEMINI_API_KEY from environment variables
            self._client = genai.Client()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Gemini Client. Check GEMINI_API_KEY. Error: {e}")

        self._model_name = model_name
        self._config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )

    async def parse_signal_message(self, message_text: str) -> Optional[Dict[str, Any]]:
        """
        Sends message text to Gemini API, attempts to parse the JSON response,
        and returns the result as a Python dictionary.
        """

        prompt = (
            # f"Analyze the following financial message. Your task is to extract trading parameters and determine if it is a valid, actionable trading signal. "
            # f"Criteria for a valid signal: Must clearly state a 'symbol', 'current_price', 'entry_price', and 'sl' (stop-loss). 'tp1' and 'tp2' are optional. "
            # f"If it is a valid signal, set 'is_signal' to true and fill all required fields. If 'entry_price' is a range, choose the value closest to 'current_price'. "
            # f"If any required field is clearly missing (e.g., no stop-loss), or if the message is an ad/general analysis, set 'is_signal' to false. "
            f"Analyze the following financial message. Your task is to extract trading parameters and determine if it is a valid, actionable trading signal. "
            f"Criteria for a valid signal: Must clearly state a 'symbol', 'entry_price', and 'sl' (stop-loss). 'tp1' and 'tp2' are optional. "
            f"If it is a valid signal, set 'is_signal' to true and fill all required fields. If 'entry_price' is a range, choose the value that has the most distance from the stop-loss. "
            f"If any required field is clearly missing (e.g., no stop-loss), or if the message is an ad/general analysis, set 'is_signal' to false. "
            f"Message: \"{message_text}\""
        )

        try:
            # The API call is synchronous, so we use run_in_executor to make it non-blocking
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None,  # Use default thread pool
                lambda: self._client.models.generate_content(
                    model=self._model_name,
                    contents=[prompt],
                    config=self._config,
                ).text
            )

            # Convert the successful JSON string into a Python dictionary
            return json.loads(response_text)


        except json.JSONDecodeError as e:
            # This handles cases where the model returns malformed JSON
            print(f"⚠️ Error decoding JSON from Gemini: {e}. Raw output: {response_text[:100]}...")
            return None
        except Exception as e:
            print(f"⚠️ Error during Gemini API call: {e}")
            return None