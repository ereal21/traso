from aiogram.utils import executor
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from bot.filters import register_all_filters
from bot.misc import EnvKeys
from bot.handlers import register_all_handlers
from bot.handlers.admin.feature_toggle import register_feature_toggle_handler
from bot.handlers.other import verify_control_chat_access
from bot.database.models import register_models
from bot.logger_mesh import logger
from bot.database.methods import ensure_owner_account

async def __on_start_up(dp: Dispatcher) -> None:
    register_all_filters(dp)
    register_all_handlers(dp)
    register_feature_toggle_handler(dp)
    register_models()

    ensure_owner_account(EnvKeys.OWNER_ID)

    try:
        owner_id = int(EnvKeys.OWNER_ID) if EnvKeys.OWNER_ID else None
    except (TypeError, ValueError):
        owner_id = None

    if owner_id:
        try:
            await dp.bot.send_message(
                owner_id,
                "✅ Viskas turėtų veikti be problemų pagal viską. Sekmės ❤️",
            )
        except Exception as e:
            logger.error("Startup ping to OWNER_ID=%s failed: %s", owner_id, e)
    else:
        logger.warning("OWNER_ID is not set or invalid; cannot send startup ping.")

    await verify_control_chat_access(dp.bot)


def start_bot():
    bot = Bot(token=EnvKeys.TOKEN, parse_mode='HTML')
    dp = Dispatcher(bot, storage=MemoryStorage())
    executor.start_polling(dp, skip_updates=False, on_startup=__on_start_up)