import asyncio

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.exceptions import BotBlocked

from bot.database.methods import (
    check_role,
    get_all_user_ids,
    get_cities,
    get_regions,
    get_resellers,
    get_user_ids_by_city,
    get_user_ids_by_region,
    get_user_ids_by_status,
    get_user_ids_without_activity,
    get_user_language,
)
from bot.database.models import Permission
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import back, close
from bot.localization import t
from bot.logger_mesh import logger
from bot.misc import TgConfig
from bot.utils.feature_config import is_feature_enabled as is_enabled


FILTER_KEY_TEMPLATE = '{user_id}_broadcast_filter'


def _filter_key(user_id: int) -> str:
    return FILTER_KEY_TEMPLATE.format(user_id=user_id)


def _set_filter(user_id: int, filter_type: str, value) -> None:
    TgConfig.STATE[_filter_key(user_id)] = (filter_type, value)


def _segment_markup(lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    buttons = [
        ('all', 'broadcast_segment_all'),
        ('active', 'broadcast_segment_active'),
        ('inactive', 'broadcast_segment_inactive'),
        ('no_activity', 'broadcast_segment_no_activity'),
        ('resellers', 'broadcast_segment_resellers'),
    ]
    for key, text_key in buttons:
        markup.add(InlineKeyboardButton(t(lang, text_key), callback_data=f'broadcast:segment:{key}'))
    markup.add(InlineKeyboardButton(t(lang, 'broadcast_segment_city'), callback_data='broadcast:segment:city'))
    markup.add(InlineKeyboardButton(t(lang, 'broadcast_segment_region'), callback_data='broadcast:segment:region'))
    markup.add(InlineKeyboardButton(t(lang, 'back_to_menu'), callback_data='console'))
    return markup


def _cities_markup(lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    cities = get_cities()
    if not cities:
        markup.add(InlineKeyboardButton(t(lang, 'broadcast_no_cities'), callback_data='broadcast:segments'))
    else:
        for city in cities:
            title = city['name']
            if city['region']:
                title = t(lang, 'analytics_city_with_region', city=city['name'], region=city['region'])
            markup.add(InlineKeyboardButton(title, callback_data=f"broadcast:city:{city['id']}"))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='broadcast:segments'))
    return markup


def _regions_markup(lang: str, user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    regions = get_regions()
    TgConfig.STATE[f'{user_id}_regions'] = regions
    if not regions:
        markup.add(InlineKeyboardButton(t(lang, 'broadcast_no_regions'), callback_data='broadcast:segments'))
    else:
        for idx, region in enumerate(regions):
            markup.add(InlineKeyboardButton(region, callback_data=f'broadcast:region_index:{idx}'))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='broadcast:segments'))
    return markup


def _resolve_recipients(filter_data: tuple[str, str | int | None]) -> list[int]:
    filter_type, value = filter_data
    if filter_type == 'active':
        return get_user_ids_by_status(True)
    if filter_type == 'inactive':
        return get_user_ids_by_status(False)
    if filter_type == 'no_activity':
        return get_user_ids_without_activity()
    if filter_type == 'resellers':
        return [row[0] for row in get_resellers()]
    if filter_type == 'city' and value is not None:
        return get_user_ids_by_city(int(value))
    if filter_type == 'region' and value:
        return get_user_ids_by_region(str(value))
    return get_all_user_ids()


async def _prompt_for_message(call: CallbackQuery, lang: str, user_id: int) -> None:
    bot = call.bot
    TgConfig.STATE[user_id] = 'waiting_for_message'
    TgConfig.STATE[f'{user_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        t(lang, 'broadcast_prompt_message'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back('console'),
    )


