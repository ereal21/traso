from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.models import Permission

from bot.localization import t
from bot.database.methods import get_category_parent, select_item_values_amount
from bot.utils import display_name





def main_menu(role: int, channel: str = None, price: str = None, lang: str = 'en') -> InlineKeyboardMarkup:
    """Return main menu with layout:
       1) Shop
       2) Profile | Top Up
       3) Channel | Price List (only those that exist)
       4) Language
       (+ Admin panel if role > 1)
    """
    inline_keyboard = []

    # Row 1: Shop (single wide)
    inline_keyboard.append(
        [InlineKeyboardButton(t(lang, 'shop'), callback_data='shop')]
    )

    # Row 2: Profile | Top Up
    inline_keyboard.append([
        InlineKeyboardButton(t(lang, 'profile'), callback_data='profile'),
        InlineKeyboardButton(t(lang, 'top_up'), callback_data='replenish_balance'),
    ])

    # Row 3: Channel | Price List (conditionally add one or both)
    row3 = []
    if channel:
        row3.append(InlineKeyboardButton(t(lang, 'channel'), url=channel))
    if price:
        row3.append(InlineKeyboardButton(t(lang, 'price_list'), callback_data='price_list'))
    if row3:
        inline_keyboard.append(row3)

    # Row 4: Language (single wide)
    inline_keyboard.append(
        [InlineKeyboardButton(t(lang, 'language'), callback_data='change_language')]
    )

    # Optional: Admin panel
    if role > 1:
        inline_keyboard.append(
            [InlineKeyboardButton(t(lang, 'admin_panel'), callback_data='console')]
        )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def categories_list(list_items: list[str]) -> InlineKeyboardMarkup:
    """Show all categories without pagination."""
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=name, callback_data=f'category_{name}'))
    markup.add(InlineKeyboardButton('🔙 Back to menu', callback_data='back_to_menu'))
    return markup


def goods_list(list_items: list[str], category_name: str) -> InlineKeyboardMarkup:
    """Show all goods for a category without pagination."""
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=display_name(name), callback_data=f'item_{name}'))
    markup.add(InlineKeyboardButton('🔙 Go back', callback_data='shop'))
    return markup


def subcategories_list(list_items: list[str], parent: str) -> InlineKeyboardMarkup:
    """Show all subcategories without pagination."""
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=name, callback_data=f'category_{name}'))
    back_parent = get_category_parent(parent)
    back_data = 'shop' if back_parent is None else f'category_{back_parent}'
    markup.add(InlineKeyboardButton('🔙 Go back', callback_data=back_data))
    return markup


def notify_categories_list(list_items: list[str], lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=name, callback_data=f'notify_cat_{name}'))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='profile'))
    return markup


def notify_subcategories_list(list_items: list[str], parent: str, lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=name, callback_data=f'notify_cat_{name}'))
    back_parent = get_category_parent(parent)
    back_data = 'notify_stock' if back_parent is None else f'notify_cat_{back_parent}'
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data=back_data))
    return markup


def notify_goods_list(list_items: list[str], category_name: str, lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=display_name(name), callback_data=f'notify_item_{name}'))
    back_parent = get_category_parent(category_name)
    back_data = 'notify_stock' if back_parent is None else f'notify_cat_{back_parent}'
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data=back_data))
    return markup


def user_items_list(list_items: list, data: str, back_data: str, pre_back: str, current_index: int, max_index: int)\
        -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    page_items = list_items[current_index * 10: (current_index + 1) * 10]
    for item in page_items:
        markup.add(InlineKeyboardButton(text=display_name(item.item_name), callback_data=f'bought-item:{item.id}:{pre_back}'))
    if max_index > 0:
        buttons = [
            InlineKeyboardButton(text='◀️', callback_data=f'bought-goods-page_{current_index - 1}_{data}'),
            InlineKeyboardButton(text=f'{current_index + 1}/{max_index + 1}', callback_data='dummy_button'),
            InlineKeyboardButton(text='▶️', callback_data=f'bought-goods-page_{current_index + 1}_{data}')
        ]
        markup.row(*buttons)
    markup.add(InlineKeyboardButton('🔙 Go back', callback_data=back_data))
    return markup


