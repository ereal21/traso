
import asyncio
import os
import re
from typing import Final

from aiogram import Bot, Dispatcher, types

# --- Backwards-compat helpers expected by admin modules ---
async def get_bot_user_ids(query):
    """Return (bot, user_id) to keep compatibility with admin modules that import this."""
    bot = query.bot
    user_id = query.from_user.id if getattr(query, "from_user", None) else None
    return bot, user_id

async def check_sub_channel(chat_member):
    """Legacy stub used in some places; return True if user is not 'left'."""
    try:
        return str(chat_member.status) != "left"
    except Exception:
        return True

async def get_bot_info(query):
    """Return this bot's username, for compatibility with old utilities."""
    bot = query.bot
    bot_info = await bot.me
    return bot_info.username
# --- end compat ---

from bot.logger_mesh import logger


# Read from env with sensible defaults
CONTROL_CHAT_ID: Final[int] = int(os.getenv("FUNCTION_ALERT_CHAT_ID", "-4930039742"))
THIS_BOT_USERNAME: Final[str] = os.getenv("BOT_USERNAME", "fgaganoybot").lstrip("@")
CONTROL_CHAT_TYPES: Final[tuple[str, ...]] = ("group", "supergroup", "channel")

VALID_FEATURES: Final[set[str]] = {
    "blackjack",
    "coinflip",
    "achievements",
    "quests",
    "gift",
    "stock_alerts",
    "assistant",
    "broadcast",
    "lottery",
    "leaderboard",
    "promocodes",
    "analytics",
    "locations",
    "product_types",
    "reviews",
    "reservations",
    "manual_payments",
    "media_library",
    "crypto_payments",
}

# Example: function "blackjack" turn ON @fgaganoybot @ParduotuveBot
TOGGLE_RE = re.compile(
    r'^function\s+"([^"]+)"\s+turn\s+(ON|OFF)\s+(@[A-Za-z0-9_]+(?:\s+@[A-Za-z0-9_]+)*)$',
    re.I,
)

# Example: restart @fgaganoybot  or  "Dealer confirmed the functions for @fgaganoybot"
RESTART_RE = re.compile(r'^restart\s+@([A-Za-z0-9_]+)$', re.I)
CONFIRMED_RE = re.compile(r'confirmed\s+the\s+functions', re.I)

def _target_matches(target_handle: str) -> bool:
    return target_handle.lower().lstrip("@") == THIS_BOT_USERNAME.lower()

async def _handle_toggle(message: types.Message, m: re.Match) -> None:
    feature = m.group(1).strip().lower()
    state_str = m.group(2).upper()
    targets_block = m.group(3)
    target_handles = targets_block.split()
    primary_target = target_handles[0] if target_handles else ""

    if not _target_matches(primary_target):
        logger.info(
            "Control chat toggle addressed to %s; bot username is %s. Ignoring.",
            primary_target,
            THIS_BOT_USERNAME,
        )
        return

    if feature not in VALID_FEATURES:
        logger.warning("Control chat requested unknown feature '%s'", feature)
        await message.reply(f"⚠️ Unknown feature '{feature}'. Ignoring.")
        return

    new_state = True if state_str == "ON" else False
    logger.info("Control chat set feature '%s' to %s", feature, "ON" if new_state else "OFF")
    await message.reply(
        f"🔧 Set '{feature}' to {'ON' if new_state else 'OFF'} for @{THIS_BOT_USERNAME}."
    )

async def _handle_restart(message: types.Message) -> None:
    logger.info("Control chat requested restart via message %s", message.message_id)
    await message.reply("♻️ Restarting bot to apply feature changes…")
    # Delay so the ACK goes out before exit
    await asyncio.sleep(1)
    os._exit(0)

def _sender_display_name(message: types.Message) -> str:
    sender = message.from_user
    if sender and sender.username:
        return f"@{sender.username}"
    if sender:
        return f"id={sender.id}"
    return "unknown"


