
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from aiogram import types, Dispatcher

from bot.utils.feature_config import FEATURE_JSON_PATH, reload_feature_flags

GROUP_ID = -4930039742
ALLOWED_BOTS = {"@fgaganoybot", "@ParduotuveBot"}
CONFIRM_USER = "@Inereal"

last_feature_request = {
    "function": None,  # type: Optional[str]
    "enabled": None,   # type: Optional[bool]
    "timestamp": None,  # type: Optional[datetime]
}

def log(msg):
    print(f"[FEATURE TOGGLE] {msg}")

def persist_feature_toggle(function_name: str, enabled: bool) -> bool:
    try:
        log(f"Attempting to persist feature '{function_name}' = {enabled}")

        with open(FEATURE_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        key = function_name.lower()
        if key not in data:
            log(f"⚠️ Function '{key}' not found in configuration.")
            return False

        data[key] = bool(enabled)

        with open(FEATURE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.write("\n")

        reload_feature_flags()
        log(f"Updated: {key} = {enabled}")
        return True
    except Exception as e:
        log(f"❌ Exception: {e}")
        return False

async def feature_toggle_handler(message: types.Message):
    print(f"[DEBUG] Message from group {message.chat.id} by @{message.from_user.username if message.from_user else 'unknown'}: {message.text}")

    if message.chat.id != GROUP_ID or not message.text:
        return

    text = message.text.strip()

    if text.startswith("/"):
        return

    if text.lower().startswith('function "') and 'turn ' in text.lower():
        try:
            func_name = text.split('"')[1].strip()

            lowered = text.lower()
            if " turn on" in lowered:
                new_state = True
            elif " turn off" in lowered:
                new_state = False
            else:
                await message.reply("⚠️ Could not determine desired state. Use ON or OFF.")
                return

            if not all(bot in text for bot in ALLOWED_BOTS):
                await message.reply("❌ Missing required bot mentions.")
                return

            last_feature_request["function"] = func_name
            last_feature_request["enabled"] = new_state
            last_feature_request["timestamp"] = datetime.utcnow()

            state_text = "enable" if new_state else "disable"
            await message.reply(
                f"🕓 Waiting for confirmation from {CONFIRM_USER} to {state_text} '{func_name}'..."
            )
            log(f"Queued feature '{func_name}' -> {new_state} for confirmation")

        except Exception as e:
            await message.reply(f"⚠️ Parse error: {e}")
            log(f"Parse error: {e}")
        return

    if message.from_user and message.from_user.username == CONFIRM_USER.strip("@"):
        if "confirmed the functions for @fgaganoybot @ParduotuveBot" in text:
            func_name = last_feature_request["function"]
            new_state = last_feature_request.get("enabled")
            if func_name is None or new_state is None:
                await message.reply("⚠️ No pending feature.")
                return

            if datetime.utcnow() - last_feature_request["timestamp"] > timedelta(minutes=2):
                await message.reply("⚠️ Request expired.")
                last_feature_request["function"] = None
                last_feature_request["enabled"] = None
                return

            success = persist_feature_toggle(func_name, new_state)
            last_feature_request["function"] = None
            last_feature_request["enabled"] = None

            if success:
                human_state = "ON" if new_state else "OFF"
                await message.reply(f"✅ Feature '{func_name}' saved as {human_state}. Restarting...")
                log(f"Feature '{func_name}' written to file as {human_state}. Restarting bot.")
                os.execv(sys.executable, [sys.executable, *sys.argv])
            else:
                await message.reply(f"❌ Failed to save feature '{func_name}'.")
                log(f"Failed to update feature '{func_name}'")
        return

    if text.lower().strip() == "restart @fgaganoybot":
        await message.reply("🔁 Restarting bot...")
        log("Manual restart triggered.")
        os.execv(sys.executable, [sys.executable, *sys.argv])

def register_feature_toggle_handler(dp: Dispatcher):
    dp.register_message_handler(
        feature_toggle_handler,
        content_types=types.ContentTypes.TEXT
    )