def item_info(item_name: str, category_name: str, lang: str) -> InlineKeyboardMarkup:
    """Return inline keyboard for a single item without basket option."""
    inline_keyboard = [
        [InlineKeyboardButton('💰 Buy', callback_data=f'confirm_{item_name}')],
        [InlineKeyboardButton('🔙 Go back', callback_data=f'category_{category_name}')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def profile(user_items: int = 0, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'games'), callback_data='games')],
        [InlineKeyboardButton(t(lang, 'achievements'), callback_data='achievements')],
        [InlineKeyboardButton(t(lang, 'quests'), callback_data='quests')],
        [InlineKeyboardButton(t(lang, 'gift'), callback_data='gift')],
        [InlineKeyboardButton(t(lang, 'stock_notify'), callback_data='notify_stock')],
    ]
    if user_items != 0:
        inline_keyboard.append([
            InlineKeyboardButton(t(lang, 'purchased_items'), callback_data='bought_items')
        ])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'help'), callback_data='help')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back_to_menu'), callback_data='back_to_menu')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def games_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'blackjack'), callback_data='blackjack')],
        [InlineKeyboardButton(t(lang, 'coinflip'), callback_data='coinflip')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='profile')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def achievements_menu(page: int, total: int, lang: str = 'en', unlocked: bool = False) -> InlineKeyboardMarkup:
    prefix = 'achievements_unlocked' if unlocked else 'achievements'
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('⬅️', callback_data=f'{prefix}:{page-1}'))
    if (page + 1) * 5 < total:
        nav.append(InlineKeyboardButton('➡️', callback_data=f'{prefix}:{page+1}'))
    rows = [nav] if nav else []
    toggle_label = t(lang, 'show_locked') if unlocked else t(lang, 'show_unlocked')
    toggle_cb = 'achievements:0' if unlocked else 'achievements_unlocked:0'
    rows.append([InlineKeyboardButton(toggle_label, callback_data=toggle_cb)])
    rows.append([InlineKeyboardButton(t(lang, 'back'), callback_data='profile')])
    return InlineKeyboardMarkup(inline_keyboard=rows)




def coinflip_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'find_game'), callback_data='coinflip_find')],
        [InlineKeyboardButton(t(lang, 'create_game'), callback_data='coinflip_create')],
        [InlineKeyboardButton(t(lang, 'play_bot'), callback_data='coinflip_bot')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='games')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def coinflip_side_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'heads'), callback_data='coinflip_side_heads')],
        [InlineKeyboardButton(t(lang, 'tails'), callback_data='coinflip_side_tails')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='coinflip')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def coinflip_create_confirm_menu(side: str, bet: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'create'), callback_data=f'coinflip_create_room_{side}_{bet}')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='coinflip')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def coinflip_waiting_menu(room_id: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'cancel'), callback_data=f'coinflip_cancel_{room_id}')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def coinflip_rooms_menu(rooms: dict[int, dict], lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = []
    for room_id, data in rooms.items():
        side = t(lang, data['side'])
        text = f"{data['creator_name']} – {data['bet']}€ ({side})"
        inline_keyboard.append([InlineKeyboardButton(text, callback_data=f'coinflip_room_{room_id}')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back'), callback_data='coinflip')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def coinflip_join_confirm_menu(room_id: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'join'), callback_data=f'coinflip_join_{room_id}')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='coinflip_find')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def rules() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('🔙 Back to menu', callback_data='back_to_menu')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def console(role: int, lang: str = 'en') -> InlineKeyboardMarkup:
    assistant_role = Permission.USE | Permission.ASSIGN_PHOTOS
    if role == assistant_role:
        inline_keyboard = [
            [InlineKeyboardButton(t(lang, 'assign_photos_menu'), callback_data='assign_photos')],
            [InlineKeyboardButton(t(lang, 'help'), callback_data='admin_help')],
            [InlineKeyboardButton(t(lang, 'back_to_menu'), callback_data='back_to_menu')]
        ]
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'shop_management_menu'), callback_data='shop_management')],
        [InlineKeyboardButton(t(lang, 'analytics_button'), callback_data='analytics')],
        [InlineKeyboardButton(t(lang, 'information_menu_button'), callback_data='information')],
        [InlineKeyboardButton(t(lang, 'tools'), callback_data='miscs')],
    ]
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'help'), callback_data='admin_help')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back_to_menu'), callback_data='back_to_menu')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def analytics_menu(period: str, view: str, lang: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    period_buttons = []
    for key in ('day', 'week', 'month'):
        label = t(lang, f'analytics_button_{key}')
        if key == period:
            label = f'• {label}'
        period_buttons.append(InlineKeyboardButton(label, callback_data=f'analytics:period:{key}'))
    markup.row(*period_buttons)
    view_options = [
        ('overview', 'analytics_view_overview'),
        ('cities', 'analytics_view_cities'),
        ('types', 'analytics_view_types'),
        ('products', 'analytics_view_products'),
        ('activity', 'analytics_view_activity'),
    ]
    for key, text_key in view_options:
        label = t(lang, text_key)
        if key == view:
            label = f'• {label}'
        markup.add(InlineKeyboardButton(label, callback_data=f'analytics:view:{key}'))
    markup.add(InlineKeyboardButton(t(lang, 'back_to_menu'), callback_data='console'))
    return markup

