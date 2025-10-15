from __future__ import annotations

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message

from bot.database.methods import (
    check_role,
    get_user_language,
    create_media_asset_record,
    get_media_assets,
    get_media_asset,
)
from bot.database.methods.delete import delete_media_asset
from bot.database.models import Permission
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import media_library_menu, media_asset_actions, media_list_keyboard
from bot.localization import t
from bot.misc import TgConfig
from bot.utils.feature_config import feature_disabled_text, is_enabled


async def _ensure_feature(call: CallbackQuery) -> bool:
    if is_enabled('media_library'):
        return True
    await call.answer(feature_disabled_text(call.from_user.id), show_alert=True)
    return False


async def media_entry(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    role = check_role(admin_id)
    if role == Permission.USE:
        await call.answer(t(lang, 'insufficient_rights'), show_alert=True)
        return
    await bot.edit_message_text(
        t(lang, 'media_title'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=media_library_menu(lang),
    )


async def media_upload_prompt(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    TgConfig.STATE[admin_id] = 'media_upload'
    TgConfig.STATE[f'{admin_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        t(lang, 'media_upload_prompt'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


async def media_upload_step(message: Message) -> None:
    bot, admin_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(admin_id) != 'media_upload':
        return
    lang = get_user_language(admin_id) or 'en'
    message_id = TgConfig.STATE.pop(f'{admin_id}_message_id', None)
    TgConfig.STATE[admin_id] = None
    file_id = None
    file_unique_id = None
    media_type = None
    caption = message.caption
    if message.photo:
        file = message.photo[-1]
        file_id = file.file_id
        file_unique_id = file.file_unique_id
        media_type = 'photo'
    elif message.video:
        file = message.video
        file_id = file.file_id
        file_unique_id = file.file_unique_id
        media_type = 'video'
    elif message.document:
        file = message.document
        file_id = file.file_id
        file_unique_id = file.file_unique_id
        media_type = 'document'
    if not media_type:
        await bot.delete_message(message.chat.id, message.message_id)
        if message_id is not None:
            await bot.edit_message_text(
                t(lang, 'media_upload_invalid'),
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=media_library_menu(lang),
            )
        return
    create_media_asset_record(
        file_id=file_id,
        file_type=media_type,
        created_by=admin_id,
        caption=caption,
        title=message.caption or None,
        file_unique_id=file_unique_id,
    )
    await bot.delete_message(message.chat.id, message.message_id)
    if message_id is not None:
        await bot.edit_message_text(
            t(lang, 'media_saved'),
            chat_id=message.chat.id,
            message_id=message_id,
            reply_markup=media_library_menu(lang),
        )


async def media_list(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    assets = get_media_assets(limit=20)
    if not assets:
        await bot.edit_message_text(
            t(lang, 'media_no_assets'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=media_library_menu(lang),
        )
        return
    lines = [t(lang, 'media_list_header')]
    markup = media_list_keyboard(assets, lang)
    for asset in assets:
        lines.append(t(lang, 'media_list_line', asset_id=asset.id, media_type=asset.file_type, created=asset.created_at))
    await bot.edit_message_text(
        '\n'.join(lines),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


async def media_view(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    asset_id = int(call.data.split('_')[-1])
    asset = get_media_asset(asset_id)
    if asset is None:
        await call.answer(t(lang, 'media_not_found'), show_alert=True)
        return
    text = t(
        lang,
        'media_detail',
        asset_id=asset.id,
        media_type=asset.file_type,
        created=asset.created_at,
        caption=asset.caption or '-',
    )
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=media_asset_actions(asset.id, lang),
    )


async def media_send(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    asset_id = int(call.data.split('_')[-1])
    lang = get_user_language(admin_id) or 'en'
    asset = get_media_asset(asset_id)
    if asset is None:
        await call.answer(t(lang, 'media_not_found'), show_alert=True)
        return
    try:
        if asset.file_type == 'photo':
            await bot.send_photo(admin_id, asset.file_id, caption=asset.caption)
        elif asset.file_type == 'video':
            await bot.send_video(admin_id, asset.file_id, caption=asset.caption)
        else:
            await bot.send_document(admin_id, asset.file_id, caption=asset.caption)
    except Exception:
        await call.answer(t(lang, 'media_send_failed'), show_alert=True)
        return
    await call.answer(t(lang, 'media_sent'))


async def media_delete(call: CallbackQuery) -> None:
    if not await _ensure_feature(call):
        return
    bot, admin_id = await get_bot_user_ids(call)
    lang = get_user_language(admin_id) or 'en'
    asset_id = int(call.data.split('_')[-1])
    asset = get_media_asset(asset_id)
    if asset is None:
        await call.answer(t(lang, 'media_not_found'), show_alert=True)
        return
    delete_media_asset(asset_id)
    await call.answer(t(lang, 'media_deleted'))
    await media_entry(call)


def register_media_library(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(media_entry, lambda c: c.data == 'media_library', state='*')
    dp.register_callback_query_handler(media_upload_prompt, lambda c: c.data == 'media_upload', state='*')
    dp.register_callback_query_handler(media_list, lambda c: c.data == 'media_list', state='*')
    dp.register_callback_query_handler(media_view, lambda c: c.data.startswith('media_view_'), state='*')
    dp.register_callback_query_handler(media_send, lambda c: c.data.startswith('media_send_'), state='*')
    dp.register_callback_query_handler(media_delete, lambda c: c.data.startswith('media_delete_'), state='*')
    dp.register_message_handler(
        media_upload_step,
        lambda m: TgConfig.STATE.get(m.from_user.id) == 'media_upload',
        content_types=['photo', 'video', 'document'],
        state='*',
    )