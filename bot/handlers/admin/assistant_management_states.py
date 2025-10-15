from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.methods import (
    check_role,
    check_user_by_username,
    get_user_language,
    set_role,
)
from bot.database.models import Permission
from bot.keyboards import back
from bot.misc import TgConfig
from bot.utils.feature_config import feature_disabled_text, is_enabled
from bot.handlers.other import get_bot_user_ids
from bot.localization import t

ASSISTANT_ROLE_ID = 4

async def assistant_management_callback(call: CallbackQuery):
    if not is_enabled("assistant"):
        disabled_text = feature_disabled_text(call.from_user.id if call.from_user else None)
        await call.answer(disabled_text, show_alert=True)
        return
    bot, user_id = await get_bot_user_ids(call)
    role = check_role(user_id)
    lang = get_user_language(user_id) or 'en'
    if not (role & Permission.OWN):
        await call.answer(t(lang, 'insufficient_rights'))
        return
    TgConfig.STATE[user_id] = None
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(t(lang, 'assistant_add_button'), callback_data='assistant_add'))
    markup.add(InlineKeyboardButton(t(lang, 'assistant_remove_button'), callback_data='assistant_remove'))
    markup.add(InlineKeyboardButton(t(lang, 'back_button'), callback_data='console'))
    await bot.edit_message_text(
        t(lang, 'assistant_choose_action'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )

async def assistant_add_callback(call: CallbackQuery):
    if not is_enabled("assistant"):
        disabled_text = feature_disabled_text(call.from_user.id if call.from_user else None)
        await call.answer(disabled_text, show_alert=True)
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'assistant_add_username'
    TgConfig.STATE[f'{user_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        t(lang, 'assistant_add_prompt'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back('assistant_management', lang),
    )

async def assistant_remove_callback(call: CallbackQuery):
    if not is_enabled("assistant"):
        disabled_text = feature_disabled_text(call.from_user.id if call.from_user else None)
        await call.answer(disabled_text, show_alert=True)
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'assistant_remove_username'
    TgConfig.STATE[f'{user_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        t(lang, 'assistant_remove_prompt'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back('assistant_management', lang),
    )

async def process_assistant_username(message: Message):
    if not is_enabled("assistant"):
        disabled_text = feature_disabled_text(message.from_user.id if message.from_user else None)
        await message.reply(disabled_text)
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_message_id", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    lang = get_user_language(user_id) or 'en'
    state = TgConfig.STATE.get(user_id)
    if state not in {'assistant_add_username', 'assistant_remove_username'}:
        return
    username = message.text.lstrip('@')
    message_id = TgConfig.STATE.get(f'{user_id}_message_id')
    TgConfig.STATE[user_id] = None
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    user = check_user_by_username(username)
    if not user:
        await bot.edit_message_text(
            t(lang, 'user_not_found'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=back('assistant_management', lang),
        )
        return
    if state == 'assistant_add_username':
        set_role(user.telegram_id, ASSISTANT_ROLE_ID)
        await bot.edit_message_text(
            t(lang, 'assistant_assigned'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=back('assistant_management', lang),
        )
    else:
        set_role(user.telegram_id, 1)
        await bot.edit_message_text(
            t(lang, 'assistant_removed'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=back('assistant_management', lang),
        )


def register_assistant_management(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(assistant_management_callback,
                                       lambda c: c.data == 'assistant_management')
    dp.register_callback_query_handler(assistant_add_callback,
                                       lambda c: c.data == 'assistant_add')
    dp.register_callback_query_handler(assistant_remove_callback,
                                       lambda c: c.data == 'assistant_remove')
    dp.register_message_handler(process_assistant_username,
                                lambda m: TgConfig.STATE.get(m.from_user.id) in {
                                    'assistant_add_username', 'assistant_remove_username'
                                })