def confirm_purchase_menu(item_name: str, lang: str, show_promo: bool = True) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'purchase_button'), callback_data=f'buy_{item_name}')]
    ]
    if show_promo:
        inline_keyboard.append(
            [InlineKeyboardButton(t(lang, 'apply_promo'), callback_data=f'applypromo_{item_name}')]
        )
    inline_keyboard.append([InlineKeyboardButton('🔙 Grįžti į meniu', callback_data='back_to_menu')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def user_management(admin_role: int, user_role: int, admin_manage: int, items: int, user_id: int) \
        -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('💸 Papildyti balansą', callback_data=f'fill-user-balance_{user_id}')]
    ]
    if items > 0:
        inline_keyboard.append([InlineKeyboardButton('🎁 Įsigytos prekės', callback_data=f'user-items_{user_id}')])
    if admin_role >= admin_manage and admin_role > user_role:
        if user_role == 1:
            inline_keyboard.append(
                [InlineKeyboardButton('⬆️ Suteikti adminą', callback_data=f'set-admin_{user_id}')])
        else:
            inline_keyboard.append(
                [InlineKeyboardButton('⬇️ Pašalinti adminą', callback_data=f'remove-admin_{user_id}')])
    inline_keyboard.append([InlineKeyboardButton('🔙 Grįžti atgal', callback_data='user_management')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def purchases_dates_list(dates: list[str], lang: str = 'en') -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for d in dates:
        markup.add(InlineKeyboardButton(d, callback_data=f'purchases_date_{d}'))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='console'))
    return markup


def purchases_list(purchases: list[dict], date: str, lang: str = 'en') -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for p in purchases:
        markup.add(
            InlineKeyboardButton(
                f"{p['unique_id']} - {display_name(p['item_name'])}",
                callback_data=f"purchase_{p['unique_id']}_{date}"
            )
        )
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='pirkimai'))
    return markup


def purchase_info_menu(purchase_id: int, date: str, lang: str = 'en') -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(t(lang, 'purchase_view_file'), callback_data=f'view_purchase_{purchase_id}'))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data=f'purchases_date_{date}'))
    return markup


