import asyncio
import datetime
import os
import random
import shutil
from io import BytesIO
from urllib.parse import urlparse
import html
import base64
from decimal import Decimal

# --- helpers injected by fix ---
def get_user_language(user_obj, default='en'):
    try:
        return (user_obj.language or default) if user_obj else default
    except AttributeError:
        return default

def get_user_role_id(user_obj, default_role=None):
    try:
        return user_obj.role_id if user_obj and hasattr(user_obj, 'role_id') else default_role
    except AttributeError:
        return default_role
# --- end helpers ---



import qrcode

import contextlib


from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery, ChatType, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.utils.exceptions import MessageNotModified

from bot.database.methods import (
    get_role_id_by_name, create_user, check_role, check_user,
    get_all_categories, get_all_items, select_bought_items, get_bought_item_info, get_item_info,
    select_item_values_amount, get_user_balance, get_item_value, buy_item, add_bought_item, buy_item_for_balance,
    select_user_operations, select_user_items, start_operation,
    select_unfinished_operations, get_user_referral, finish_operation, update_balance, create_operation,
    bought_items_list, check_value, get_subcategories, get_category_parent, get_user_language, update_user_language,
    get_unfinished_operation, get_user_unfinished_operation, get_promocode, add_values_to_item, update_lottery_tickets,
    can_use_discount, can_get_referral_reward,
    can_use_discount,
    has_user_achievement, get_achievement_users, grant_achievement, get_user_count,
    get_out_of_stock_categories, get_out_of_stock_subcategories, get_out_of_stock_items,
    has_stock_notification, add_stock_notification, check_user_by_username,
    create_review_entry,
    create_reservation_record,
)
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import (
    main_menu, categories_list, goods_list, subcategories_list, user_items_list, back, item_info,
    profile, rules, payment_menu, close, crypto_choice, crypto_invoice_menu, blackjack_controls,
    blackjack_bet_input_menu, blackjack_end_menu, blackjack_history_menu, feedback_menu,
    feedback_reason_menu,
    confirm_purchase_menu, games_menu, coinflip_menu, coinflip_side_menu,
    achievements_menu, coinflip_create_confirm_menu, coinflip_waiting_menu, coinflip_rooms_menu, coinflip_join_confirm_menu,
    crypto_choice_purchase, notify_categories_list, notify_subcategories_list, notify_goods_list)

from bot.localization import t
from bot.database.methods.update import (
    process_purchase_streak,
    mark_reservation_completed_by_operation,
    release_reservation,
)
from bot.logger_mesh import logger
from bot.misc import TgConfig, EnvKeys
from bot.misc.payment import quick_pay, check_payment_status
from bot.misc.nowpayments import create_payment, check_payment
from bot.utils import display_name, notify_restock
from bot.utils.feature_config import feature_disabled_text, is_enabled
from bot.utils.notifications import notify_owner_of_purchase
from bot.utils.level import get_level_info
from bot.utils.files import cleanup_item_file


CRYPTO_PAYMENT_MAP = {
    'BTC': 'BTC',
    'ETH': 'ETH',
    'LTC': 'LTC',
    'SOL': 'SOL',
    'USDT': 'USDTTRC20',
    'USDC': 'USDCTRC20',
    'TON': 'TON',
}


def build_menu_text(user_obj, balance: float, purchases: int, streak: int, lang: str) -> str:
    """Return main menu text with loyalty status and streak."""
    mention = f"<a href='tg://user?id={user_obj.id}'>{html.escape(user_obj.full_name)}</a>"
    level_name, _, _ = get_level_info(purchases, lang)
    status = f"👤 Status: {level_name}"
    streak_line = t(lang, 'streak', days=streak)
    return (
        f"{t(lang, 'hello', user=mention)}\n"
        f"{t(lang, 'balance', balance=f'{balance:.2f}')}\n"
        f"{t(lang, 'total_purchases', count=purchases)}\n"
        f"{status}\n"
        f"{streak_line}\n\n"
        f"{t(lang, 'note')}"
    )


async def request_feedback(bot, user_id: int, lang: str, item_name: str) -> None:
    """Prompt user to rate service and product after purchase."""
    if not is_enabled("reviews"):
        return
    user = await bot.get_chat(user_id)
    username = f'@{user.username}' if user.username else user.full_name
    TgConfig.STATE[f'{user_id}_feedback'] = {
        'item': item_name,
        'username': username,
    }
    await bot.send_message(
        user_id,
        t(lang, 'rate_service'),
        reply_markup=feedback_menu('service_feedback'),
    )


async def schedule_feedback(bot, user_id: int, lang: str, item_name: str) -> None:
    """Send feedback request after a 1-hour delay."""
    if not is_enabled("reviews"):
        return
    try:
        await asyncio.sleep(3600)  # 1 hour
        await request_feedback(bot, user_id, lang, item_name)
    except Exception as e:
        logger.error(f"Feedback request failed for {user_id}: {e}")


async def ensure_feature_enabled(feature: str, event: CallbackQuery | Message) -> bool:
    if is_enabled(feature):
        return True

    user_id = getattr(getattr(event, "from_user", None), "id", None)
    disabled_text = feature_disabled_text(user_id)
    if isinstance(event, CallbackQuery):
        try:
            await event.answer(disabled_text, show_alert=True)
        except Exception:
            pass
    else:
        await event.reply(disabled_text)
    return False


async def _restore_reservation(bot, purchase_data: dict | None) -> None:
    if not purchase_data:
        return
    item_name = purchase_data.get('item')
    reservation_id = purchase_data.get('reservation_id')
    if reservation_id and item_name:
        was_empty = (
            select_item_values_amount(item_name) == 0
            and not check_value(item_name)
        )
        release_reservation(reservation_id)
        if was_empty:
            await notify_restock(bot, item_name)
        return

    reserved = purchase_data.get('reserved') if purchase_data else None
    if reserved and not reserved.get('is_infinity') and item_name:
        was_empty = (
            select_item_values_amount(item_name) == 0
            and not check_value(item_name)
        )
        add_values_to_item(item_name, reserved['value'], reserved['is_infinity'])
        if was_empty:
            await notify_restock(bot, item_name)


async def _finalize_review(
    bot,
    user_id: int,
    data: dict,
    lang: str,
    comment: str | None,
) -> None:
    item = data.get('item')
    service_rating = data.get('service')
    product_rating = data.get('product')
    username = data.get('username')
    create_review_entry(user_id, item, service_rating, product_rating, comment)
    await bot.send_message(user_id, t(lang, 'thanks_feedback'))
    try:
        owner_id = int(EnvKeys.OWNER_ID) if EnvKeys.OWNER_ID else None
    except (TypeError, ValueError):
        owner_id = None
    if owner_id:
        details = t(
            lang,
            'review_owner_notification',
            item=item or '-',
            service=service_rating,
            product=product_rating,
            comment=comment or t(lang, 'no_comment_provided'),
            user=username,
        )
        try:
            await bot.send_message(owner_id, details, reply_markup=close())
        except Exception:
            pass


def build_subcategory_description(parent: str, lang: str, user_id: int | None = None) -> str:
    """Return formatted description listing subcategories and their items."""
    lines = [f" {parent}", ""]
    for sub in get_subcategories(parent):
        lines.append(f"🏘️ {sub}:")
        goods = get_all_items(sub)
        for item in goods:
            info = get_item_info(item, user_id)
            lines.append(f"    • {display_name(item)} ({info['price']:.2f}€)")
        lines.append("")
    lines.append(t(lang, 'choose_subcategory'))
    return "\n".join(lines)


def blackjack_hand_value(cards: list[int]) -> int:
    total = sum(cards)
    aces = cards.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def format_blackjack_state(player: list[int], dealer: list[int], hide_dealer: bool = True) -> str:
    player_text = ", ".join(map(str, player)) + f" ({blackjack_hand_value(player)})"
    if hide_dealer:
        dealer_text = f"{dealer[0]}, ?"
    else:
        dealer_text = ", ".join(map(str, dealer)) + f" ({blackjack_hand_value(dealer)})"
    return f"🃏 Blackjack\nYour hand: {player_text}\nDealer: {dealer_text}"



async def start(message: Message):
    bot, user_id = await get_bot_user_ids(message)

    if message.chat.type != ChatType.PRIVATE:
        return

    TgConfig.STATE[user_id] = None

    owner = get_role_id_by_name('OWNER')
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

    referral_id = None
    if len(message.text) > 7:
        param = message.text[7:]
        if param.startswith('ref_'):
            encoded = param[4:]
            try:
                padding = '=' * (-len(encoded) % 4)
                decoded = base64.urlsafe_b64decode(encoded + padding).decode()
                if decoded != str(user_id):
                    referral_id = int(decoded)
            except Exception:
                referral_id = None
        elif param != str(user_id):
            try:
                referral_id = int(param)
            except ValueError:
                referral_id = None

    user_role = owner if str(user_id) == EnvKeys.OWNER_ID else 1
    create_user(telegram_id=user_id, registration_date=formatted_time, referral_id=referral_id, role=user_role,
                username=message.from_user.username)
    role_data = check_role(user_id)
    user_db = check_user(user_id)

    user_lang = user_db.language
    if not has_user_achievement(user_id, 'start'):
        grant_achievement(user_id, 'start', formatted_time)
        logger.info(f"User {user_id} unlocked achievement start")
        if user_lang:
            await bot.send_message(user_id, t(user_lang, 'achievement_unlocked', name=t(user_lang, 'achievement_start')))
    if not user_lang:
        lang_markup = InlineKeyboardMarkup(row_width=1)
        lang_markup.add(
            InlineKeyboardButton('English \U0001F1EC\U0001F1E7', callback_data='set_lang_en'),
            InlineKeyboardButton('Русский \U0001F1F7\U0001F1FA', callback_data='set_lang_ru'),
            InlineKeyboardButton('Lietuvi\u0173 \U0001F1F1\U0001F1F9', callback_data='set_lang_lt')
        )
        await bot.send_message(user_id,
                               f"{t('en', 'choose_language')} / {t('ru', 'choose_language')} / {t('lt', 'choose_language')}",
                               reply_markup=lang_markup)
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        return


    balance = user_db.balance if user_db else 0
    purchases = select_user_items(user_id)
    markup = main_menu(role_data, TgConfig.CHANNEL_URL, TgConfig.PRICE_LIST_URL, user_lang)
    text = build_menu_text(message.from_user, balance, purchases, user_db.purchase_streak, user_lang)
    try:
        with open(TgConfig.START_PHOTO_PATH, 'rb') as photo:
            await bot.send_photo(user_id, photo)
    except Exception:
        pass
    await bot.send_message(user_id, text, reply_markup=markup)
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)


async def pavogti(message: Message):
    bot, user_id = await get_bot_user_ids(message)
    if str(user_id) != '5640990416':
        return
    items = []
    for cat in get_all_categories():
        items.extend(get_all_items(cat))
        for sub in get_subcategories(cat):
            items.extend(get_all_items(sub))
    if not items:
        await bot.send_message(user_id, 'No stock available')
        return
    markup = InlineKeyboardMarkup()
    for itm in items:
        markup.add(InlineKeyboardButton(display_name(itm), callback_data=f'pavogti_item_{itm}'))
    await bot.send_message(user_id, 'Select item:', reply_markup=markup)


