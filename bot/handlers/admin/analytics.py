from aiogram import Dispatcher
from aiogram.types import CallbackQuery

from bot.database.methods import (
    get_sales_by_city,
    get_sales_by_product_type,
    get_sales_totals,
    get_top_products,
    get_total_revenue,
    get_user_activity_counts,
    get_user_language,
)
from bot.handlers.other import get_bot_user_ids
from bot.keyboards import analytics_menu
from bot.localization import t
from bot.misc import TgConfig
from bot.utils import display_name
from bot.utils.feature_config import feature_disabled_text, is_enabled


PERIOD_PRESETS = {
    'day': {'days': 7, 'bucket': 'day', 'label_key': 'analytics_period_daily'},
    'week': {'days': 28, 'bucket': 'week', 'label_key': 'analytics_period_weekly'},
    'month': {'days': 180, 'bucket': 'month', 'label_key': 'analytics_period_monthly'},
}


def _state_key(user_id: int) -> str:
    return f'{user_id}_analytics_state'


def _get_state(user_id: int) -> dict:
    state = TgConfig.STATE.get(_state_key(user_id))
    if not state:
        state = {'period': 'day', 'view': 'overview'}
        TgConfig.STATE[_state_key(user_id)] = state
    return state


def _set_state(user_id: int, period: str | None = None, view: str | None = None) -> dict:
    state = _get_state(user_id)
    if period:
        state['period'] = period
    if view:
        state['view'] = view
    TgConfig.STATE[_state_key(user_id)] = state
    return state


def _format_chart(data: list[dict], lang: str) -> str:
    if not data:
        return t(lang, 'analytics_no_data')
    max_revenue = max(row['revenue'] for row in data) or 1
    bar_unit = max_revenue / 20
    lines = []
    for row in data:
        bar_length = int(row['revenue'] / bar_unit) if max_revenue else 0
        bar = '▇' * max(bar_length, 1) if row['revenue'] > 0 else '▁'
        lines.append(
            t(
                lang,
                'analytics_chart_line',
                period=row['period'],
                bar=bar,
                revenue=row['revenue'],
                orders=row['orders'],
            )
        )
    return '\n'.join(lines)


def _render_overview(lang: str, period_key: str) -> str:
    preset = PERIOD_PRESETS.get(period_key, PERIOD_PRESETS['day'])
    totals = get_sales_totals(preset['days'], preset['bucket'])
    total_revenue = get_total_revenue()
    lines = [
        t(lang, 'analytics_title'),
        '',
        t(lang, 'analytics_total_revenue', amount=total_revenue),
        '',
        t(lang, 'analytics_chart_header', label=t(lang, preset['label_key'])),
        _format_chart(totals, lang),
    ]
    return '\n'.join(lines)


def _render_cities(lang: str) -> str:
    data = get_sales_by_city()
    if not data:
        return '\n'.join([t(lang, 'analytics_title'), '', t(lang, 'analytics_no_data')])
    lines = [t(lang, 'analytics_title'), '', t(lang, 'analytics_top_cities_header')]
    for row in data[:5]:
        city_name = row['city'] or t(lang, 'analytics_unknown_city')
        if row['region']:
            city_name = t(lang, 'analytics_city_with_region', city=city_name, region=row['region'])
        lines.append(
            t(
                lang,
                'analytics_group_line',
                name=city_name,
                revenue=row['revenue'],
                orders=row['orders'],
            )
        )
    return '\n'.join(lines)


def _render_product_types(lang: str) -> str:
    data = get_sales_by_product_type()
    if not data:
        return '\n'.join([t(lang, 'analytics_title'), '', t(lang, 'analytics_no_data')])
    lines = [t(lang, 'analytics_title'), '', t(lang, 'analytics_top_types_header')]
    for row in data[:5]:
        type_name = row['product_type'] or t(lang, 'analytics_uncategorized')
        lines.append(
            t(
                lang,
                'analytics_group_line',
                name=type_name,
                revenue=row['revenue'],
                orders=row['orders'],
            )
        )
    return '\n'.join(lines)


def _render_products(lang: str) -> str:
    data = get_top_products()
    if not data:
        return '\n'.join([t(lang, 'analytics_title'), '', t(lang, 'analytics_no_data')])
    lines = [t(lang, 'analytics_title'), '', t(lang, 'analytics_top_products_header')]
    for row in data:
        item_name = display_name(row['item_name'])
        lines.append(
            t(
                lang,
                'analytics_group_line',
                name=item_name,
                revenue=row['revenue'],
                orders=row['orders'],
            )
        )
    return '\n'.join(lines)


def _render_activity(lang: str) -> str:
    counts = get_user_activity_counts()
    lines = [
        t(lang, 'analytics_title'),
        '',
        t(lang, 'analytics_activity_header'),
        t(lang, 'analytics_activity_line_active', count=counts.get('active', 0)),
        t(lang, 'analytics_activity_line_inactive', count=counts.get('inactive', 0)),
    ]
    return '\n'.join(lines)


def _render_view(lang: str, view: str, period: str) -> str:
    if view == 'cities':
        return _render_cities(lang)
    if view == 'types':
        return _render_product_types(lang)
    if view == 'products':
        return _render_products(lang)
    if view == 'activity':
        return _render_activity(lang)
    return _render_overview(lang, period)


async def _respond(call: CallbackQuery, period: str | None = None, view: str | None = None) -> None:
    bot, user_id = await get_bot_user_ids(call)
    if not is_enabled('analytics'):
        await call.answer(feature_disabled_text(call.from_user.id if call.from_user else None), show_alert=True)
        return
    state = _set_state(user_id, period, view)
    lang = get_user_language(user_id) or 'en'
    text = _render_view(lang, state['view'], state['period'])
    markup = analytics_menu(state['period'], state['view'], lang)
    await bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


async def analytics_callback(call: CallbackQuery) -> None:
    await _respond(call)


async def analytics_period_callback(call: CallbackQuery) -> None:
    period = call.data.split(':')[-1]
    await _respond(call, period=period)


async def analytics_view_callback(call: CallbackQuery) -> None:
    view = call.data.split(':')[-1]
    await _respond(call, view=view)


def register_analytics(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(analytics_callback, lambda c: c.data == 'analytics', state='*')
    dp.register_callback_query_handler(
        analytics_period_callback,
        lambda c: c.data.startswith('analytics:period:'),
        state='*',
    )
    dp.register_callback_query_handler(
        analytics_view_callback,
        lambda c: c.data.startswith('analytics:view:'),
        state='*',
    )