async def _control_listener(message: types.Message):
    # Only react in the configured control chat
    if message.chat.id != CONTROL_CHAT_ID:
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        logger.info(
            "Control chat message from %s (%s) had no text payload. Nothing to process.",
            _sender_display_name(message),
            message.chat.id,
        )
        return

    logger.info(
        "Control chat message from %s (%s): %s",
        _sender_display_name(message),
        message.chat.id,
        text,
    )

    # 1) Toggle command
    mt = TOGGLE_RE.match(text)
    if mt:
        await _handle_toggle(message, mt)
        return

    # 2) Restart command explicitly
    mr = RESTART_RE.match(text)
    if mr and _target_matches(mr.group(1)):
        await _handle_restart(message)
        return

    # 3) Confirmation message triggers restart for this bot
    if CONFIRMED_RE.search(text):
        mentions = re.findall(r'@[A-Za-z0-9_]+', text)
        if any(_target_matches(handle) for handle in mentions):
            await _handle_restart(message)
            return
        logger.info(
            "Confirmation message detected but no matching mention for %s. Ignoring.",
            THIS_BOT_USERNAME,
        )
        return

    # logger.info("Control chat message did not match any automation keywords. Ignored.")  # Disabled by request


async def _group_listener(message: types.Message):
    """Compatibility wrapper for legacy registration code."""
    await _control_listener(message)


def register_other_handlers(dp: Dispatcher) -> None:
    # Listen to all messages in the configured control chat (group, supergroup, or channel)
    dp.register_message_handler(
        _group_listener,
        content_types=types.ContentType.ANY,
        chat_type=list(CONTROL_CHAT_TYPES),
        state='*',
    )

    # Handle cases where the control chat is implemented as a broadcast channel
    dp.register_channel_post_handler(
        _control_listener,
        state='*',
    )


async def verify_control_chat_access(bot: Bot) -> None:
    """Log diagnostic information about the control chat membership."""

    try:
        chat = await bot.get_chat(CONTROL_CHAT_ID)
    except Exception as exc:
        logger.warning(
            "Unable to resolve control chat id %s: %s. Ensure the bot is added to the control group and the FUNCTION_ALERT_CHAT_ID is correct.",
            CONTROL_CHAT_ID,
            exc,
        )
        return

    try:
        me = await bot.me
        member = await bot.get_chat_member(CONTROL_CHAT_ID, me.id)
        logger.info(
            "Control chat '%s' (%s) resolved. Bot membership status: %s.",
            getattr(chat, 'title', chat.id),
            CONTROL_CHAT_ID,
            getattr(member, 'status', 'unknown'),
        )
        if getattr(member, 'status', None) == 'left':
            logger.warning(
                "Bot is not a member of the control chat %s. Add the bot and disable privacy mode to receive updates.",
                CONTROL_CHAT_ID,
            )
    except Exception as exc:
        logger.warning(
            "Unable to verify bot membership in control chat %s: %s. The bot might need admin rights or privacy mode disabled.",
            CONTROL_CHAT_ID,
            exc,
        )

def register_other_handlers(dp: Dispatcher) -> None:
    # Listen to all messages in the configured control chat (group, supergroup, or channel)
    dp.register_message_handler(
        _control_listener,
        content_types=types.ContentType.ANY,
        chat_type=list(CONTROL_CHAT_TYPES),
        state='*',
    )

    # Handle cases where the control chat is implemented as a broadcast channel
    dp.register_channel_post_handler(
        _control_listener,
        state='*',
    )


async def verify_control_chat_access(bot: Bot) -> None:
    """Log diagnostic information about the control chat membership."""

    try:
        chat = await bot.get_chat(CONTROL_CHAT_ID)
    except Exception as exc:
        logger.warning(
            "Unable to resolve control chat id %s: %s. Ensure the bot is added to the control group and the FUNCTION_ALERT_CHAT_ID is correct.",
            CONTROL_CHAT_ID,
            exc,
        )
        return

    try:
        me = await bot.me
        member = await bot.get_chat_member(CONTROL_CHAT_ID, me.id)
        logger.info(
            "Control chat '%s' (%s) resolved. Bot membership status: %s.",
            getattr(chat, 'title', chat.id),
            CONTROL_CHAT_ID,
            getattr(member, 'status', 'unknown'),
        )
        if getattr(member, 'status', None) == 'left':
            logger.warning(
                "Bot is not a member of the control chat %s. Add the bot and disable privacy mode to receive updates.",
                CONTROL_CHAT_ID,
            )
    except Exception as exc:
        logger.warning(
            "Unable to verify bot membership in control chat %s: %s. The bot might need admin rights or privacy mode disabled.",
            CONTROL_CHAT_ID,
            exc,
        )
        return

    # logger.info("Control chat message did not match any automation keywords. Ignored.")  # Disabled by request

def register_other_handlers(dp: Dispatcher) -> None:
    # Listen to all text messages in groups/supergroups (we filter by chat id inside)
    dp.register_message_handler(
        _group_listener,
        content_types=['text'],
        chat_type=['group', 'supergroup'],
        state='*',
    )