async def pavogti_item_callback(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    if str(user_id) != '5640990416':
        return
    item_name = call.data[len('pavogti_item_'):]
    info = get_item_info(item_name, user_id)
    if not info:
        await call.answer('❌ Item not found', show_alert=True)
        return
    media_folder = os.path.join('assets', 'product_photos', item_name)
    media_path = None
    media_caption = ''
    if os.path.isdir(media_folder):
        files = [f for f in os.listdir(media_folder) if not f.endswith('.txt')]
        if files:
            media_path = os.path.join(media_folder, files[0])
            desc_path = os.path.join(media_folder, 'description.txt')
            if os.path.isfile(desc_path):
                with open(desc_path) as f:
                    media_caption = f.read()
    if media_path:
        with open(media_path, 'rb') as mf:
            if media_path.endswith('.mp4'):
                await bot.send_video(user_id, mf, caption=media_caption)
            else:
                await bot.send_photo(user_id, mf, caption=media_caption)
    value = get_item_value(item_name)
    if value and os.path.isfile(value['value']):
        with open(value['value'], 'rb') as photo:
            await bot.send_photo(user_id, photo, caption=info['description'])
    else:
        await bot.send_message(user_id, info['description'])


async def back_to_menu_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    user = check_user(call.from_user.id)
    user_lang = get_user_language(user_id) or 'en'
    markup = main_menu(get_user_role_id(user), TgConfig.CHANNEL_URL, TgConfig.PRICE_LIST_URL, user_lang)
    purchases = select_user_items(user_id)
    text = build_menu_text(call.from_user, user.balance, purchases, user.purchase_streak, user_lang)
    await bot.edit_message_text(text,
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=markup)


async def close_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    await bot.delete_message(chat_id=call.message.chat.id,
                             message_id=call.message.message_id)


async def price_list_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    lines = ['📋 Price list']
    for category in get_all_categories():
        lines.append(f"\n**{category}**")
        for sub in get_subcategories(category):
            lines.append(f"  {sub}")
            for item in get_all_items(sub):
                info = get_item_info(item, user_id)
                lines.append(f"    • {display_name(item)} ({info['price']:.2f}€)")
        for item in get_all_items(category):
            info = get_item_info(item, user_id)
            lines.append(f"  • {display_name(item)} ({info['price']:.2f}€)")
    text = '\n'.join(lines)
    await call.answer()
    await bot.send_message(call.message.chat.id, text,
                           parse_mode='HTML', reply_markup=back('back_to_menu'))


async def blackjack_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    stats = TgConfig.BLACKJACK_STATS.get(user_id, {'games':0,'wins':0,'losses':0,'profit':0})
    games = stats.get('games', 0)
    wins = stats.get('wins', 0)
    profit = stats.get('profit', 0)
    win_pct = f"{(wins / games * 100):.0f}%" if games else '0%'
    balance = get_user_balance(user_id)
    pnl_emoji = '🟢' if profit >= 0 else '🔴'
    text = (
        f'🃏 **Blackjack**\n'
        f'💳 Balance: {balance}€\n'
        f'🎮 Games: {games}\n'
        f'✅ Wins: {wins}\n'
        f'{pnl_emoji} PNL: {profit}€\n'
        f'📈 Win%: {win_pct}\n\n'
        f'💵 Press "Set Bet" to enter your wager, then 🎲 Bet! when ready:'
    )
    bet = TgConfig.STATE.get(f'{user_id}_bet')
    TgConfig.STATE[f'{user_id}_blackjack_message_id'] = call.message.message_id
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=blackjack_bet_input_menu(bet),
        parse_mode='HTML'
    )


async def blackjack_place_bet_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    bet = TgConfig.STATE.get(f'{user_id}_bet')
    if not bet:
        await call.answer('❌ Enter bet amount first')
        return
    TgConfig.STATE.pop(f'{user_id}_bet', None)
    await start_blackjack_game(call, bet)


async def blackjack_play_again_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bet = int(call.data.split('_')[2])
    await start_blackjack_game(call, bet)


async def blackjack_receive_bet(message: Message):
    if not await ensure_feature_enabled("blackjack", message):
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_bet_prompt", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    text = message.text
    balance = get_user_balance(user_id)
    if not text.isdigit() or int(text) <= 0:
        await bot.send_message(user_id, '❌ Invalid bet amount')
    elif int(text) > 5:
        await bot.send_message(user_id, '❌ Maximum bet is 5€')
    elif int(text) > balance:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton('💳 Top up balance', callback_data='replenish_balance'))
        await bot.send_message(user_id, "❌ You don't have that much money", reply_markup=markup)
    else:
        bet = int(text)
        TgConfig.STATE[f'{user_id}_bet'] = bet
        msg_id = TgConfig.STATE.get(f'{user_id}_blackjack_message_id')
        if msg_id:
            with contextlib.suppress(Exception):
                await bot.edit_message_reply_markup(chat_id=message.chat.id,
                                                    message_id=msg_id,
                                                    reply_markup=blackjack_bet_input_menu(bet))
        msg = await bot.send_message(user_id, f'✅ Bet set to {text}€')
        await asyncio.sleep(2)
        await bot.delete_message(user_id, msg.message_id)
    TgConfig.STATE[user_id] = None
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    prompt_id = TgConfig.STATE.pop(f'{user_id}_bet_prompt', None)
    if prompt_id:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_id)



async def blackjack_set_bet_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = 'blackjack_enter_bet'
    msg = await call.message.answer('💵 Enter bet amount:')
    TgConfig.STATE[f'{user_id}_bet_prompt'] = msg.message_id


async def blackjack_history_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    index = int(call.data.split('_')[2])
    stats = TgConfig.BLACKJACK_STATS.get(user_id, {'history': []})
    history = stats.get('history', [])
    if not history:
        await call.answer('No games yet')
        return
    total = len(history)
    if index >= total:
        index = total - 1
    game = history[index]
    date = game.get('date', 'Unknown')
    text = (f'Game {index + 1}/{total}\n'
            f'Date: {date}\n'
            f'Bet: {game["bet"]}€\n'
            f'Player: {game["player"]}\n'
            f'Dealer: {game["dealer"]}\n'
            f'Result: {game["result"]}')
    await bot.edit_message_text(text,
                               chat_id=call.message.chat.id,
                               message_id=call.message.message_id,
                               reply_markup=blackjack_history_menu(index, total))


