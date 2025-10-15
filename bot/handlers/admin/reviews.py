from __future__ import annotations

import html

from aiogram import Dispatcher
from aiogram.types import CallbackQuery

from bot.database.methods import (
    check_role,
    get_user_language,
    get_reviews_by_status,
    get_review,
    update_review_status,
)
from bot.database.models import Permission
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import reviews_menu, reviews_list_markup, review_actions_keyboard
from bot.localization import t
from bot.utils.feature_config import feature_disabled_text, is_enabled


def _has_access(role: int) -> bool:
    return role != Permission.USE


async def _ensure_feature(call: CallbackQuery, feature: str) -> bool:
    if is_enabled(feature):
        return True
    await call.answer(feature_disabled_text(call.from_user.id), show_alert=True)
    return False


async def reviews_entry(call: CallbackQuery) -> None:
    if not await _ensure_feature(call, 'reviews'):
        return
    bot, admin_id = await get_bot_user_ids(call)
    role = check_role(admin_id)
    lang = get_user_language(admin_id) or 'en'
    if not _has_access(role):
        await call.answer(t(lang, 'insufficient_rights'), show_alert=True)
        return
    await bot.edit_message_text(
        t(lang, 'reviews_title'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=reviews_menu(lang),
    )


async def reviews_status(call: CallbackQuery) -> None:
    if not await _ensure_feature(call, 'reviews'):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    status = call.data.split('_')[-1]
    reviews = get_reviews_by_status(status)
    if not reviews:
        await bot.edit_message_text(
            t(lang, 'reviews_none'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=reviews_menu(lang),
        )
        return
    status_text = t(lang, f'review_status_{status}')
    header = t(lang, 'reviews_list_header', status=status_text, count=len(reviews))
    await bot.edit_message_text(
        header,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=reviews_list_markup(reviews, lang),
    )


async def review_view(call: CallbackQuery) -> None:
    if not await _ensure_feature(call, 'reviews'):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    review_id = int(call.data.split('_')[-1])
    review = get_review(review_id)
    if review is None:
        await call.answer(t(lang, 'reviews_not_found'), show_alert=True)
        return
    comment = review.comment or t(lang, 'no_comment_provided')
    comment = html.escape(comment)
    status_text = t(lang, f'review_status_{review.status}')
    body = t(
        lang,
        'review_detail',
        user=review.user_id,
        item=review.item_name or '-',
        service=review.service_rating,
        product=review.product_rating,
        comment=comment,
        status=status_text,
        created=review.created_at,
    )
    await bot.edit_message_text(
        body,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=review_actions_keyboard(review_id, review.status, lang),
        parse_mode='HTML',
    )


async def review_update(call: CallbackQuery) -> None:
    if not await _ensure_feature(call, 'reviews'):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    parts = call.data.split('_')
    action = parts[1]
    review_id = int(parts[-1])
    review = get_review(review_id)
    if review is None:
        await call.answer(t(lang, 'reviews_not_found'), show_alert=True)
        return
    new_status = 'approved' if action == 'approve' else 'rejected'
    update_review_status(review_id, new_status, admin_id)
    await call.answer(t(lang, 'review_status_updated'))
    updated = get_review(review_id)
    if updated:
        status_text = t(lang, f'review_status_{updated.status}')
        comment = html.escape(updated.comment or t(lang, 'no_comment_provided'))
        text = t(
            lang,
            'review_detail',
            user=updated.user_id,
            item=updated.item_name or '-',
            service=updated.service_rating,
            product=updated.product_rating,
            comment=comment,
            status=status_text,
            created=updated.created_at,
        )
        await bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=review_actions_keyboard(review_id, updated.status, lang),
            parse_mode='HTML',
        )


def register_reviews_management(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(reviews_entry, lambda c: c.data == 'reviews', state='*')
    dp.register_callback_query_handler(
        reviews_status,
        lambda c: c.data.startswith('reviews_status_'),
        state='*',
    )
    dp.register_callback_query_handler(
        review_view,
        lambda c: c.data.startswith('review_view_'),
        state='*',
    )
    dp.register_callback_query_handler(
        review_update,
        lambda c: c.data.startswith(('review_approve_', 'review_reject_')),
        state='*',
    )