async def _show_segments(call: CallbackQuery, lang: str, user_id: int) -> None:
    bot = call.bot
    TgConfig.STATE[user_id] = 'broadcast_select_segment'
    TgConfig.STATE.pop(_filter_key(user_id), None)
    TgConfig.STATE.pop(f'{user_id}_regions', None)
    await bot.edit_message_text(
        t(lang, 'broadcast_choose_segment'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=_segment_markup(lang),
    )


async def send_message_callback_handler(call: CallbackQuery):
    if not is_enabled("broadcast"):
        disabled_text = feature_disabled_text(call.from_user.id if call.from_user else None)
        await call.answer(disabled_text, show_alert=True)
        return
    _, user_id = await get_bot_user_ids(call)
    role = check_role(user_id)
    lang = get_user_language(user_id) or 'en'
    if role & Permission.BROADCAST:
        await _show_segments(call, lang, user_id)
        return
    await call.answer(t(lang, 'insufficient_rights'))


async def broadcast_segment_root(call: CallbackQuery) -> None:
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    await _show_segments(call, lang, user_id)


async def broadcast_segment_choice(call: CallbackQuery) -> None:
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    segment = call.data.split(':')[-1]
    if segment in {'all', 'active', 'inactive', 'resellers', 'no_activity'}:
        _set_filter(user_id, segment, None)
        await _prompt_for_message(call, lang, user_id)
    elif segment == 'city':
        await bot.edit_message_text(
            t(lang, 'broadcast_pick_city'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=_cities_markup(lang),
        )
    elif segment == 'region':
        await bot.edit_message_text(
            t(lang, 'broadcast_pick_region'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=_regions_markup(lang, user_id),
        )


async def broadcast_city_choice(call: CallbackQuery) -> None:
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    city_id = call.data.split(':')[-1]
    _set_filter(user_id, 'city', int(city_id))
    await _prompt_for_message(call, lang, user_id)


async def broadcast_region_choice(call: CallbackQuery) -> None:
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    index = int(call.data.split(':')[-1])
    regions_key = f'{user_id}_regions'
    regions = TgConfig.STATE.get(regions_key) or []
    if index >= len(regions):
        await _show_segments(call, lang, user_id)
        return
    region = regions[index]
    TgConfig.STATE.pop(regions_key, None)
    _set_filter(user_id, 'region', region)
    await _prompt_for_message(call, lang, user_id)


async def broadcast_messages(message: Message):
    if not is_enabled("broadcast"):
        disabled_text = feature_disabled_text(message.from_user.id if message.from_user else None)
        await message.reply(disabled_text)
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_message_id", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    lang = get_user_language(user_id) or 'en'
    msg = message.text
    message_id = TgConfig.STATE.get(f'{user_id}_message_id')
    TgConfig.STATE[user_id] = None
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    filter_data = TgConfig.STATE.pop(_filter_key(user_id), ('all', None))
    recipients = _resolve_recipients(filter_data)
    if not recipients:
        await bot.edit_message_text(
            t(lang, 'broadcast_no_recipients'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=back('console'),
        )
        return
    sent = 0
    for recipient in recipients:
        await asyncio.sleep(0.1)
        try:
            await bot.send_message(chat_id=int(recipient), text=msg, reply_markup=close())
            sent += 1
        except BotBlocked:
            continue
    await bot.edit_message_text(
        t(lang, 'broadcast_completed', count=sent),
        chat_id=message.chat.id,
        message_id=message_id,
        reply_markup=back('console'),
    )
    logger.info(
        "Broadcast by %s sent to %s users using filter %s",
        user_id,
        sent,
        filter_data,
    )


def register_mailing(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(send_message_callback_handler, lambda c: c.data == 'send_message')
    dp.register_callback_query_handler(broadcast_segment_root, lambda c: c.data == 'broadcast:segments')
    dp.register_callback_query_handler(
        broadcast_segment_choice,
        lambda c: c.data.startswith('broadcast:segment:'),
    )
    dp.register_callback_query_handler(broadcast_city_choice, lambda c: c.data.startswith('broadcast:city:'))
    dp.register_callback_query_handler(broadcast_region_choice, lambda c: c.data.startswith('broadcast:region_index:'))
    dp.register_message_handler(
        broadcast_messages,
        lambda c: TgConfig.STATE.get(c.from_user.id) == 'waiting_for_message',
    )