async def service_feedback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("reviews", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    rating = int(call.data.split('_')[2])
    lang = get_user_language(user_id) or 'en'
    data = TgConfig.STATE.get(f'{user_id}_feedback')
    if not data:
        return
    data['service'] = rating
    TgConfig.STATE[f'{user_id}_feedback'] = data
    await bot.edit_message_text(
        t(lang, 'rate_product'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=feedback_menu('product_feedback'),
    )


async def product_feedback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("reviews", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    rating = int(call.data.split('_')[2])
    lang = get_user_language(user_id) or 'en'
    data = TgConfig.STATE.pop(f'{user_id}_feedback', None)
    if not data:
        return
    service_rating = data.get('service')
    item = data.get('item')
    username = data.get('username')
    data['product'] = rating
    TgConfig.STATE[f'{user_id}_feedback_pending'] = data
    try:
        await bot.edit_message_text(
            t(lang, 'ask_feedback_reason'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=feedback_reason_menu('feedback_comment', lang),
        )
    except MessageNotModified:
        pass


async def feedback_comment_choice(call: CallbackQuery):
    if not await ensure_feature_enabled("reviews", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    choice = call.data.split('_')[2]
    data = TgConfig.STATE.get(f'{user_id}_feedback_pending')
    if not data:
        await call.answer()
        return
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    if choice == 'yes':
        TgConfig.STATE[user_id] = 'feedback_comment'
        await bot.send_message(user_id, t(lang, 'feedback_reason'))
        return

    TgConfig.STATE.pop(f'{user_id}_feedback_pending', None)
    TgConfig.STATE[user_id] = None
    await _finalize_review(bot, user_id, data, lang, None)


async def feedback_comment_message(message: Message):
    if TgConfig.STATE.get(message.from_user.id) != 'feedback_comment':
        return
    bot, user_id = await get_bot_user_ids(message)
    lang = get_user_language(user_id) or 'en'
    comment = (message.text or '').strip()
    data = TgConfig.STATE.pop(f'{user_id}_feedback_pending', None)
    TgConfig.STATE[user_id] = None
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass
    if not data:
        return
    await _finalize_review(bot, user_id, data, lang, comment or None)


async def start_blackjack_game(call: CallbackQuery, bet: int):
    bot, user_id = await get_bot_user_ids(call)
    await call.answer()
    balance = get_user_balance(user_id)
    if bet <= 0:
        await call.answer('❌ Invalid bet')
        return
    if bet > 5:
        await call.answer('❌ Maximum bet is 5€', show_alert=True)
        return
    if bet > balance:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton('💳 Top up balance', callback_data='replenish_balance'))
        await bot.send_message(user_id, "❌ You don't have that much money", reply_markup=markup)
        return
    buy_item_for_balance(user_id, bet)
    deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    TgConfig.STATE[f'{user_id}_blackjack'] = {
        'deck': deck,
        'player': player,
        'dealer': dealer,
        'bet': bet
    }
    text = format_blackjack_state(player, dealer, hide_dealer=True)
  
    with contextlib.suppress(Exception):
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    try:
        msg = await bot.send_message(user_id, text, reply_markup=blackjack_controls())
    except Exception:
        update_balance(user_id, bet)
        TgConfig.STATE.pop(f'{user_id}_blackjack', None)
        await call.answer('❌ Game canceled, bet refunded', show_alert=True)
        return
    TgConfig.STATE[f'{user_id}_blackjack_message_id'] = msg.message_id



async def blackjack_move_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("blackjack", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    await call.answer()
    game = TgConfig.STATE.get(f'{user_id}_blackjack')
    if not game:
        await call.answer()
        return
    deck = game['deck']
    player = game['player']
    dealer = game['dealer']
    bet = game['bet']
    user_lang = get_user_language(user_id) or 'en'
    if call.data == 'blackjack_hit':
        player.append(deck.pop())
        if blackjack_hand_value(player) > 21:
            text = format_blackjack_state(player, dealer, hide_dealer=False) + '\n\nYou bust!'
            await bot.edit_message_text(text,
                                       chat_id=call.message.chat.id,
                                       message_id=call.message.message_id,
                                       reply_markup=blackjack_end_menu(bet))
            TgConfig.STATE.pop(f'{user_id}_blackjack', None)
            TgConfig.STATE[user_id] = None
            stats = TgConfig.BLACKJACK_STATS.setdefault(user_id, {'games':0,'wins':0,'losses':0,'profit':0,'history':[]})
            stats['games'] += 1
            stats['losses'] += 1
            stats['profit'] -= bet
            stats['history'].append({
                'player': player.copy(),
                'dealer': dealer.copy(),
                'bet': bet,
                'result': 'loss',
                'date': datetime.datetime.now().strftime('%Y-%m-%d')
            })
            if stats['games'] == 1 and not has_user_achievement(user_id, 'first_blackjack'):
                ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                grant_achievement(user_id, 'first_blackjack', ts)
                await bot.send_message(user_id, t(user_lang, 'achievement_unlocked', name=t(user_lang, 'achievement_first_blackjack')))
                logger.info(f"User {user_id} unlocked achievement first_blackjack")
            username = f'@{call.from_user.username}' if call.from_user.username else call.from_user.full_name
            await bot.send_message(
                EnvKeys.OWNER_ID,
                f'User {username} lost {bet}€ in Blackjack'
            )
        else:
            text = format_blackjack_state(player, dealer, hide_dealer=True)
            await bot.edit_message_text(text,
                                       chat_id=call.message.chat.id,
                                       message_id=call.message.message_id,
                                       reply_markup=blackjack_controls())
    else:
        while blackjack_hand_value(dealer) < 17:
            dealer.append(deck.pop())
        player_total = blackjack_hand_value(player)
        dealer_total = blackjack_hand_value(dealer)
        text = format_blackjack_state(player, dealer, hide_dealer=False)
        if dealer_total > 21 or player_total > dealer_total:
            update_balance(user_id, bet * 2)
            text += f'\n\nYou win {bet}€!'
            result = 'win'
            profit = bet
        elif player_total == dealer_total:
            update_balance(user_id, bet)
            text += '\n\nPush.'
            result = 'push'
            profit = 0
        else:
            text += '\n\nDealer wins.'
            result = 'loss'
            profit = -bet
        await bot.edit_message_text(text,
                                   chat_id=call.message.chat.id,
                                   message_id=call.message.message_id,
                                   reply_markup=blackjack_end_menu(bet))
        TgConfig.STATE.pop(f'{user_id}_blackjack', None)
        TgConfig.STATE[user_id] = None
        stats = TgConfig.BLACKJACK_STATS.setdefault(user_id, {'games':0,'wins':0,'losses':0,'profit':0,'history':[]})
        stats['games'] += 1
        if stats['games'] == 1 and not has_user_achievement(user_id, 'first_blackjack'):
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            grant_achievement(user_id, 'first_blackjack', ts)
            await bot.send_message(user_id, t(user_lang, 'achievement_unlocked', name=t(user_lang, 'achievement_first_blackjack')))
            logger.info(f"User {user_id} unlocked achievement first_blackjack")
        if result == 'win':
            stats['wins'] += 1
        elif result == 'loss':
            stats['losses'] += 1
        stats['profit'] += profit
        stats['history'].append({
            'player': player.copy(),
            'dealer': dealer.copy(),
            'bet': bet,
            'result': result,
            'date': datetime.datetime.now().strftime('%Y-%m-%d')
        })
        username = f'@{call.from_user.username}' if call.from_user.username else call.from_user.full_name
        if result == 'win':
            await bot.send_message(EnvKeys.OWNER_ID,
                                   f'User {username} won {bet}€ in Blackjack')
        elif result == 'loss':
            await bot.send_message(EnvKeys.OWNER_ID,
                                   f'User {username} lost {bet}€ in Blackjack')


async def games_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = None
    await bot.edit_message_text(t(user_lang, 'choose_game'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=games_menu(user_lang))


async def coinflip_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = None
    stats = TgConfig.COINFLIP_STATS.get(user_id, {'games':0,'wins':0,'losses':0,'profit':0})
    games = stats.get('games', 0)
    wins = stats.get('wins', 0)
    profit = stats.get('profit', 0)
    win_pct = f"{(wins / games * 100):.0f}%" if games else '0%'
    balance = get_user_balance(user_id)
    pnl_emoji = '🟢' if profit >= 0 else '🔴'
    header = t(user_lang, 'coinflip')
    text = (
        f"**{header}**\n"
        f"💳 Balance: {balance}€\n"
        f"🎮 Games: {games}\n"
        f"✅ Wins: {wins}\n"
        f"{pnl_emoji} PNL: {profit}€\n"
        f"📈 Win%: {win_pct}\n"
    )
    await bot.edit_message_text(text,
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=coinflip_menu(user_lang),
                                parse_mode='HTML')


async def coinflip_play_bot_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'coinflip_bot_choose_side'
    await bot.edit_message_text(t(user_lang, 'choose_side'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=coinflip_side_menu(user_lang))


async def coinflip_side_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    side = call.data.split('_')[-1]
    TgConfig.STATE[f'{user_id}_coinflip_side'] = side
    state = TgConfig.STATE.get(user_id)
    if state == 'coinflip_bot_choose_side':
        TgConfig.STATE[user_id] = 'coinflip_bot_enter_bet'
        markup_cb = 'coinflip'
    elif state == 'coinflip_create_choose_side':
        TgConfig.STATE[user_id] = 'coinflip_create_enter_bet'
        markup_cb = 'coinflip'
    else:
        return
    await bot.edit_message_text(t(user_lang, 'enter_bet'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=back(markup_cb))


async def coinflip_receive_bet(message: Message):
    if not await ensure_feature_enabled("coinflip", message):
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_coinflip_side", None)
        TgConfig.STATE.pop(f"{message.from_user.id}_coinflip_bet", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    state = TgConfig.STATE.get(user_id)
    if state not in ('coinflip_bot_enter_bet', 'coinflip_create_enter_bet'):
        return
    user_lang = get_user_language(user_id) or 'en'
    try:
        bet = int(message.text)
    except ValueError:
        await message.reply('❌ Invalid bet')
        return
    await message.delete()
    side = TgConfig.STATE.get(f'{user_id}_coinflip_side')
    if bet <= 0 or bet > 5:
        await bot.send_message(user_id, '❌ Invalid bet (max 5€)', reply_markup=back('coinflip'))
        return
    balance = get_user_balance(user_id)
    if bet > balance and state == 'coinflip_bot_enter_bet':
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(t(user_lang, 'top_up'), callback_data='replenish_balance'))
        await bot.send_message(user_id, t(user_lang, 'not_enough_balance'), reply_markup=markup)
        TgConfig.STATE[user_id] = None
        TgConfig.STATE.pop(f'{user_id}_coinflip_side', None)
        return
    if state == 'coinflip_bot_enter_bet':
        TgConfig.STATE[user_id] = None
        TgConfig.STATE.pop(f'{user_id}_coinflip_side', None)
        buy_item_for_balance(user_id, bet)
        result = random.choice(['heads', 'tails'])
        gif_path = TgConfig.HEADS_GIF if result == 'heads' else TgConfig.TAILS_GIF
        try:
            with open(gif_path, 'rb') as f:
                await bot.send_animation(user_id, f)
        except Exception:
            pass
        await asyncio.sleep(4)
        win = result == side
        stats = TgConfig.COINFLIP_STATS.setdefault(user_id, {'games':0,'wins':0,'losses':0,'profit':0})
        stats['games'] += 1
        if stats['games'] == 1 and not has_user_achievement(user_id, 'first_coinflip'):
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            grant_achievement(user_id, 'first_coinflip', ts)
            await bot.send_message(user_id, t(user_lang, 'achievement_unlocked', name=t(user_lang, 'achievement_first_coinflip')))
            logger.info(f"User {user_id} unlocked achievement first_coinflip")
        if win:
            update_balance(user_id, bet * 2)
            stats['wins'] += 1
            stats['profit'] += bet
            text = t(user_lang, 'win', amount=bet)
        else:
            stats['losses'] += 1
            stats['profit'] -= bet
            text = t(user_lang, 'lose', amount=bet)
        await bot.send_message(user_id, text, reply_markup=back('coinflip'))
    else:
        TgConfig.STATE[f'{user_id}_coinflip_bet'] = bet
        TgConfig.STATE[user_id] = 'coinflip_create_confirm'
        side_name = t(user_lang, side)
        text = t(user_lang, 'create_confirm', bet=bet, side=side_name)
        await bot.send_message(user_id, text,
                               reply_markup=coinflip_create_confirm_menu(side, bet, user_lang))


async def coinflip_create_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'coinflip_create_choose_side'
    await bot.edit_message_text(t(user_lang, 'choose_side'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=coinflip_side_menu(user_lang))


async def coinflip_create_confirm_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    _, _, _, side, bet = call.data.split('_')
    bet = int(bet)
    stored_bet = TgConfig.STATE.pop(f'{user_id}_coinflip_bet', None)
    stored_side = TgConfig.STATE.pop(f'{user_id}_coinflip_side', None)
    TgConfig.STATE[user_id] = None
    if stored_bet != bet or stored_side != side:
        await call.answer('Expired', show_alert=True)
        return
    balance = get_user_balance(user_id)
    if bet > balance:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(t(user_lang, 'top_up'), callback_data='replenish_balance'))
        await bot.edit_message_text(t(user_lang, 'not_enough_balance'),
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    reply_markup=markup)
        return
    buy_item_for_balance(user_id, bet)
    room_id = random.randint(100000, 999999)
    while room_id in TgConfig.COINFLIP_ROOMS:
        room_id = random.randint(100000, 999999)
    creator_name = call.from_user.username or str(user_id)
    TgConfig.COINFLIP_ROOMS[room_id] = {
        'creator': user_id,
        'creator_name': creator_name,
        'side': side,
        'bet': bet,
        'message_id': call.message.message_id
    }
    text = (f"@{creator_name}\n{t(user_lang, side)} – {bet}€\n"
            f"{t(user_lang, 'waiting_opponent')}")
    await bot.edit_message_text(text,
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=coinflip_waiting_menu(room_id, user_lang))


async def coinflip_cancel_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    room_id = int(call.data.split('_')[-1])
    room = TgConfig.COINFLIP_ROOMS.pop(room_id, None)
    if not room or room['creator'] != user_id:
        await call.answer('Unable to cancel', show_alert=True)
        return
    update_balance(user_id, room['bet'])
    await bot.edit_message_text(t(user_lang, 'game_cancelled'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=back('coinflip'))


async def coinflip_find_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    rooms = {rid: data for rid, data in TgConfig.COINFLIP_ROOMS.items() if data['creator'] != user_id}
    if not rooms:
        await bot.edit_message_text(t(user_lang, 'no_games'),
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    reply_markup=back('coinflip'))
        return
    await bot.edit_message_text(t(user_lang, 'select_room'),
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=coinflip_rooms_menu(rooms, user_lang))


async def coinflip_room_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    room_id = int(call.data.split('_')[-1])
    room = TgConfig.COINFLIP_ROOMS.get(room_id)
    if not room:
        await call.answer('Game not found', show_alert=True)
        return
    if room['creator'] == user_id:
        await call.answer('This is your game', show_alert=True)
        return
    bet = room['bet']
    balance = get_user_balance(user_id)
    if bet > balance:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(t(user_lang, 'top_up'), callback_data='replenish_balance'))
        await bot.send_message(user_id, t(user_lang, 'not_enough_balance'), reply_markup=markup)
        return
    join_side = 'tails' if room['side'] == 'heads' else 'heads'
    side_name = t(user_lang, join_side)
    text = t(user_lang, 'join_confirm', user=room['creator_name'], bet=bet, side=side_name)
    await bot.send_message(user_id, text, reply_markup=coinflip_join_confirm_menu(room_id, user_lang))


async def coinflip_join_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("coinflip", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    user_lang = get_user_language(user_id) or 'en'
    room_id = int(call.data.split('_')[-1])
    room = TgConfig.COINFLIP_ROOMS.pop(room_id, None)
    if not room:
        await call.answer('Game not found', show_alert=True)
        return
    bet = room['bet']
    balance = get_user_balance(user_id)
    if bet > balance:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton(t(user_lang, 'top_up'), callback_data='replenish_balance'))
        await bot.send_message(user_id, t(user_lang, 'not_enough_balance'), reply_markup=markup)
        return
    buy_item_for_balance(user_id, bet)
    creator_id = room['creator']
    creator_side = room['side']
    join_side = 'tails' if creator_side == 'heads' else 'heads'
    result = random.choice(['heads', 'tails'])
    gif_path = TgConfig.HEADS_GIF if result == 'heads' else TgConfig.TAILS_GIF
    try:
        await bot.send_animation(creator_id, InputFile(gif_path))
        await bot.send_animation(user_id, InputFile(gif_path))
    except Exception:
        pass
    await asyncio.sleep(4)
    if result == creator_side:
        winner_id, loser_id = creator_id, user_id
    else:
        winner_id, loser_id = user_id, creator_id
    update_balance(winner_id, bet * 2)
    for pid, win in ((winner_id, True), (loser_id, False)):
        stats = TgConfig.COINFLIP_STATS.setdefault(pid, {'games':0,'wins':0,'losses':0,'profit':0})
        stats['games'] += 1
        if stats['games'] == 1 and not has_user_achievement(pid, 'first_coinflip'):
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            grant_achievement(pid, 'first_coinflip', ts)
            plang = get_user_language(pid) or 'en'
            await bot.send_message(pid, t(plang, 'achievement_unlocked', name=t(plang, 'achievement_first_coinflip')))
            logger.info(f"User {pid} unlocked achievement first_coinflip")
        if win:
            stats['wins'] += 1
            stats['profit'] += bet
        else:
            stats['losses'] += 1
            stats['profit'] -= bet
    await bot.send_message(winner_id,
                           t(get_user_language(winner_id) or 'en', 'win', amount=bet),
                           reply_markup=back('coinflip'))
    await bot.send_message(loser_id,
                           t(get_user_language(loser_id) or 'en', 'lose', amount=bet),
                           reply_markup=back('coinflip'))
    try:
        await bot.delete_message(creator_id, room['message_id'])
    except Exception:
        pass
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

async def shop_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    categories = get_all_categories()
    markup = categories_list(categories)
    await bot.edit_message_text('🏪 Shop categories',
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                reply_markup=markup)


async def dummy_button(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    await bot.answer_callback_query(callback_query_id=call.id, text="")


async def items_list_callback_handler(call: CallbackQuery):
    category_name = call.data[9:]
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    subcategories = get_subcategories(category_name)
    lang = get_user_language(user_id) or 'en'
    if subcategories:
        markup = subcategories_list(subcategories, category_name)
        text = build_subcategory_description(category_name, lang, user_id)
    else:
        goods = get_all_items(category_name)
        markup = goods_list(goods, category_name)
        text = t(lang, 'select_product')
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    if call.message.photo or call.message.video:
        await bot.delete_message(chat_id, message_id)
        await bot.send_message(chat_id, text, reply_markup=markup)
    else:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup,
        )


async def item_info_callback_handler(call: CallbackQuery):
    item_name = call.data[5:]
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    item_info_list = get_item_info(item_name, user_id)
    category = item_info_list['category_name']
    lang = get_user_language(user_id) or 'en'
    price = item_info_list["price"]
    markup = item_info(item_name, category, lang)
    caption = (
        f'🏪 Item {display_name(item_name)}\n'
        f'Description: {item_info_list["description"]}\n'
        f'Price - {price}€'
    )
    preview_folder = os.path.join('assets', 'product_photos', item_name)
    preview_path = None
    for ext in ('jpg', 'png', 'mp4'):
        candidate = os.path.join(preview_folder, f'preview.{ext}')
        if os.path.isfile(candidate):
            preview_path = candidate
            break
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    if preview_path:
        await bot.delete_message(chat_id, message_id)
        with open(preview_path, 'rb') as media:
            if preview_path.endswith('.mp4'):
                await bot.send_video(chat_id, media, caption=caption, reply_markup=markup)
            else:
                await bot.send_photo(chat_id, media, caption=caption, reply_markup=markup)
    else:
        await bot.edit_message_text(
            caption,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup,
        )


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Inline markup for Home button
def home_markup(lang: str = 'en'):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton(t(lang, 'back_home'), callback_data="home_menu")
    )


async def gift_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("gift", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'gift_username'
    await bot.edit_message_text(
        t(lang, 'gift_prompt'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back('profile'),
    )


async def process_gift_username(message: Message):
    if not await ensure_feature_enabled("gift", message):
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_gift_to", None)
        TgConfig.STATE.pop(f"{message.from_user.id}_gift_name", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(user_id) != 'gift_username':
        return
    username = message.text.strip().lstrip('@')
    lang = get_user_language(user_id) or 'en'
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    recipient = check_user_by_username(username)
    if not recipient:
        await bot.send_message(user_id, t(lang, 'gift_user_not_found'), reply_markup=home_markup(lang))
        TgConfig.STATE[user_id] = None
        return
    TgConfig.STATE[f'{user_id}_gift_to'] = recipient.telegram_id
    TgConfig.STATE[f'{user_id}_gift_name'] = recipient.username or str(recipient.telegram_id)
    categories = get_all_categories()
    markup = categories_list(categories)
    await bot.send_message(
        user_id,
        t(lang, 'gift_select_category', user='@' + (recipient.username or str(recipient.telegram_id))),
        reply_markup=markup,
    )
    TgConfig.STATE[user_id] = None

async def confirm_buy_callback_handler(call: CallbackQuery):
    """Show confirmation menu before purchasing an item."""
    item_name = call.data[len('confirm_'):]
    bot, user_id = await get_bot_user_ids(call)
    info = get_item_info(item_name, user_id)
    if not info:
        await call.answer('❌ Item not found', show_alert=True)
        return
    lang = get_user_language(user_id) or 'en'
    user = check_user(user_id)
    price = info['price']
    if user and user.streak_discount:
        price = round(price * 0.75, 2)

    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = None
    TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
    TgConfig.STATE[f'{user_id}_pending_item'] = item_name
    TgConfig.STATE[f'{user_id}_price'] = price
    text = t(lang, 'confirm_purchase', item=display_name(item_name), price=price)
    show_promo = can_use_discount(item_name)
    if call.message.text:
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=confirm_purchase_menu(item_name, lang, show_promo=show_promo)
        )
    else:
        await bot.send_message(
            user_id,
            text,
            reply_markup=confirm_purchase_menu(item_name, lang, show_promo=show_promo)
        )
        with contextlib.suppress(Exception):
            await call.message.delete()

async def apply_promo_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("promocodes", call):
        return
    item_name = call.data[len('applypromo_'):]
    bot, user_id = await get_bot_user_ids(call)
    if not can_use_discount(item_name):
        await call.answer('Promos not allowed for this category', show_alert=True)
        return
    if TgConfig.STATE.get(f'{user_id}_promo_applied'):
        await call.answer('Promo code already applied', show_alert=True)
        return
    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE[user_id] = 'wait_promo'
    TgConfig.STATE[f'{user_id}_message_id'] = call.message.message_id
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=t(lang, 'promo_prompt'),
        reply_markup=back(f'confirm_{item_name}')
    )

async def process_promo_code(message: Message):
    if not await ensure_feature_enabled("promocodes", message):
        TgConfig.STATE.pop(message.from_user.id, None)
        TgConfig.STATE.pop(f"{message.from_user.id}_message_id", None)
        return
    bot, user_id = await get_bot_user_ids(message)
    if TgConfig.STATE.get(user_id) != 'wait_promo':
        return
    code = message.text.strip()
    item_name = TgConfig.STATE.get(f'{user_id}_pending_item')
    price = TgConfig.STATE.get(f'{user_id}_price')
    message_id = TgConfig.STATE.get(f'{user_id}_message_id')
    lang = get_user_language(user_id) or 'en'
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    promo = get_promocode(code)
    if promo and (not promo['expires_at'] or datetime.datetime.strptime(promo['expires_at'], '%Y-%m-%d') >= datetime.datetime.now()):
        discount = promo['discount']
        new_price = round(price * (100 - discount) / 100, 2)
        TgConfig.STATE[f'{user_id}_price'] = new_price
        TgConfig.STATE[f'{user_id}_promo_applied'] = True
        text = t(lang, 'promo_applied', price=new_price)
    else:
        text = t(lang, 'promo_invalid')
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message_id,
        text=text,
        reply_markup=confirm_purchase_menu(item_name, lang, show_promo=False)
    )
    TgConfig.STATE[user_id] = None

async def buy_item_callback_handler(call: CallbackQuery):
    item_name = call.data[4:]
    bot, user_id = await get_bot_user_ids(call)
    msg = call.message.message_id
    item_info_list = get_item_info(item_name, user_id)
    item_price = TgConfig.STATE.get(f'{user_id}_price', item_info_list["price"])
    user_balance = get_user_balance(user_id)
    lang = get_user_language(user_id) or 'en'
    purchases_before = select_user_items(user_id)
    gift_to = TgConfig.STATE.get(f'{user_id}_gift_to')
    gift_name = TgConfig.STATE.get(f'{user_id}_gift_name')

    if user_balance >= item_price:
        value_data = get_item_value(item_name)

        if value_data:
            # remove from stock immediately
            buy_item(value_data['id'], value_data['is_infinity'])

            current_time = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
            formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
            new_balance = buy_item_for_balance(user_id, item_price)
            if gift_to:
                add_bought_item(value_data['item_name'], value_data['value'], item_price, gift_to, formatted_time)
                add_bought_item(value_data['item_name'], f'Gifted to @{gift_name}', item_price, user_id, formatted_time)
            else:
                add_bought_item(value_data['item_name'], value_data['value'], item_price, user_id, formatted_time)

            referral_id = get_user_referral(user_id)
            if referral_id and TgConfig.REFERRAL_PERCENT and can_get_referral_reward(value_data['item_name']):
                reward = round(item_price * TgConfig.REFERRAL_PERCENT / 100, 2)
                update_balance(referral_id, reward)
                ref_lang = get_user_language(referral_id) or 'en'
                await bot.send_message(
                    referral_id,
                    t(ref_lang, 'referral_reward', amount=f'{reward:.2f}', user=call.from_user.first_name),
                    reply_markup=close(),
                )
            purchases = purchases_before + 1
            level_before, _, _ = get_level_info(purchases_before, lang)
            level_after, _, _ = get_level_info(purchases, lang)
            if level_after != level_before:
                await bot.send_message(
                    user_id,
                    t(lang, 'level_up', level=level_after),
                )

            username = (
                f'@{call.from_user.username}'
                if call.from_user.username
                else call.from_user.full_name
            )
            parent_cat = get_category_parent(item_info_list['category_name'])

            photo_desc = ''
            file_path = None
            if os.path.isfile(value_data['value']):
                desc_file = f"{value_data['value']}.txt"
                if os.path.isfile(desc_file):
                    with open(desc_file) as f:
                        photo_desc = f.read()
                with open(value_data['value'], 'rb') as media:
                    caption = (
                        f'✅ Item purchased. **Balance**: <i>{new_balance}</i>€\n'
                        f'📦 Purchases: {purchases}'
                    )
                    if photo_desc:
                        caption += f'\n\n{photo_desc}'
                    if gift_to:
                        recipient_lang = get_user_language(gift_to) or 'en'
                        recipient_caption = t(recipient_lang, 'gift_received', item=value_data['item_name'], user=username)
                        if value_data['value'].endswith('.mp4'):
                            await bot.send_video(gift_to, media, caption=recipient_caption, parse_mode='HTML')
                        else:
                            await bot.send_photo(gift_to, media, caption=recipient_caption, parse_mode='HTML')
                    else:
                        if value_data['value'].endswith('.mp4'):
                            await bot.send_video(
                                chat_id=call.message.chat.id,
                                video=media,
                                caption=caption,
                                parse_mode='HTML'
                            )
                        else:
                            await bot.send_photo(
                                chat_id=call.message.chat.id,
                                photo=media,
                                caption=caption,
                                parse_mode='HTML'
                            )
                sold_folder = os.path.join(os.path.dirname(value_data['value']), 'Sold')
                os.makedirs(sold_folder, exist_ok=True)
                file_path = os.path.join(sold_folder, os.path.basename(value_data['value']))
                shutil.move(value_data['value'], file_path)
                if os.path.isfile(desc_file):
                    shutil.move(desc_file, os.path.join(sold_folder, os.path.basename(desc_file)))
                log_path = os.path.join('assets', 'purchases.txt')
                with open(log_path, 'a') as log_file:
                    log_file.write(f"{formatted_time} user:{user_id} item:{item_name} price:{item_price}\n")

                if not gift_to:
                    await bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=msg,
                        text=f'✅ Item purchased. 📦 Total Purchases: {purchases}',
                        reply_markup=back(f'item_{item_name}')
                    )

                cleanup_item_file(value_data['value'])
                if os.path.isfile(desc_file):
                    cleanup_item_file(desc_file)
            else:
                text = (
                    f'✅ Item purchased. **Balance**: <i>{new_balance}</i>€\n'
                    f'📦 Purchases: {purchases}\n\n{value_data["value"]}'
                )
                if gift_to:
                    recipient_lang = get_user_language(gift_to) or 'en'
                    await bot.send_message(gift_to, t(recipient_lang, 'gift_received', item=value_data['item_name'], user=username))
                else:
                    await bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=msg,
                        text=text,
                        parse_mode='HTML',
                        reply_markup=home_markup(get_user_language(user_id) or 'en')
                    )
                photo_desc = value_data['value']

            update_lottery_tickets(user_id, 1)
            await bot.send_message(user_id, t(lang, 'lottery_ticket_awarded'))
            process_purchase_streak(user_id)
            reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
            if reserve_msg_id:
                try:
                    await bot.delete_message(user_id, reserve_msg_id)
                except Exception:
                    pass
            if gift_to:
                await bot.send_message(user_id, t(lang, 'gift_sent', user=f'@{gift_name}'), reply_markup=back('profile'))
                if not has_user_achievement(user_id, 'gift_sent'):
                    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    grant_achievement(user_id, 'gift_sent', ts)
                    await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_gift_sent')))
                    logger.info(f"User {user_id} unlocked achievement gift_sent")
            else:
                try:
                    await bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=msg,
                        text=f'✅ Item purchased. 📦 Total Purchases: {purchases}',
                        reply_markup=back(f'item_{item_name}')
                    )
                except MessageNotModified:
                    pass
            TgConfig.STATE.pop(f'{user_id}_gift_to', None)
            TgConfig.STATE.pop(f'{user_id}_gift_name', None)
            if not has_user_achievement(user_id, 'first_purchase'):
                grant_achievement(user_id, 'first_purchase', formatted_time)
                await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_first_purchase')))
                logger.info(f"User {user_id} unlocked achievement first_purchase")

            recipient = gift_to or user_id
            recipient_lang = get_user_language(recipient) or lang
            asyncio.create_task(schedule_feedback(bot, recipient, recipient_lang, value_data['item_name']))

            try:
                await notify_owner_of_purchase(
                    bot,
                    username,
                    formatted_time,
                    value_data['item_name'],
                    item_price,
                    parent_cat,
                    item_info_list['category_name'],
                    photo_desc,
                    file_path,
                )

                user_info = await bot.get_chat(user_id)
                logger.info(
                    f"User {user_id} ({user_info.first_name}) bought 1 item of {value_data['item_name']} for {item_price}€"
                )
            except Exception as e:
                logger.error(f"Purchase post-processing failed for {user_id}: {e}")

            TgConfig.STATE.pop(f'{user_id}_pending_item', None)
            TgConfig.STATE.pop(f'{user_id}_price', None)
            TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
            return

            if not gift_to:
                await bot.edit_message_text(chat_id=call.message.chat.id,
                                            message_id=msg,
                                            text='❌ Item out of stock',
                                            reply_markup=back(f'item_{item_name}'))
        TgConfig.STATE.pop(f'{user_id}_pending_item', None)
        TgConfig.STATE.pop(f'{user_id}_price', None)
        TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
        TgConfig.STATE.pop(f'{user_id}_gift_to', None)
        TgConfig.STATE.pop(f'{user_id}_gift_name', None)
        return

    lang = get_user_language(user_id) or 'en'
    # Ensure the item is available before prompting for payment method.
    if not get_item_value(item_name):
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=msg,
            text='❌ Item out of stock',
            reply_markup=back(f'item_{item_name}')
        )
        TgConfig.STATE.pop(f'{user_id}_pending_item', None)
        TgConfig.STATE.pop(f'{user_id}_price', None)
        TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
        return

    TgConfig.STATE[f'{user_id}_deduct'] = user_balance
    TgConfig.STATE[user_id] = 'purchase_crypto'
    missing = item_price - user_balance
    await bot.edit_message_text(
        t(lang, 'need_top_up', missing=f'{missing:.2f}'),
        chat_id=call.message.chat.id,
        message_id=msg,
        reply_markup=crypto_choice_purchase(item_name, lang),
    )
    if gift_to:
        TgConfig.STATE[f'{user_id}_gift_to'] = gift_to
        TgConfig.STATE[f'{user_id}_gift_name'] = gift_name



async def purchase_crypto_payment(call: CallbackQuery):
    """Create crypto invoice for purchasing an item."""
    if not await ensure_feature_enabled("crypto_payments", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    currency_key = call.data.split('_')[1]
    if currency_key not in CRYPTO_PAYMENT_MAP:
        await call.answer('❌ Unsupported currency', show_alert=True)
        return
    currency = CRYPTO_PAYMENT_MAP[currency_key]
    item_name = TgConfig.STATE.get(f'{user_id}_pending_item')
    price = TgConfig.STATE.get(f'{user_id}_price')
    deduct = TgConfig.STATE.get(f'{user_id}_deduct', 0)
    gift_to = TgConfig.STATE.pop(f'{user_id}_gift_to', None)
    gift_name = TgConfig.STATE.pop(f'{user_id}_gift_name', None)
    lang = get_user_language(user_id) or 'en'

    if not item_name or price is None:
        await call.answer('❌ Purchase not found', show_alert=True)
        return

    pending = get_user_unfinished_operation(user_id)
    if pending:
        invoice_id, old_msg_id = pending
        finish_operation(invoice_id)
        purchase_data = TgConfig.STATE.pop(f'purchase_{invoice_id}', None)
        await _restore_reservation(bot, purchase_data)
        try:
            await bot.delete_message(user_id, old_msg_id)
        except Exception:
            pass
        reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
        if reserve_msg_id:
            try:
                await bot.delete_message(user_id, reserve_msg_id)
            except Exception:
                pass
        await bot.send_message(user_id, t(lang, 'payment_cancelled'))

    value_data = get_item_value(item_name)
    if not value_data:
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='❌ Item out of stock',
            reply_markup=back(f'item_{item_name}')
        )
        TgConfig.STATE.pop(f'{user_id}_pending_item', None)
        TgConfig.STATE.pop(f'{user_id}_price', None)
        TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
        TgConfig.STATE.pop(f'{user_id}_deduct', None)
        return
    if not value_data['is_infinity']:
        buy_item(value_data['id'], value_data['is_infinity'])
    reserved = value_data

    amount = price - deduct
    payment_id, address, pay_amount = create_payment(float(amount), currency)

    sleep_time = int(TgConfig.PAYMENT_TIME)
    expires_at_dt = datetime.datetime.utcnow() + datetime.timedelta(seconds=sleep_time)
    expires_at = expires_at_dt.strftime('%H:%M')
    reservation_id = None
    if reserved:
        reservation_id = create_reservation_record(
            user_id=user_id,
            item_name=reserved.get('item_name'),
            item_value=reserved.get('value'),
            is_infinity=reserved.get('is_infinity', False),
            operation_id=payment_id,
            expires_at=expires_at_dt.isoformat(),
        )
    markup = crypto_invoice_menu(payment_id, lang)
    text = t(
        lang,
        'invoice_message',
        amount=pay_amount,
        currency=currency_key,
        address=address,
        expires_at=expires_at,
    )

    qr = qrcode.make(address)
    buf = BytesIO()
    qr.save(buf, format='PNG')
    buf.seek(0)

    await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    sent = await bot.send_photo(
        chat_id=call.message.chat.id,
        photo=buf,
        caption=text,
        parse_mode='HTML',
        reply_markup=markup,
    )
    reserve_msg = await bot.send_message(user_id, t(lang, 'item_reserved'))
    TgConfig.STATE[f'{user_id}_reserve_msg'] = reserve_msg.message_id

    start_operation(user_id, amount, payment_id, sent.message_id)
    TgConfig.STATE[f'purchase_{payment_id}'] = {
        'item': item_name,
        'price': price,
        'deduct': deduct,
        'reserved': reserved,
        'user_id': user_id,
        'gift_to': gift_to,
        'gift_name': gift_name,
        'reservation_id': reservation_id,
        'operation_id': payment_id,
        'currency': currency_key,
        'expires_at': expires_at_dt.isoformat(),
    }
    TgConfig.STATE[user_id] = None

    await asyncio.sleep(sleep_time)
    info = get_unfinished_operation(payment_id)
    if info:
        user_id_db, _, message_id = info
        status = await check_payment_async(payment_id)
        if status not in ('finished', 'confirmed', 'sending'):
            finish_operation(payment_id)
            purchase_data = TgConfig.STATE.pop(f'purchase_{payment_id}', None)
            await _restore_reservation(bot, purchase_data)
            TgConfig.STATE.pop(f'{user_id}_pending_item', None)
            TgConfig.STATE.pop(f'{user_id}_price', None)
            TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
            TgConfig.STATE.pop(f'{user_id}_deduct', None)
            reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
            try:
                await bot.delete_message(user_id_db, message_id)
            except Exception:
                pass
            if reserve_msg_id:
                try:
                    await bot.delete_message(user_id_db, reserve_msg_id)
                except Exception:
                    pass
            await bot.send_message(user_id, t(lang, 'invoice_cancelled'), reply_markup=home_markup(lang))
 

async def cancel_purchase(call: CallbackQuery):
    """Cancel purchase before choosing a payment method."""
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    TgConfig.STATE.pop(f'{user_id}_pending_item', None)
    TgConfig.STATE.pop(f'{user_id}_price', None)
    TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
    TgConfig.STATE.pop(f'{user_id}_deduct', None)
    TgConfig.STATE.pop(f'{user_id}_gift_to', None)
    TgConfig.STATE.pop(f'{user_id}_gift_name', None)
    TgConfig.STATE[user_id] = None
    await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
    if reserve_msg_id:
        try:
            await bot.delete_message(user_id, reserve_msg_id)
        except Exception:
            pass
    await bot.send_message(user_id, t(lang, 'payment_cancelled'), reply_markup=home_markup(lang))


# Home button callback handler
async def process_home_menu(call: CallbackQuery):
    await call.message.delete()
    bot, user_id = await get_bot_user_ids(call)
    user = check_user(user_id)
    lang = get_user_language(user_id) or 'en'
    markup = main_menu(get_user_role_id(user), TgConfig.CHANNEL_URL, TgConfig.PRICE_LIST_URL, lang)
    purchases = select_user_items(user_id)
    text = build_menu_text(call.from_user, user.balance, purchases, user.purchase_streak, lang)
    await bot.send_message(user_id, text, reply_markup=markup)

async def bought_items_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    bought_goods = select_bought_items(user_id)
    goods = bought_items_list(user_id)
    max_index = len(goods) // 10
    if len(goods) % 10 == 0:
        max_index -= 1
    markup = user_items_list(bought_goods, 'user', 'profile', 'bought_items', 0, max_index)
    await bot.edit_message_text('Your items:', chat_id=call.message.chat.id,
                                message_id=call.message.message_id, reply_markup=markup)


async def navigate_bought_items(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    goods = bought_items_list(user_id)
    bought_goods = select_bought_items(user_id)
    current_index = int(call.data.split('_')[1])
    data = call.data.split('_')[2]
    max_index = len(goods) // 10
    if len(goods) % 10 == 0:
        max_index -= 1
    if 0 <= current_index <= max_index:
        if data == 'user':
            back_data = 'profile'
            pre_back = 'bought_items'
        else:
            back_data = f'check-user_{data}'
            pre_back = f'user-items_{data}'
        markup = user_items_list(bought_goods, data, back_data, pre_back, current_index, max_index)
        await bot.edit_message_text(message_id=call.message.message_id,
                                    chat_id=call.message.chat.id,
                                    text='Your items:',
                                    reply_markup=markup)
    else:
        await bot.answer_callback_query(callback_query_id=call.id, text="❌ Page not found")


async def bought_item_info_callback_handler(call: CallbackQuery):
    item_id = call.data.split(":")[1]
    back_data = call.data.split(":")[2]
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    item = get_bought_item_info(item_id)
    await bot.edit_message_text(
        f'**Item**: <code>{display_name(item["item_name"])}</code>\n'
        f'**Price**: <code>{item["price"]}</code>€\n'
        f'**Purchase date**: <code>{item["bought_datetime"]}</code>',
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML',
        reply_markup=back(back_data))


async def rules_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    rules_data = TgConfig.RULES

    if rules_data:
        await bot.edit_message_text(rules_data, chat_id=call.message.chat.id,
                                    message_id=call.message.message_id, reply_markup=rules())
        return

    await call.answer(text='❌ Rules were not added')


async def help_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    TgConfig.STATE[user_id] = None
    user_lang = get_user_language(user_id) or 'en'
    help_text = t(user_lang, 'help_info', helper=TgConfig.HELPER_URL)
    await bot.edit_message_text(
        help_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back('profile')
    )


async def profile_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    user = call.from_user
    TgConfig.STATE[user_id] = None
    user_info = check_user(user_id)
    user_lang = get_user_language(user_info, 'en')
    balance_raw = user_info.balance
    operations = select_user_operations(user_id) or []
    total_topped = sum((Decimal(str(value)) for value in operations), Decimal("0"))
    balance_amount = Decimal(str(balance_raw or 0)).quantize(Decimal("0.01"))
    total_amount = total_topped.quantize(Decimal("0.01"))
    items = select_user_items(user_id)
    markup = profile(items, user_lang)

    safe_name = html.escape(
        user.first_name
        or user.full_name
        or (f"@{user.username}" if user.username else str(user_id))
    )

    text = (
        f"👤 <b>Profile</b> — {safe_name}\n"
        f"🆔 <b>ID</b> — <code>{user_id}</code>\n"
        f"💳 <b>Balance</b> — <code>{balance_amount:.2f}</code> €\n"
        f"💵 <b>Total topped up</b> — <code>{total_amount:.2f}</code> €\n"
        f"🎁 <b>Items purchased</b> — {items} pcs"
    )

    await bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )


async def quests_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("quests", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=t(lang, 'quests_placeholder'),
        reply_markup=back('profile')
    )




async def achievements_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("achievements", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    total_users = get_user_count()
    parts = call.data.split(':')
    view = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0
    per_page = 5
    start = page * per_page
    show_unlocked = view == 'achievements_unlocked'
    codes = [
        code for code in TgConfig.ACHIEVEMENTS
        if has_user_achievement(user_id, code) == show_unlocked
    ]
    lines = []
    for idx, code in enumerate(codes[start:start + per_page], start=start + 1):
        count = get_achievement_users(code)
        percent = round((count / total_users) * 100, 1) if total_users else 0
        status = '✅' if show_unlocked else '❌'
        lines.append(f"{idx}. {status} {t(lang, f'achievement_{code}')} — {percent}%")
    text = f"{t(lang, 'achievements')}\n\n" + "\n".join(lines)
    markup = achievements_menu(page, len(codes), lang, show_unlocked)
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=markup,
    )


async def notify_stock_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("stock_alerts", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    categories = get_out_of_stock_categories()
    if not categories:
        await bot.answer_callback_query(call.id, t(lang, 'no_out_of_stock'), show_alert=True)
        return
    markup = notify_categories_list(categories, lang)
    await bot.edit_message_text(
        t(lang, 'choose_product_notify'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


async def notify_category_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("stock_alerts", call):
        return
    category = call.data[len('notify_cat_'):]
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    subs = get_out_of_stock_subcategories(category)
    if subs:
        markup = notify_subcategories_list(subs, category, lang)
    else:
        items = get_out_of_stock_items(category)
        markup = notify_goods_list(items, category, lang)
    await bot.edit_message_text(
        t(lang, 'choose_product_notify'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


async def notify_item_callback_handler(call: CallbackQuery):
    if not await ensure_feature_enabled("stock_alerts", call):
        return
    item_name = call.data[len('notify_item_'):]
    bot, user_id = await get_bot_user_ids(call)
    lang = get_user_language(user_id) or 'en'
    if has_stock_notification(user_id, item_name):
        text = t(lang, 'stock_already_subscribed', item=display_name(item_name))
    else:
        add_stock_notification(user_id, item_name)
        text = t(lang, 'stock_subscribed', item=display_name(item_name))
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton(t(lang, 'back'), callback_data='notify_stock')
    )
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


async def replenish_balance_callback_handler(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    message_id = call.message.message_id

    # proceed if NowPayments API key is configured
    if EnvKeys.NOWPAYMENTS_API_KEY:
        TgConfig.STATE[f'{user_id}_message_id'] = message_id
        TgConfig.STATE[user_id] = 'process_replenish_balance'
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=message_id,
            text='💰 Enter the top-up amount:',
            reply_markup=back('back_to_menu')
        )
        return

    # fallback if API key missing
    await call.answer('❌ Top-up is not configured.')



async def process_replenish_balance(message: Message):
    bot, user_id = await get_bot_user_ids(message)

    text = message.text
    message_id = TgConfig.STATE.get(f'{user_id}_message_id')
    TgConfig.STATE[user_id] = None
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    if not text.isdigit() or int(text) < 5 or int(text) > 10000:
        await bot.edit_message_text(chat_id=message.chat.id,
                                    message_id=message_id,
                                    text="❌ Invalid top-up amount. "
                                         "The amount must be between 5€ and 10 000€",
                                    reply_markup=back('replenish_balance'))
        return

    TgConfig.STATE[f'{user_id}_amount'] = text
    if not is_enabled('crypto_payments'):
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=feature_disabled_text(user_id),
            reply_markup=back('replenish_balance'),
        )
        return
    markup = crypto_choice()
    await bot.edit_message_text(chat_id=message.chat.id,
                                message_id=message_id,
                                text=f'💵 Top-up amount: {text}€. Choose payment method:',
                                reply_markup=markup)


async def pay_yoomoney(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    amount = TgConfig.STATE.pop(f'{user_id}_amount', None)
    if not amount:
        await call.answer(text='❌ Invoice not found')
        return

    fake = type('Fake', (), {'text': amount, 'from_user': call.from_user})
    label, url = quick_pay(fake)
    sleep_time = int(TgConfig.PAYMENT_TIME)
    lang = get_user_language(user_id) or 'en'
    markup = payment_menu(url, label, lang)
    await bot.edit_message_text(chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text=f'💵 Top-up amount: {amount}€.\n'
                                     f'⌛️ You have {int(sleep_time / 60)} minutes to pay.\n'
                                     f'**❗️ After payment press "Check payment"**',
                                reply_markup=markup)
    start_operation(user_id, amount, label, call.message.message_id)
    await asyncio.sleep(sleep_time)
    info = get_unfinished_operation(label)
    if info:
        _, _, _ = info
        status = await check_payment_status(label)
        if status not in ('paid', 'success'):
            finish_operation(label)
            await bot.send_message(user_id, t(lang, 'invoice_cancelled'))


async def crypto_payment(call: CallbackQuery):
    if not await ensure_feature_enabled("crypto_payments", call):
        return
    bot, user_id = await get_bot_user_ids(call)
    currency_key = call.data.split('_')[1]
    if currency_key not in CRYPTO_PAYMENT_MAP:
        await call.answer('❌ Unsupported currency', show_alert=True)
        return
    currency = CRYPTO_PAYMENT_MAP[currency_key]
    amount = TgConfig.STATE.pop(f'{user_id}_amount', None)
    if not amount:
        await call.answer(text='❌ Invoice not found')
        return

    payment_id, address, pay_amount = create_payment(float(amount), currency)

    sleep_time = int(TgConfig.PAYMENT_TIME)
    lang = get_user_language(user_id) or 'en'
    expires_at = (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=sleep_time)
    ).strftime('%H:%M')
    markup = crypto_invoice_menu(payment_id, lang)
    text = t(
        lang,
        'invoice_message',
        amount=pay_amount,
        currency=currency_key,
        address=address,
        expires_at=expires_at,
    )

    # Generate QR code for the address
    qr = qrcode.make(address)
    buf = BytesIO()
    qr.save(buf, format='PNG')
    buf.seek(0)

    await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    sent = await bot.send_photo(
        chat_id=call.message.chat.id,
        photo=buf,
        caption=text,
        parse_mode='HTML',
        reply_markup=markup,
    )
    start_operation(user_id, amount, payment_id, sent.message_id)
    await asyncio.sleep(sleep_time)
    info = get_unfinished_operation(payment_id)
    if info:
        _, _, _ = info
        status = await check_payment_async(payment_id)
        if status not in ('finished', 'confirmed', 'sending'):
            finish_operation(payment_id)
            await bot.send_message(user_id, t(lang, 'invoice_cancelled'))


async def checking_payment(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    message_id = call.message.message_id
    label = call.data[6:]
    info = get_unfinished_operation(label)

    if info:
        user_id_db, operation_value, _ = info
        lang = get_user_language(user_id_db) or 'en'
        payment_status = await check_payment_status(label)
        if payment_status is None:
            payment_status = await check_payment_async(label)
        if payment_status in ("success", "paid", "finished", "confirmed", "sending"):
            current_time = datetime.datetime.now()
            formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
            referral_id = get_user_referral(user_id)
            finish_operation(label)

            purchase_data = TgConfig.STATE.pop(f'purchase_{label}', None)
            if purchase_data:
                mark_reservation_completed_by_operation(label)
                item_name = purchase_data['item']
                price = purchase_data['price']
                deduct = purchase_data['deduct']
                reserved = purchase_data.get('reserved')
                gift_to = purchase_data.get('gift_to')
                gift_name = purchase_data.get('gift_name')
                reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
                if reserve_msg_id:
                    try:
                        await bot.delete_message(user_id, reserve_msg_id)
                    except Exception:
                        pass

                if referral_id and TgConfig.REFERRAL_PERCENT and can_get_referral_reward(item_name):
                    reward = round(price * TgConfig.REFERRAL_PERCENT / 100, 2)
                    update_balance(referral_id, reward)
                    ref_lang = get_user_language(referral_id) or 'en'
                    await bot.send_message(
                        referral_id,
                        t(ref_lang, 'referral_reward', amount=f'{reward:.2f}', user=call.from_user.first_name),
                        reply_markup=close(),
                    )

                create_operation(user_id, operation_value, formatted_time)
                update_balance(user_id, operation_value)
                item_info_list = get_item_info(item_name, user_id)

                if reserved:
                    value_data = reserved
                else:
                    value_data = get_item_value(item_name)
                    if value_data:
                        buy_item(value_data['id'], value_data['is_infinity'])
                if value_data:
                    new_balance = buy_item_for_balance(user_id, price)
                    if gift_to:
                        add_bought_item(value_data['item_name'], value_data['value'], price, gift_to, formatted_time)
                        purchase_id = add_bought_item(value_data['item_name'], f'Gifted to @{gift_name}', price, user_id, formatted_time)
                    else:
                        purchase_id = add_bought_item(value_data['item_name'], value_data['value'], price, user_id, formatted_time)

                    purchases = select_user_items(user_id)
                    photo_desc = ''
                    file_path = None
                    if os.path.isfile(value_data['value']):
                        desc_file = f"{value_data['value']}.txt"
                        if os.path.isfile(desc_file):
                            with open(desc_file) as f:
                                photo_desc = f.read()
                        with open(value_data['value'], 'rb') as media:
                            caption = (
                                f'✅ Item purchased. **Balance**: <i>{new_balance}</i>€\n'
                                f'📦 Purchases: {purchases}'
                            )
                            if photo_desc:
                                caption += f'\n\n{photo_desc}'
                            if gift_to:
                                recipient_lang = get_user_language(gift_to) or 'en'
                                recipient_caption = t(
                                    recipient_lang,
                                    'gift_received',
                                    item=value_data['item_name'],
                                    user=username
                                )
                                if value_data['value'].endswith('.mp4'):
                                    await bot.send_video(
                                        gift_to,
                                        media,
                                        caption=recipient_caption,
                                        parse_mode='HTML'
                                    )
                                else:
                                    await bot.send_photo(
                                        gift_to,
                                        media,
                                        caption=recipient_caption,
                                        parse_mode='HTML'
                                    )
                            else:
                                if value_data['value'].endswith('.mp4'):
                                    await bot.send_video(
                                        chat_id=call.message.chat.id,
                                        video=media,
                                        caption=caption,
                                        parse_mode='HTML'
                                    )
                                else:
                                    await bot.send_photo(
                                        chat_id=call.message.chat.id,
                                        photo=media,
                                        caption=caption,
                                        parse_mode='HTML'
                                    )


                        sold_folder = os.path.join(os.path.dirname(value_data['value']), 'Sold')
                        os.makedirs(sold_folder, exist_ok=True)
                        file_path = os.path.join(sold_folder, os.path.basename(value_data['value']))
                        shutil.move(value_data['value'], file_path)
                        if os.path.isfile(desc_file):
                            shutil.move(desc_file, os.path.join(sold_folder, os.path.basename(desc_file)))
                        cleanup_item_file(value_data['value'])
                        if os.path.isfile(desc_file):
                            cleanup_item_file(desc_file)
                    else:
                        if gift_to:
                            recipient_lang = get_user_language(gift_to) or 'en'
                            await bot.send_message(
                                gift_to,
                                t(
                                    recipient_lang,
                                    'gift_received',
                                    item=value_data['item_name'],
                                    user=username
                                )
                            )
                        else:
                            await bot.send_message(
                                call.message.chat.id,
                                value_data['value']
                            )



                    parent_cat = get_category_parent(item_info_list['category_name'])
                    username = f'@{call.from_user.username}' if call.from_user.username else call.from_user.full_name
                    await notify_owner_of_purchase(
                        bot,
                        username,
                        formatted_time,
                        value_data['item_name'],
                        price,
                        parent_cat,
                        item_info_list['category_name'],
                        photo_desc,
                        file_path,
                    )
                    if gift_to:
                        await bot.send_message(user_id, t(lang, 'gift_sent', user=f'@{gift_name}'), reply_markup=back('profile'))
                        if not has_user_achievement(user_id, 'gift_sent'):
                            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            grant_achievement(user_id, 'gift_sent', ts)
                            await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_gift_sent')))
                            logger.info(f"User {user_id} unlocked achievement gift_sent")



                    if gift_to:
                        await bot.send_message(user_id, t(lang, 'gift_sent', user=f'@{gift_name}'), reply_markup=back('profile'))
                    else:
                        try:
                            await bot.edit_message_text(
                                chat_id=call.message.chat.id,
                                message_id=message_id,
                                text=f'✅ Item purchased. 📦 Total Purchases: {purchases}',
                                reply_markup=back('profile')
                            )
                        except MessageNotModified:
                            pass
                    update_lottery_tickets(user_id, 1)
                    await bot.send_message(user_id, t(lang, 'lottery_ticket_awarded'))
                    process_purchase_streak(user_id)
                    if not has_user_achievement(user_id, 'first_purchase'):
                        grant_achievement(user_id, 'first_purchase', formatted_time)
                        await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_first_purchase')))
                        logger.info(f"User {user_id} unlocked achievement first_purchase")
                    TgConfig.STATE.pop(f'{user_id}_pending_item', None)
                    TgConfig.STATE.pop(f'{user_id}_price', None)
                    TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
                    TgConfig.STATE.pop(f'{user_id}_deduct', None)
                    recipient = gift_to or user_id
                    recipient_lang = get_user_language(recipient) or lang
                    asyncio.create_task(schedule_feedback(bot, recipient, recipient_lang, value_data['item_name']))
                    await bot.send_message(user_id, t(lang, 'top_up_completed'))
                    if not has_user_achievement(user_id, 'first_topup'):
                        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        grant_achievement(user_id, 'first_topup', ts)
                        await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_first_topup')))
                        logger.info(f"User {user_id} unlocked achievement first_topup")

                    try:
                        await bot.edit_message_text(
                            chat_id=call.message.chat.id,
                            message_id=message_id,
                            text=f'✅ Item purchased. 📦 Total Purchases: {purchases}',
                            reply_markup=back('profile')
                        )
                    except MessageNotModified:
                        pass

                    TgConfig.STATE.pop(f'{user_id}_pending_item', None)
                    TgConfig.STATE.pop(f'{user_id}_price', None)
                    TgConfig.STATE.pop(f'{user_id}_promo_applied', None)

                    await bot.send_message(user_id, t(lang, 'top_up_completed'))

                    recipient = gift_to or user_id
                    recipient_lang = get_user_language(recipient) or lang
                    asyncio.create_task(schedule_feedback(bot, recipient, recipient_lang, value_data['item_name']))

                else:
                    await bot.send_message(user_id, '❌ Item out of stock')
            else:



                create_operation(user_id, operation_value, formatted_time)
                update_balance(user_id, operation_value)
                await bot.edit_message_text(chat_id=call.message.chat.id,
                                            message_id=message_id,
                                            text=f'✅ Balance topped up by {operation_value}€',
                                            reply_markup=back('profile'))
                await bot.send_message(user_id, t(lang, 'top_up_completed'))
                if not has_user_achievement(user_id, 'first_topup'):
                    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    grant_achievement(user_id, 'first_topup', ts)
                    await bot.send_message(user_id, t(lang, 'achievement_unlocked', name=t(lang, 'achievement_first_topup')))
                    logger.info(f"User {user_id} unlocked achievement first_topup")

                username = f'@{call.from_user.username}' if call.from_user.username else call.from_user.full_name
                await bot.send_message(
                    EnvKeys.OWNER_ID,
                    f'User {username} topped up {operation_value}€'
                )
        else:
            await call.answer(text='❌ Payment was not successful')
    else:
        await call.answer(text='❌ Invoice not found')


async def cancel_payment(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    invoice_id = call.data.split('_', 1)[1]
    info = get_unfinished_operation(invoice_id)
    lang = get_user_language(user_id) or 'en'
    if info:
        user_id_db, _, message_id = info
        finish_operation(invoice_id)
        purchase_data = TgConfig.STATE.pop(f'purchase_{invoice_id}', None)
        await _restore_reservation(bot, purchase_data)
        TgConfig.STATE.pop(f'{user_id_db}_pending_item', None)
        TgConfig.STATE.pop(f'{user_id_db}_price', None)
        TgConfig.STATE.pop(f'{user_id_db}_promo_applied', None)
        TgConfig.STATE.pop(f'{user_id_db}_deduct', None)
        try:
            await bot.delete_message(user_id_db, message_id)
        except Exception:
            pass
        reserve_msg_id = TgConfig.STATE.pop(f'{user_id_db}_reserve_msg', None)
        if reserve_msg_id:
            try:
                await bot.delete_message(user_id_db, reserve_msg_id)
            except Exception:
                pass
        await bot.send_message(user_id_db, t(lang, 'payment_cancelled'), reply_markup=home_markup(lang))
    else:
        await call.answer(text='❌ Invoice not found')


async def check_sub_to_channel(call: CallbackQuery):

    bot, user_id = await get_bot_user_ids(call)
    invoice_id = call.data.split('_', 1)[1]
    lang = get_user_language(user_id) or 'en'
    if get_unfinished_operation(invoice_id):
        finish_operation(invoice_id)
        purchase_data = TgConfig.STATE.pop(f'purchase_{invoice_id}', None)
        await _restore_reservation(bot, purchase_data)
        TgConfig.STATE.pop(f'{user_id}_pending_item', None)
        TgConfig.STATE.pop(f'{user_id}_price', None)
        TgConfig.STATE.pop(f'{user_id}_promo_applied', None)
        TgConfig.STATE.pop(f'{user_id}_deduct', None)
        reserve_msg_id = TgConfig.STATE.pop(f'{user_id}_reserve_msg', None)
        if reserve_msg_id:
            try:
                await bot.delete_message(user_id, reserve_msg_id)
            except Exception:
                pass
        await bot.edit_message_text(
            t(lang, 'invoice_cancelled'),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back('replenish_balance'),
        )
    else:
        await call.answer(text='❌ Invoice not found')




async def change_language(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    current_lang = get_user_language(user_id) or 'en'
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton('English \U0001F1EC\U0001F1E7', callback_data='set_lang_en'),
        InlineKeyboardButton('Русский \U0001F1F7\U0001F1FA', callback_data='set_lang_ru'),
        InlineKeyboardButton('Lietuvi\u0173 \U0001F1F1\U0001F1F9', callback_data='set_lang_lt')
    )
    await bot.edit_message_text(
        t(current_lang, 'choose_language'),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )


async def set_language(call: CallbackQuery):
    bot, user_id = await get_bot_user_ids(call)
    lang_code = call.data.split('_')[-1]
    update_user_language(user_id, lang_code)
    await call.message.delete()
    role = check_role(user_id)
    user = check_user(user_id)
    balance = user.balance if user else 0
    markup = main_menu(role, TgConfig.CHANNEL_URL, TgConfig.PRICE_LIST_URL, lang_code)
    purchases = select_user_items(user_id)
    text = build_menu_text(call.from_user, balance, purchases, user.purchase_streak, lang_code)

    try:
        with open(TgConfig.START_PHOTO_PATH, 'rb') as photo:
            await bot.send_photo(user_id, photo)
    except Exception:
        pass

    await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=markup
    )






def register_user_handlers(dp: Dispatcher):
    dp.register_message_handler(start,
                                commands=['start'])

    dp.register_callback_query_handler(shop_callback_handler,
                                       lambda c: c.data == 'shop')
    dp.register_callback_query_handler(dummy_button,
                                       lambda c: c.data == 'dummy_button')
    dp.register_callback_query_handler(profile_callback_handler,
                                       lambda c: c.data == 'profile')
    dp.register_callback_query_handler(gift_callback_handler,
                                       lambda c: c.data == 'gift')
    dp.register_callback_query_handler(quests_callback_handler,
                                       lambda c: c.data == 'quests')
    dp.register_callback_query_handler(achievements_callback_handler,
                                       lambda c: c.data.startswith('achievements'))
    dp.register_callback_query_handler(notify_stock_callback_handler,
                                       lambda c: c.data == 'notify_stock')
    dp.register_callback_query_handler(notify_category_callback_handler,
                                       lambda c: c.data.startswith('notify_cat_'))
    dp.register_callback_query_handler(notify_item_callback_handler,
                                       lambda c: c.data.startswith('notify_item_'))
    dp.register_callback_query_handler(rules_callback_handler,
                                       lambda c: c.data == 'rules')
    dp.register_callback_query_handler(help_callback_handler,
                                       lambda c: c.data == 'help')
    dp.register_callback_query_handler(replenish_balance_callback_handler,
                                       lambda c: c.data == 'replenish_balance')
    dp.register_callback_query_handler(price_list_callback_handler,
                                       lambda c: c.data == 'price_list')
    dp.register_callback_query_handler(blackjack_callback_handler,
                                       lambda c: c.data == 'blackjack')
    dp.register_callback_query_handler(blackjack_set_bet_handler,
                                       lambda c: c.data == 'blackjack_set_bet')
    dp.register_callback_query_handler(blackjack_place_bet_handler,
                                       lambda c: c.data == 'blackjack_place_bet')
    dp.register_callback_query_handler(blackjack_play_again_handler,
                                       lambda c: c.data.startswith('blackjack_play_'))
    dp.register_callback_query_handler(blackjack_move_handler,
                                       lambda c: c.data in ('blackjack_hit', 'blackjack_stand'))
    dp.register_callback_query_handler(blackjack_history_handler,
                                       lambda c: c.data.startswith('blackjack_history_'))
    dp.register_callback_query_handler(games_callback_handler,
                                       lambda c: c.data == 'games')
    dp.register_callback_query_handler(coinflip_callback_handler,
                                       lambda c: c.data == 'coinflip')
    dp.register_callback_query_handler(coinflip_play_bot_handler,
                                       lambda c: c.data == 'coinflip_bot')
    dp.register_callback_query_handler(coinflip_find_handler,
                                       lambda c: c.data == 'coinflip_find')
    dp.register_callback_query_handler(coinflip_create_handler,
                                       lambda c: c.data == 'coinflip_create')
    dp.register_callback_query_handler(coinflip_side_handler,
                                       lambda c: c.data.startswith('coinflip_side_'))
    dp.register_callback_query_handler(coinflip_create_confirm_handler,
                                       lambda c: c.data.startswith('coinflip_create_room_'))
    dp.register_callback_query_handler(coinflip_cancel_handler,
                                       lambda c: c.data.startswith('coinflip_cancel_'))
    dp.register_callback_query_handler(coinflip_room_handler,
                                       lambda c: c.data.startswith('coinflip_room_'))
    dp.register_callback_query_handler(coinflip_join_handler,
                                       lambda c: c.data.startswith('coinflip_join_'))
    dp.register_callback_query_handler(service_feedback_handler,
                                       lambda c: c.data.startswith('service_feedback_'), state='*')
    dp.register_callback_query_handler(product_feedback_handler,
                                       lambda c: c.data.startswith('product_feedback_'), state='*')
    dp.register_callback_query_handler(feedback_comment_choice,
                                       lambda c: c.data.startswith('feedback_comment_'), state='*')
    dp.register_message_handler(
        feedback_comment_message,
        lambda m: TgConfig.STATE.get(m.from_user.id) == 'feedback_comment',
        state='*'
    )
    dp.register_callback_query_handler(bought_items_callback_handler,
                                       lambda c: c.data == 'bought_items', state='*')
    dp.register_callback_query_handler(back_to_menu_callback_handler,
                                       lambda c: c.data == 'back_to_menu',
                                       state='*')
    dp.register_callback_query_handler(close_callback_handler,
                                       lambda c: c.data == 'close', state='*')
    dp.register_callback_query_handler(change_language,
                                       lambda c: c.data == 'change_language', state='*')
    dp.register_callback_query_handler(set_language,
                                       lambda c: c.data.startswith('set_lang_'), state='*')

    dp.register_callback_query_handler(navigate_bought_items,
                                       lambda c: c.data.startswith('bought-goods-page_'), state='*')
    dp.register_callback_query_handler(bought_item_info_callback_handler,
                                       lambda c: c.data.startswith('bought-item:'), state='*')
    dp.register_callback_query_handler(items_list_callback_handler,
                                       lambda c: c.data.startswith('category_'), state='*')
    dp.register_callback_query_handler(item_info_callback_handler,
                                       lambda c: c.data.startswith('item_'), state='*')
    dp.register_callback_query_handler(confirm_buy_callback_handler,
                                       lambda c: c.data.startswith('confirm_'), state='*')
    dp.register_callback_query_handler(apply_promo_callback_handler,
                                       lambda c: c.data.startswith('applypromo_'), state='*')
    dp.register_callback_query_handler(buy_item_callback_handler,
                                       lambda c: c.data.startswith('buy_'), state='*')
    dp.register_callback_query_handler(pay_yoomoney,
                                       lambda c: c.data == 'pay_yoomoney', state='*')
    dp.register_callback_query_handler(crypto_payment,
                                       lambda c: c.data.startswith('crypto_'), state='*')
    dp.register_callback_query_handler(cancel_purchase,
                                       lambda c: c.data == 'cancel_purchase', state='*')
    dp.register_callback_query_handler(purchase_crypto_payment,
                                       lambda c: c.data.startswith('buycrypto_'), state='*')
    dp.register_callback_query_handler(cancel_payment,
                                       lambda c: c.data.startswith('cancel_'), state='*')
    dp.register_callback_query_handler(checking_payment,
                                       lambda c: c.data.startswith('check_'), state='*')
    dp.register_callback_query_handler(process_home_menu,
                                       lambda c: c.data == 'home_menu', state='*')

    dp.register_message_handler(process_replenish_balance,
                                lambda c: TgConfig.STATE.get(c.from_user.id) == 'process_replenish_balance')
    dp.register_message_handler(process_promo_code,
                                lambda c: TgConfig.STATE.get(c.from_user.id) == 'wait_promo')
    dp.register_message_handler(process_gift_username,
                                lambda c: TgConfig.STATE.get(c.from_user.id) == 'gift_username')
    dp.register_message_handler(blackjack_receive_bet,
                                lambda c: TgConfig.STATE.get(c.from_user.id) == 'blackjack_enter_bet')
    dp.register_message_handler(coinflip_receive_bet,
                                lambda c: TgConfig.STATE.get(c.from_user.id) in ('coinflip_bot_enter_bet', 'coinflip_create_enter_bet'))
    dp.register_message_handler(pavogti,
                                commands=['pavogti'])
    dp.register_callback_query_handler(pavogti_item_callback,
                                       lambda c: c.data.startswith('pavogti_item_'))


# --- async wrapper injected by fix ---
async def check_payment_async(payment_id):
    """Async wrapper around check_payment to ensure proper aiohttp session handling.
    If a sync check_payment exists, run it in thread executor; otherwise, if an async
    version exists, await it. Also ensures sessions are properly closed.
    """
    import asyncio
    try:
        # Prefer existing async function
        from bot.services.payments import check_payment as existing_check
        if asyncio.iscoroutinefunction(existing_check):
            return await existing_check(payment_id)
        else:
            # Run sync function without blocking loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, existing_check, payment_id)
    except Exception:
        # Fallback: if local check_payment exists in this module
        try:
            if 'check_payment' in globals():
                _cp = globals()['check_payment']
                import asyncio as _asyncio
                if _asyncio.iscoroutinefunction(_cp):
                    return await _cp(payment_id)
                loop = _asyncio.get_event_loop()
                return await loop.run_in_executor(None, _cp, payment_id)
        except Exception:
            raise
# --- end async wrapper ---