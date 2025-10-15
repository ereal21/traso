from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message

from bot.database.methods import (
    check_role,
    get_user_language,
    check_user,
    check_user_by_username,
    create_manual_payment_record,
    create_operation,
    get_manual_payments,
    update_balance,
)
from bot.database.models import Permission
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import manual_payments_menu
from bot.localization import t
from bot.misc import TgConfig
from bot.utils.feature_config import feature_disabled_text, is_enabled


def _format_user_display(user) -> str:
    if not user:
        return '—'
    if getattr(user, 'username', None):
        return f"@{user.username}"
    return str(getattr(user, 'telegram_id', getattr(user, 'user_id', '')))


async def _ensure_feature(call: CallbackQuery) -> bool:
    if is_enabled('manual_payments'):
        return True
    await call.answer(feature_disabled_text(call.from_user.id), show_alert=True)
    return False


async def manual_payments_entry(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    role = check_role(admin_id)
    lang = get_user_language(admin_id) or 'en'
    if not (role & (Permission.OWN | Permission.USERS_MANAGE)):
        await call.answer(t(lang, 'insufficient_rights'), show_alert=True)
        return
    await bot.edit_message_text(
        t(lang, 'manual_payments_title'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=manual_payments_menu(lang),
    )


async def manual_payments_add(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    TgConfig.STATE[admin_id] = 'manual_payment_user'
    TgConfig.STATE[f'{admin_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        t(lang, 'manual_payments_prompt_user'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


async def manual_payment_user_step(message: Message) -> None:
    bot, admin_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(admin_id) != 'manual_payment_user':
        return
    lang = get_user_language(admin_id) or 'en'
    username = (message.text or '').strip().lstrip('@')
    TgConfig.STATE[admin_id] = None
    await bot.delete_message(message.chat.id, message.message_id)
    user = check_user(int(username)) if username.isdigit() else check_user_by_username(username)
    if not user:
        message_id = TgConfig.STATE.get(f'{admin_id}_message_id')
        await bot.edit_message_text(
            t(lang, 'manual_payments_invalid_user'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=manual_payments_menu(lang),
        )
        return
    TgConfig.STATE[f'{admin_id}_manual_target'] = user.telegram_id
    TgConfig.STATE[f'{admin_id}_manual_target_display'] = _format_user_display(user)
    TgConfig.STATE[admin_id] = 'manual_payment_amount'
    message_id = TgConfig.STATE.get(f'{admin_id}_message_id')
    await bot.edit_message_text(
        t(lang, 'manual_payments_prompt_amount'),
        chat_id=message.chat.id,
        message_id=message_id,
    )


async def manual_payment_amount_step(message: Message) -> None:
    bot, admin_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(admin_id) != 'manual_payment_amount':
        return
    lang = get_user_language(admin_id) or 'en'
    amount_text = message.text.strip()
    target_id = TgConfig.STATE.get(f'{admin_id}_manual_target')
    message_id = TgConfig.STATE.get(f'{admin_id}_message_id')
    await bot.delete_message(message.chat.id, message.message_id)
    try:
        amount = Decimal(amount_text)
    except (InvalidOperation, ValueError):
        await bot.edit_message_text(
            t(lang, 'manual_payments_invalid_amount'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=manual_payments_menu(lang),
        )
        TgConfig.STATE[admin_id] = None
        TgConfig.STATE.pop(f'{admin_id}_manual_target_display', None)
        TgConfig.STATE.pop(f'{admin_id}_manual_target', None)
        return
    if amount <= 0 or amount % 1 != 0:
        await bot.edit_message_text(
            t(lang, 'manual_payments_invalid_amount'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=manual_payments_menu(lang),
        )
        TgConfig.STATE[admin_id] = None
        TgConfig.STATE.pop(f'{admin_id}_manual_target_display', None)
        TgConfig.STATE.pop(f'{admin_id}_manual_target', None)
        return
    TgConfig.STATE[f'{admin_id}_manual_amount'] = int(amount)
    TgConfig.STATE[admin_id] = 'manual_payment_note'
    await bot.edit_message_text(
        t(lang, 'manual_payments_prompt_note'),
        chat_id=message.chat.id,
        message_id=message_id,
    )


async def manual_payment_note_step(message: Message) -> None:
    bot, admin_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(admin_id) != 'manual_payment_note':
        return
    lang = get_user_language(admin_id) or 'en'
    note = message.text.strip()
    target_id = TgConfig.STATE.pop(f'{admin_id}_manual_target', None)
    amount = TgConfig.STATE.pop(f'{admin_id}_manual_amount', None)
    target_display = TgConfig.STATE.pop(f'{admin_id}_manual_target_display', None)
    message_id = TgConfig.STATE.pop(f'{admin_id}_message_id', None)
    TgConfig.STATE[admin_id] = None
    await bot.delete_message(message.chat.id, message.message_id)
    if target_id is None or amount is None:
        return
    amount_value = int(amount)
    update_balance(target_id, amount_value)
    create_operation(target_id, amount_value, message.date.isoformat())
    create_manual_payment_record(
        user_id=target_id,
        amount=amount_value,
        currency='EUR',
        created_by=admin_id,
        note=note or None,
    )
    display = target_display or str(target_id)
    await bot.edit_message_text(
        t(lang, 'manual_payments_completed', amount=f'{amount_value:.2f}', user=display),
        chat_id=message.chat.id,
        message_id=message_id,
        reply_markup=manual_payments_menu(lang),
    )
    user_lang = get_user_language(target_id) or 'en'
    try:
        await bot.send_message(
            target_id,
            t(user_lang, 'manual_payment_user_notice', amount=f'{amount_value:.2f}'),
        )
    except Exception:
        pass


async def manual_payments_history(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    history = get_manual_payments(limit=15)
    if not history:
        text = t(lang, 'manual_payments_none')
    else:
        lines = [t(lang, 'manual_payments_history_header')]
        for entry in history:
            lines.append(
                t(
                    lang,
                    'manual_payments_history_line',
                    entry_id=entry.id,
                    user=_format_user_display(entry.user if hasattr(entry, 'user') else check_user(entry.user_id)),
                    amount=f'{entry.amount:.2f}',
                    admin=_format_user_display(entry.admin if hasattr(entry, 'admin') else check_user(entry.created_by)),
                    note=entry.note or '-',
                    created=entry.created_at,
                )
            )
        text = '\n'.join(lines)
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=manual_payments_menu(lang),
    )


def register_manual_payments(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(manual_payments_entry, lambda c: c.data == 'manual_payments', state='*')
    dp.register_callback_query_handler(manual_payments_add, lambda c: c.data == 'manual_payments_add', state='*')
    dp.register_callback_query_handler(manual_payments_history, lambda c: c.data == 'manual_payments_history', state='*')
    dp.register_message_handler(
        manual_payment_user_step,
        lambda m: TgConfig.STATE.get(m.from_user.id) == 'manual_payment_user',
        state='*',
    )
    dp.register_message_handler(
        manual_payment_amount_step,
        lambda m: TgConfig.STATE.get(m.from_user.id) == 'manual_payment_amount',
        state='*',
    )
    dp.register_message_handler(
        manual_payment_note_step,
        lambda m: TgConfig.STATE.get(m.from_user.id) == 'manual_payment_note',
        state='*',
    )