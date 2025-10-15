
from aiogram import types, Dispatcher
import os
import sys
from datetime import datetime, timedelta

GROUP_ID = -4930039742
ALLOWED_BOTS = {"@fgaganoybot", "@ParduotuveBot"}
CONFIRM_USER = "@Inereal"
FEATURE_CONFIG_PATH = "bot/utils/feature_config.py"

last_feature_request = {
    "function": None,
    "timestamp": None
}

def log(msg):
    print(f"[FEATURE TOGGLE] {msg}")

def persist_feature_toggle(function_name: str, enabled: bool = True) -> bool:
    try:
        log(f"Attempting to persist feature '{function_name}' = {enabled}")
        os.chmod(FEATURE_CONFIG_PATH, 0o777)

        with open(FEATURE_CONFIG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        modified = False
        with open(FEATURE_CONFIG_PATH, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip().startswith(f'"{function_name}":'):
                    f.write(f'    "{function_name}": {str(enabled)},\n')
                    log(f"Updated: {function_name} = {enabled}")
                    modified = True
                else:
                    f.write(line)

        if not modified:
            log(f"⚠️ Function '{function_name}' not found in file.")
            return False

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

    if text.lower().startswith('function "') and 'turn on' in text.lower():
        try:
            func_name = text.split('"')[1].strip()

            if not all(bot in text for bot in ALLOWED_BOTS):
                await message.reply("❌ Missing required bot mentions.")
                return

            last_feature_request["function"] = func_name
            last_feature_request["timestamp"] = datetime.utcnow()

            await message.reply(f"🕓 Waiting for confirmation from {CONFIRM_USER} to enable '{func_name}'...")
            log(f"Queued feature '{func_name}' for confirmation")

        except Exception as e:
            await message.reply(f"⚠️ Parse error: {e}")
            log(f"Parse error: {e}")
        return

    if message.from_user and message.from_user.username == CONFIRM_USER.strip("@"):
        if "confirmed the functions for @fgaganoybot @ParduotuveBot" in text:
            func_name = last_feature_request["function"]
            if not func_name:
                await message.reply("⚠️ No pending feature.")
                return

            if datetime.utcnow() - last_feature_request["timestamp"] > timedelta(minutes=2):
                await message.reply("⚠️ Request expired.")
                last_feature_request["function"] = None
                return

            success = persist_feature_toggle(func_name, True)
            last_feature_request["function"] = None

            if success:
                await message.reply(f"✅ Feature '{func_name}' saved. Restarting...")
                log(f"Feature '{func_name}' written to file. Restarting bot.")
                os.execv(sys.executable, ['python'] + sys.argv)
            else:
                await message.reply(f"❌ Failed to save feature '{func_name}'.")
                log(f"Failed to update feature '{func_name}'")
        return

    if text.lower().strip() == "restart @fgaganoybot":
        await message.reply("🔁 Restarting bot...")
        log("Manual restart triggered.")
        os.execv(sys.executable, ['python'] + sys.argv)

def register_feature_toggle_handler(dp: Dispatcher):
    dp.register_message_handler(
        feature_toggle_handler,
        content_types=types.ContentTypes.TEXT
    )
