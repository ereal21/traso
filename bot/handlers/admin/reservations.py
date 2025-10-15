from __future__ import annotations

from aiogram import Dispatcher
from aiogram.types import CallbackQuery

from bot.database.methods import (
    check_role,
    get_user_language,
    get_reservations_by_status,
    get_reservation,
)
from bot.database.methods.update import release_reservation
from bot.database.methods.read import select_item_values_amount, check_value
from bot.database.models import Permission
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import reservations_list_markup, reservation_actions_keyboard
from bot.localization import t
from bot.utils import notify_restock
from bot.utils.feature_config import feature_disabled_text, is_enabled


async def _ensure_feature(call: CallbackQuery) -> bool:
    if is_enabled('reservations'):
        return True
    await call.answer(feature_disabled_text(call.from_user.id), show_alert=True)
    return False


async def reservations_entry(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    role = check_role(admin_id)
    if role == Permission.USE:
        await call.answer(t(lang, 'insufficient_rights'), show_alert=True)
        return
    reservations = get_reservations_by_status('active')
    if not reservations:
        await bot.edit_message_text(
            t(lang, 'reservations_none'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=reservations_list_markup([], lang),
        )
        return
    await bot.edit_message_text(
        t(lang, 'reservations_title', count=len(reservations)),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=reservations_list_markup(reservations, lang),
    )


async def reservation_view(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    reservation_id = int(call.data.split('_')[-1])
    reservation = get_reservation(reservation_id)
    if reservation is None:
        await call.answer(t(lang, 'reservations_not_found'), show_alert=True)
        return
    text = t(
        lang,
        'reservation_detail',
        reservation_id=reservation.id,
        user=reservation.user_id,
        item=reservation.item_name,
        status=reservation.status,
        reserved_at=reservation.reserved_at,
        expires_at=reservation.expires_at or '-',
    )
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=reservation_actions_keyboard(reservation.id, lang),
    )


async def reservation_release_action(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    reservation_id = int(call.data.split('_')[-1])
    reservation = get_reservation(reservation_id)
    if reservation is None:
        await call.answer(t(lang, 'reservations_not_found'), show_alert=True)
        return
    was_empty = (
        select_item_values_amount(reservation.item_name) == 0
        and not check_value(reservation.item_name)
    )
    release_reservation(reservation_id)
    if was_empty:
        await notify_restock(bot, reservation.item_name)
    user_lang = get_user_language(reservation.user_id) or 'en'
    try:
        await bot.send_message(
            reservation.user_id,
            t(user_lang, 'reservation_released_notice', item=reservation.item_name),
        )
    except Exception:
        pass
    await call.answer(t(lang, 'reservation_released'))
    await reservations_entry(call)


def register_reservations_management(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(reservations_entry, lambda c: c.data == 'reservations', state='*')
    dp.register_callback_query_handler(
        reservation_view,
        lambda c: c.data.startswith('reservation_view_'),
        state='*',
    )
    dp.register_callback_query_handler(
        reservation_release_action,
        lambda c: c.data.startswith('reservation_release_'),
        state='*',
    )