def user_manage_check(user_id: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'yes'), callback_data=f'check-user_{user_id}')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='user_management')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def shop_management(role: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'shop_manage_goods'), callback_data='goods_management')],
        [InlineKeyboardButton(t(lang, 'shop_manage_categories'), callback_data='categories_management')],
        [InlineKeyboardButton(t(lang, 'shop_manage_promos'), callback_data='promo_management')],
        [InlineKeyboardButton(t(lang, 'shop_manage_resellers'), callback_data='resellers_management')],
        [InlineKeyboardButton(t(lang, 'shop_manage_broadcast'), callback_data='send_message')],
    ]
    if role & Permission.OWN:
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'shop_manage_stock'), callback_data='manage_stock')])
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'shop_manage_assistants'), callback_data='assistant_management')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back'), callback_data='console')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def information_menu(role: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'information_users'), callback_data='user_management')],
        [InlineKeyboardButton(t(lang, 'information_logs'), callback_data='show_logs')],
        [InlineKeyboardButton(t(lang, 'information_statistics'), callback_data='statistics')],
        [InlineKeyboardButton(t(lang, 'information_purchases'), callback_data='pirkimai')],
    ]
    if role & Permission.OWN:
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'information_stock'), callback_data='view_stock')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back'), callback_data='console')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def miscs_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'menu_lottery'), callback_data='lottery')],
        [InlineKeyboardButton(t(lang, 'menu_reviews'), callback_data='reviews')],
        [InlineKeyboardButton(t(lang, 'menu_reservations'), callback_data='reservations')],
        [InlineKeyboardButton(t(lang, 'menu_manual_payments'), callback_data='manual_payments')],
        [InlineKeyboardButton(t(lang, 'menu_media'), callback_data='media_library')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='console')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def lottery_menu(role: int | None = None, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'lottery_view_tickets'), callback_data='view_tickets')],
        [InlineKeyboardButton(t(lang, 'lottery_run_action'), callback_data='run_lottery')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='miscs')],
    ]
    if role is not None and role & Permission.OWN:
        inline_keyboard.insert(2, [InlineKeyboardButton(t(lang, 'information_stock'), callback_data='view_stock')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def lottery_run_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'confirm'), callback_data='lottery_confirm')],
        [InlineKeyboardButton(t(lang, 'rerun'), callback_data='lottery_rerun')],
        [InlineKeyboardButton(t(lang, 'cancel'), callback_data='lottery_cancel')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def lottery_broadcast_menu(role: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = []
    if role & Permission.OWN:
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'yes'), callback_data='lottery_broadcast_yes')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'no'), callback_data='lottery_broadcast_no')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def reviews_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'reviews_menu_pending'), callback_data='reviews_status_pending')],
        [InlineKeyboardButton(t(lang, 'reviews_menu_approved'), callback_data='reviews_status_approved')],
        [InlineKeyboardButton(t(lang, 'reviews_menu_rejected'), callback_data='reviews_status_rejected')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='miscs')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def reviews_list_markup(reviews: list, lang: str = 'en') -> InlineKeyboardMarkup:
    rows = []
    for review in reviews:
        rows.append([
            InlineKeyboardButton(
                f"#{review.id} — {review.user_id}",
                callback_data=f'review_view_{review.id}'
            )
        ])
    rows.append([InlineKeyboardButton(t(lang, 'back'), callback_data='reviews')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_actions_keyboard(review_id: int, current_status: str, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = []
    if current_status != 'approved':
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'review_approve'), callback_data=f'review_approve_{review_id}')])
    if current_status != 'rejected':
        inline_keyboard.append([InlineKeyboardButton(t(lang, 'review_reject'), callback_data=f'review_reject_{review_id}')])
    inline_keyboard.append([InlineKeyboardButton(t(lang, 'back'), callback_data='reviews')])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def reservations_list_markup(reservations: list, lang: str = 'en') -> InlineKeyboardMarkup:
    rows = []
    for reservation in reservations:
        rows.append([
            InlineKeyboardButton(
                f"#{reservation.id} — {reservation.item_name}",
                callback_data=f'reservation_view_{reservation.id}'
            )
        ])
    rows.append([InlineKeyboardButton(t(lang, 'back'), callback_data='miscs')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reservation_actions_keyboard(reservation_id: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'reservation_release'), callback_data=f'reservation_release_{reservation_id}')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='reservations')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def manual_payments_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'manual_payments_add'), callback_data='manual_payments_add')],
        [InlineKeyboardButton(t(lang, 'manual_payments_history'), callback_data='manual_payments_history')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='miscs')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def media_library_menu(lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'media_upload_button'), callback_data='media_upload')],
        [InlineKeyboardButton(t(lang, 'media_list_button'), callback_data='media_list')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='miscs')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def media_list_keyboard(assets, lang: str = 'en') -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for asset in assets:
        button_text = f"#{asset.id} {asset.file_type}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f'media_view_{asset.id}'))
    markup.add(InlineKeyboardButton(t(lang, 'back'), callback_data='media_library'))
    return markup


