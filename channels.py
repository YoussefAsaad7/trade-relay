import abc
from typing import Set, List, Dict, Any
from pyrogram import Client, types
from pyrogram.enums import ParseMode
from pyrogram.raw.core import Message

from formatter import SignalFormatter


class BaseChannel(abc.ABC):
    """
    Abstract Base Class defining the required interface for all channel types.
    """

    def __init__(self, client: Client, channel_username: str):
        self._client = client
        self._username = channel_username

    @abc.abstractmethod
    async def get_latest_messages(self, limit: int = 5) -> List[types.Message]:
        """Fetches the latest messages from the channel."""
        pass

    @abc.abstractmethod
    async def save_message(self, content: str):
        """Saves or sends a message to the channel."""
        pass


class SourceChannel(BaseChannel):
    """
    Encapsulates logic for polling the channel containing raw signals.
    """

    async def get_latest_messages(self, limit: int = 5) -> List[types.Message]:
        """Fetches and filters the last N messages from the source channel."""

        # NOTE: Pyrogram's get_chat_history is an async generator
        messages = []
        async for message in self._client.get_chat_history(self._username, limit=limit):
            # Only consider messages with actual text content
            if message.text:
                messages.append(message)
        return messages

    async def save_message(self, content: str):
        """Source channel is typically read-only; implementation is a placeholder."""
        raise NotImplementedError("SourceChannel is read-only and cannot save messages.")


class StorageChannel(BaseChannel):
    """
    Encapsulates logic for reading and writing processed message IDs for state persistence.
    """

    async def get_latest_messages(self, limit: int = 10) -> Set[int]:
        """Fetches processed message IDs from the storage channel and returns a Set."""
        processed_ids: Set[int] = set()
        print(f"Loading processed IDs from {self._username}...")
        try:
            async for message in self._client.get_chat_history(self._username, limit=limit):
                # The storage channel message text is the ID of the processed message
                if message.text:
                    try:
                        processed_ids.add(int(message.text.strip()))
                    except (ValueError, AttributeError):
                        continue
            return processed_ids
        except Exception as e:
            print(f"Error loading processed IDs from storage: {e}")
            return set()  # Return empty set on error

    async def save_message(self, content: str):
        """Saves the ID of a processed message to the storage channel."""
        try:
            await self._client.send_message(
                chat_id=self._username,
                text=content
            )
        except Exception as e:
            print(f"Error saving message ID {content} to storage channel: {e}")


class TargetChannel(BaseChannel):
    """
    Encapsulates logic for sending the final, parsed signal to the target channel.
    """

    async def get_latest_messages(self, limit: int = 5) -> List[types.Message]:
        """Target channel is write-only; implementation is a placeholder."""
        raise NotImplementedError("TargetChannel is write-only and cannot retrieve messages.")

    async def save_message(self, signal_data: Dict[str, Any]) -> types.Message:
        """
        Formats and sends the structured signal data to the target channel.

        """

        # ⬅️ Delegation: Let the dedicated formatter handle the complexity
        formatted_message = SignalFormatter.format_signal_message_ar(signal_data)

        try:
            message = await self._client.send_message(
                chat_id=self._username,
                text=formatted_message,
                parse_mode= ParseMode.MARKDOWN
            )
            print(f"Signal sent to {self._username}.")
            return message
        except Exception as e:
            print(f"Error sending message to target channel: {e}")
            return message


    async def reply_to_message(self, message_id: int, text: str):
        """Sends a message as a reply to a specific message ID."""
        try:
            await self._client.send_message(
                chat_id=self._username,
                text=text,
                reply_to_message_id=message_id,  # ⬅️ Crucial Pyrogram parameter
                parse_mode=ParseMode.MARKDOWN
            )
            print(f"Trade update sent as reply to ID {message_id} in {self._username}.")
        except Exception as e:
            print(f"Error sending reply to message ID {message_id}: {e}")