def media_asset_actions(asset_id: int, lang: str = 'en') -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'media_send'), callback_data=f'media_send_{asset_id}')],
        [InlineKeyboardButton(t(lang, 'media_delete'), callback_data=f'media_delete_{asset_id}')],
        [InlineKeyboardButton(t(lang, 'back'), callback_data='media_list')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def goods_management() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('➕ Pridėti prekę', callback_data='item-management')],
        [InlineKeyboardButton('✏️ Atnaujinti prekę', callback_data='update_item')],
        [InlineKeyboardButton('🖼 Priskirti nuotraukas', callback_data='assign_photos')],
        [InlineKeyboardButton('🗑️ Pašalinti prekę', callback_data='delete_item')],
        [InlineKeyboardButton('🛒 Nupirktų prekių informacija', callback_data='show_bought_item')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data='shop_management')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)



def item_management() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('🆕 Sukurti prekę', callback_data='add_item')],
        [InlineKeyboardButton('➕ Pridėti prie esamos prekės', callback_data='update_item_amount')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data='goods_management')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def categories_management() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('🗃️ Sukurti pagrindinę kategoriją', callback_data='add_main_category')],
        [InlineKeyboardButton('📁 Pridėti kategoriją', callback_data='add_category')],
        [InlineKeyboardButton('📂 Pridėti subkategoriją', callback_data='add_subcategory')],
        [InlineKeyboardButton('✏️ Atnaujinti kategoriją', callback_data='update_category')],
        [InlineKeyboardButton('🗑️ Pašalinti kategoriją', callback_data='delete_category')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data='shop_management')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def resellers_management(lang: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'reseller_add_button'), callback_data='reseller_add')],
        [InlineKeyboardButton(t(lang, 'reseller_remove_button'), callback_data='reseller_remove')],
        [InlineKeyboardButton(t(lang, 'reseller_prices_button'), callback_data='reseller_prices')],
        [InlineKeyboardButton(t(lang, 'back_button'), callback_data='shop_management')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def resellers_list(
    resellers: list[tuple[int, str | None]],
    action: str,
    back_data: str,
    lang: str,
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for user_id, username in resellers:
        name = f'@{username}' if username else str(user_id)
        markup.add(InlineKeyboardButton(name, callback_data=f'{action}_{user_id}'))
    markup.add(InlineKeyboardButton(t(lang, 'back_button'), callback_data=back_data))
    return markup


def promo_codes_management() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('➕ Sukurti nuolaidos kodą', callback_data='create_promo')],
        [InlineKeyboardButton('🗑️ Ištrinti nuolaidos kodą', callback_data='delete_promo')],
        [InlineKeyboardButton('🛠 Tvarkyti nuolaidos kodą', callback_data='manage_promo')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data='shop_management')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def promo_expiry_keyboard(back_data: str) -> InlineKeyboardMarkup:
    """Keyboard to choose promo code expiry units."""
    inline_keyboard = [
        [InlineKeyboardButton('Dienos', callback_data='promo_expiry_days')],
        [InlineKeyboardButton('Savaitės', callback_data='promo_expiry_weeks')],
        [InlineKeyboardButton('Mėnesiai', callback_data='promo_expiry_months')],
        [InlineKeyboardButton('Be galiojimo', callback_data='promo_expiry_none')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data=back_data)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def promo_codes_list(codes: list[str], action: str, back_data: str) -> InlineKeyboardMarkup:
    """Create a list of promo codes with callback prefix."""
    markup = InlineKeyboardMarkup()
    for code in codes:
        markup.add(InlineKeyboardButton(code, callback_data=f'{action}_{code}'))
    markup.add(InlineKeyboardButton('🔙 Grįžti atgal', callback_data=back_data))
    return markup


def promo_manage_actions(code: str) -> InlineKeyboardMarkup:
    """Keyboard with actions for a single promo code."""
    inline_keyboard = [
        [InlineKeyboardButton('✏️ Pakeisti nuolaidą', callback_data=f'promo_manage_discount_{code}')],
        [InlineKeyboardButton('⏰ Pakeisti galiojimą', callback_data=f'promo_manage_expiry_{code}')],
        [InlineKeyboardButton('🗑️ Ištrinti', callback_data=f'promo_manage_delete_{code}')],
        [InlineKeyboardButton('🔙 Grįžti atgal', callback_data='manage_promo')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def stock_categories_list(
    list_items: list[str],
    parent: str | None,
    lang: str,
    root_cb: str = 'console',
) -> InlineKeyboardMarkup:
    """List categories or subcategories for stock view."""
    markup = InlineKeyboardMarkup()
    for name in list_items:
        markup.add(InlineKeyboardButton(text=name, callback_data=f'stock_cat:{name}'))
    if parent is None:
        back_data = root_cb if root_cb in {'information', 'shop_management'} else 'console'
    else:
        back_data = f'stock_cat:{parent}'
    markup.add(InlineKeyboardButton(t(lang, 'back_button'), callback_data=back_data))
    return markup


def stock_goods_list(
    list_items: list[str],
    category_name: str,
    lang: str,
    root_cb: str = 'console',
) -> InlineKeyboardMarkup:
    """Show goods with stock counts for a category."""
    markup = InlineKeyboardMarkup()
    for name in list_items:
        amount = select_item_values_amount(name)
        markup.add(InlineKeyboardButton(
            text=f'{display_name(name)} ({amount})',
            callback_data=f'stock_item:{name}:{category_name}'
        ))
    parent = get_category_parent(category_name)
    if parent is None:
        back_data = root_cb if root_cb in {'information', 'shop_management'} else 'console'
    else:
        back_data = f'stock_cat:{parent}'
    markup.add(InlineKeyboardButton(t(lang, 'back_button'), callback_data=back_data))
    return markup


def stock_values_list(values, item_name: str, category_name: str, lang: str) -> InlineKeyboardMarkup:
    """List individual stock entries for an item."""
    markup = InlineKeyboardMarkup()
    for val in values:
        markup.add(InlineKeyboardButton(
            text=f'ID {val.id}',
            callback_data=f'stock_val:{val.id}:{item_name}:{category_name}'
        ))
    markup.add(InlineKeyboardButton(t(lang, 'back_button'), callback_data=f'stock_item:{item_name}:{category_name}'))
    return markup


def stock_value_actions(value_id: int, item_name: str, category_name: str, lang: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'delete_button'), callback_data=f'stock_del:{value_id}:{item_name}:{category_name}')],
        [InlineKeyboardButton(t(lang, 'back_button'), callback_data=f'stock_item:{item_name}:{category_name}')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)



def close() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('Hide', callback_data='close')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def check_sub(channel_username: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('Subscribe', url=f'https://t.me/{channel_username}')
         ],
        [InlineKeyboardButton('Check', callback_data='sub_channel_done')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def back(callback: str, lang: str | None = None) -> InlineKeyboardMarkup:
    lang = lang or 'lt'
    inline_keyboard = [
        [InlineKeyboardButton(t(lang, 'back_button'), callback_data=callback)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def payment_menu(url: str, label: str, lang: str) -> InlineKeyboardMarkup:
    """Return markup for fiat payment invoices."""
    inline_keyboard = [
        [InlineKeyboardButton('✅ Pay', url=url)],
        [InlineKeyboardButton('🔄 Check payment', callback_data=f'check_{label}')],
        [InlineKeyboardButton(t(lang, 'cancel_payment'), callback_data=f'cancel_{label}')],
        [InlineKeyboardButton('🔙 Go back', callback_data='back_to_menu')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def crypto_invoice_menu(invoice_id: str, lang: str) -> InlineKeyboardMarkup:
    """Return markup for crypto invoice."""
    inline_keyboard = [

        [InlineKeyboardButton(t(lang, 'cancel_payment'), callback_data=f'cancel_{invoice_id}')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def confirm_cancel(invoice_id: str, lang: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('✅ Yes', callback_data=f'confirm_cancel_{invoice_id}')],
        [InlineKeyboardButton('🔙 Back', callback_data=f'check_{invoice_id}')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def crypto_choice() -> InlineKeyboardMarkup:
    order = ['BTC', 'ETH', 'LTC', 'SOL', 'USDT', 'USDC', 'TON']
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(order), 2):
        chunk = order[i:i + 2]
        rows.append([
            InlineKeyboardButton(symbol, callback_data=f'crypto_{symbol}')
            for symbol in chunk
        ])
    rows.append([InlineKeyboardButton('🔙 Go back', callback_data='replenish_balance')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crypto_choice_purchase(item_name: str, lang: str) -> InlineKeyboardMarkup:
    """Return crypto choice markup for product purchase."""
    order = ['BTC', 'ETH', 'LTC', 'SOL', 'USDT', 'USDC', 'TON']
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(order), 2):
        chunk = order[i:i + 2]
        rows.append([
            InlineKeyboardButton(symbol, callback_data=f'buycrypto_{symbol}')
            for symbol in chunk
        ])
    rows.append([InlineKeyboardButton(t(lang, 'cancel'), callback_data='cancel_purchase')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reset_config(key: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(f'Reset {key}', callback_data=f'reset_{key}')
         ],
        [InlineKeyboardButton('🔙 Go back', callback_data='settings')
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def question_buttons(question: str, back_data: str) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('✅ Yes', callback_data=f'{question}_yes'),
         InlineKeyboardButton('❌ No', callback_data=f'{question}_no')
         ],
        [InlineKeyboardButton('🔙 Go back', callback_data=back_data)
         ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def blackjack_controls() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton('🃏 Hit', callback_data='blackjack_hit'),
         InlineKeyboardButton('🛑 Stand', callback_data='blackjack_stand')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def blackjack_bet_input_menu(bet: int | None = None) -> InlineKeyboardMarkup:
    bet_text = f'🎲 Bet! ({bet}€)' if bet else '🎲 Bet!'
    inline_keyboard = [
        [InlineKeyboardButton(bet_text, callback_data='blackjack_place_bet')],
        [InlineKeyboardButton('💵 Set Bet', callback_data='blackjack_set_bet')],
        [InlineKeyboardButton('📜 History', callback_data='blackjack_history_0')],
        [InlineKeyboardButton('🔙 Back to menu', callback_data='back_to_menu')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def blackjack_end_menu(bet: int) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(f'▶️ Play Again ({bet}€)', callback_data=f'blackjack_play_{bet}')],
        [InlineKeyboardButton('🔙 Back to menu', callback_data='blackjack')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def blackjack_history_menu(index: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    if index > 0:
        buttons.append(InlineKeyboardButton('◀️', callback_data=f'blackjack_history_{index-1}'))
    buttons.append(InlineKeyboardButton(f'{index+1}/{total}', callback_data='dummy_button'))
    if index < total - 1:
        buttons.append(InlineKeyboardButton('▶️', callback_data=f'blackjack_history_{index+1}'))
    inline_keyboard = [buttons, [InlineKeyboardButton('🔙 Back', callback_data='blackjack')]]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def feedback_menu(prefix: str) -> InlineKeyboardMarkup:
    """Return 1-5 star rating buttons arranged vertically."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("⭐" * i, callback_data=f"{prefix}_{i}")]
            for i in range(1, 6)
        ]
    )


def feedback_reason_menu(prefix: str, lang: str) -> InlineKeyboardMarkup:
    """Return Yes/No menu asking whether to provide feedback text."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(t(lang, 'yes'), callback_data=f'{prefix}_yes'),
        InlineKeyboardButton(t(lang, 'no'), callback_data=f'{prefix}_no'),
    ]])
