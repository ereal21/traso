import datetime

import sqlalchemy
from sqlalchemy import exc, func

from bot.database.models import (
    Achievement,
    BoughtGoods,
    Categories,
    City,
    Database,
    District,
    Goods,
    ItemValues,
    Operations,
    ProductMetadata,
    ProductType,
    PromoCode,
    Reseller,
    ResellerPrice,
    Review,
    Reservation,
    ManualPayment,
    MediaAsset,
    Role,
    StockNotification,
    UnfinishedOperations,
    User,
    UserAchievement,
    UserProfile,
)


def check_user(telegram_id: int) -> User | None:
    try:
        return Database().session.query(User).filter(User.telegram_id == telegram_id).one()
    except exc.NoResultFound:
        return None


def check_user_by_username(username: str) -> User | None:
    try:
        return Database().session.query(User).filter(User.username == username).one()
    except exc.NoResultFound:
        return None


def check_role(telegram_id: int) -> User | None:
    role_id = Database().session.query(User.role_id).filter(User.telegram_id == telegram_id).one()[0]
    return Database().session.query(Role.permissions).filter(Role.id == role_id).one()[0]


def check_role_name_by_id(role_id: int):
    return Database().session.query(Role.name).filter(Role.id == role_id).one()[0]


def get_role_id_by_name(role_name: str) -> int | None:
    """Return role id for the given name or None if not found."""
    try:
        return Database().session.query(Role.id).filter(Role.name == role_name).one()[0]
    except exc.NoResultFound:
        return None


def select_today_users(date: str) -> int | None:
    try:
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        start_of_day = datetime.datetime.combine(date_obj, datetime.time.min)
        end_of_day = datetime.datetime.combine(date_obj, datetime.time.max)

        return Database().session.query(User).filter(
            User.registration_date >= str(start_of_day),
            User.registration_date <= str(end_of_day)
        ).count()
    except exc.NoResultFound:
        return None


def get_user_count() -> int:
    return Database().session.query(User).count()


def select_admins() -> int | None:
    try:
        return Database().session.query(func.count()).filter(User.role_id > 1).scalar()
    except exc.NoResultFound:
        return None


def get_all_users() -> list[tuple[int]]:
    return Database().session.query(User.telegram_id).all()


def get_resellers() -> list[tuple[int, str | None]]:
    session = Database().session
    return session.query(User.telegram_id, User.username).join(
        Reseller, Reseller.user_id == User.telegram_id
    ).all()


def is_reseller(user_id: int) -> bool:
    return Database().session.query(Reseller).filter(Reseller.user_id == user_id).first() is not None


def item_in_stock(item_name: str) -> bool:
    """Return True if item has unlimited quantity or remaining stock."""
    if check_value(item_name):
        return True
    return select_item_values_amount(item_name) > 0


def get_all_categories() -> list[str]:
    """Return categories that contain at least one item in stock."""
    categories = [c[0] for c in Database().session.query(Categories.name)
                  .filter(Categories.parent_name.is_(None)).all()]
    result = []
    for name in categories:
        if get_all_items(name) or get_subcategories(name):
            result.append(name)
    return result


def get_all_category_names() -> list[str]:
    """Return all top-level categories regardless of contents."""
    return [c[0] for c in Database().session.query(Categories.name)
            .filter(Categories.parent_name.is_(None)).all()]


def get_all_subcategories(parent_name: str) -> list[str]:
    """Return all subcategories of a given category."""
    return [c[0] for c in Database().session.query(Categories.name)
            .filter(Categories.parent_name == parent_name).all()]


def get_subcategories(parent_name: str) -> list[str]:
    subs = [c[0] for c in Database().session.query(Categories.name)
            .filter(Categories.parent_name == parent_name).all()]
    result = []
    for sub in subs:
        if get_all_items(sub) or get_subcategories(sub):
            result.append(sub)
    return result


def get_category_parent(category_name: str) -> str | None:
    result = (Database().session.query(Categories.parent_name)
              .filter(Categories.name == category_name).first())
    return result[0] if result else None


def get_all_items(category_name: str) -> list[str]:
    items = [item[0] for item in
             Database().session.query(Goods.name)
             .filter(Goods.category_name == category_name).all()]
    return [name for name in items if item_in_stock(name)]


def get_all_item_names(category_name: str) -> list[str]:
    """Return all items for a category regardless of stock."""
    return [item[0] for item in
            Database().session.query(Goods.name)
            .filter(Goods.category_name == category_name).all()]


def get_out_of_stock_items(category_name: str) -> list[str]:
    """Return items in a category that currently have no stock."""
    items = get_all_item_names(category_name)
    result = []
    for name in items:
        if not item_in_stock(name):
            result.append(name)
    return result


def get_out_of_stock_categories() -> list[str]:
    """Return root categories containing any out-of-stock items."""
    categories = [c[0] for c in Database().session.query(Categories.name)
                  .filter(Categories.parent_name.is_(None)).all()]
    result = []
    for name in categories:
        if get_out_of_stock_items(name) or get_out_of_stock_subcategories(name):
            result.append(name)
    return result


def get_out_of_stock_subcategories(parent_name: str) -> list[str]:
    subs = [c[0] for c in Database().session.query(Categories.name)
            .filter(Categories.parent_name == parent_name).all()]
    result = []
    for sub in subs:
        if get_out_of_stock_items(sub) or get_out_of_stock_subcategories(sub):
            result.append(sub)
    return result


def get_bought_item_info(item_id: str) -> dict | None:
    result = Database().session.query(BoughtGoods).filter(BoughtGoods.id == item_id).first()
    return result.__dict__ if result else None


def get_item_info(item_name: str, user_id: int | None = None) -> dict | None:
    session = Database().session
    result = session.query(Goods).filter(Goods.name == item_name).first()
    if not result:
        return None
    data = result.__dict__.copy()
    if user_id is not None and is_reseller(user_id):
        price = session.query(ResellerPrice.price).filter_by(
            reseller_id=None, item_name=item_name
        ).first()
        if price:
            data['price'] = price[0]
    return data


def get_user_balance(telegram_id: int) -> float | None:
    result = Database().session.query(User.balance).filter(User.telegram_id == telegram_id).first()
    return result[0] if result else None


def get_user_language(telegram_id: int) -> str | None:
    result = Database().session.query(User.language).filter(User.telegram_id == telegram_id).first()
    return result[0] if result else None


def get_user_tickets(telegram_id: int) -> int:
    result = (Database().session.query(User.lottery_tickets)
              .filter(User.telegram_id == telegram_id).first())
    return result[0] if result else 0


def get_users_with_tickets() -> list[tuple[int, str | None, int]]:
    return Database().session.query(
        User.telegram_id, User.username, User.lottery_tickets
    ).filter(User.lottery_tickets > 0).all()


def has_user_achievement(user_id: int, code: str) -> bool:
    return Database().session.query(UserAchievement).filter_by(
        user_id=user_id, achievement_code=code
    ).first() is not None


def get_achievement_users(code: str) -> int:
    session = Database().session
    return session.query(func.count(UserAchievement.user_id)).filter(
        UserAchievement.achievement_code == code
    ).scalar()


def get_all_admins() -> list[int]:
    return [admin[0] for admin in Database().session.query(User.telegram_id).filter(User.role_id == 'ADMIN').all()]


def check_item(item_name: str) -> dict | None:
    result = Database().session.query(Goods).filter(Goods.name == item_name).first()
    return result.__dict__ if result else None


def check_category(category_name: str) -> dict | None:
    result = Database().session.query(Categories).filter(Categories.name == category_name).first()
    return result.__dict__ if result else None


def can_use_discount(item_name: str) -> bool:
    """Return True if item's main category allows discounts."""
    session = Database().session
    category_name = session.query(Goods.category_name).filter(Goods.name == item_name).scalar()
    if not category_name:
        return True
    while True:
        category = session.query(Categories.parent_name, Categories.allow_discounts) \
            .filter(Categories.name == category_name).first()
        if not category:
            return True
        parent, allow = category
        if parent is None:
            return bool(allow)
        category_name = parent


def can_get_referral_reward(item_name: str) -> bool:
    """Return True if item's main category allows referral rewards."""
    session = Database().session
    category_name = session.query(Goods.category_name).filter(Goods.name == item_name).scalar()
    if not category_name:
        return True
    while True:
        category = session.query(Categories.parent_name, Categories.allow_referral_rewards) \
            .filter(Categories.name == category_name).first()
        if not category:
            return True
        parent, allow = category
        if parent is None:
            return bool(allow)
        category_name = parent



def get_item_value(item_name: str) -> dict | None:
    result = Database().session.query(ItemValues).filter(ItemValues.item_name == item_name).first()
    return result.__dict__ if result else None


def get_item_values(item_name: str):
    return Database().session.query(ItemValues).filter(ItemValues.item_name == item_name).all()


def get_item_value_by_id(value_id: int) -> dict | None:
    result = Database().session.query(ItemValues).filter(ItemValues.id == value_id).first()
    return result.__dict__ if result else None


def select_item_values_amount(item_name: str) -> int:
    return Database().session.query(func.count()).filter(ItemValues.item_name == item_name).scalar()


def check_value(item_name: str) -> bool | None:
    try:
        result = False
        values = select_item_values_amount(item_name)
        for i in range(values):
            is_inf = Database().session.query(ItemValues).filter(ItemValues.item_name == item_name).first()
            if is_inf and is_inf.is_infinity:
                result = True
    except exc.NoResultFound:
        return False
    return result


def has_stock_notification(user_id: int, item_name: str) -> bool:
    return Database().session.query(StockNotification).filter_by(
        user_id=user_id, item_name=item_name
    ).first() is not None


def get_item_subscribers(item_name: str) -> list[int]:
    return [row[0] for row in Database().session.query(StockNotification.user_id)
            .filter(StockNotification.item_name == item_name).all()]


def select_user_items(buyer_id: int) -> int:
    return Database().session.query(func.count()).filter(BoughtGoods.buyer_id == buyer_id).scalar()


def get_reviews_by_status(status: str, limit: int | None = None) -> list[Review]:
    query = Database().session.query(Review).filter(Review.status == status)
    query = query.order_by(Review.created_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_review(review_id: int) -> Review | None:
    return Database().session.query(Review).filter(Review.id == review_id).first()


def get_reservations_by_status(status: str = 'active') -> list[Reservation]:
    session = Database().session
    return session.query(Reservation).filter(Reservation.status == status).order_by(Reservation.reserved_at.asc()).all()


def get_reservation_by_operation(operation_id: str) -> Reservation | None:
    session = Database().session
    if not operation_id:
        return None
    return session.query(Reservation).filter(Reservation.operation_id == operation_id).first()


def get_reservation(reservation_id: int) -> Reservation | None:
    return Database().session.query(Reservation).filter(Reservation.id == reservation_id).first()


def get_manual_payments(limit: int = 50) -> list[ManualPayment]:
    session = Database().session
    return (
        session.query(ManualPayment)
        .order_by(ManualPayment.created_at.desc())
        .limit(limit)
        .all()
    )


def get_media_assets(limit: int = 50) -> list[MediaAsset]:
    session = Database().session
    return (
        session.query(MediaAsset)
        .order_by(MediaAsset.created_at.desc())
        .limit(limit)
        .all()
    )


def get_media_asset(asset_id: int) -> MediaAsset | None:
    return Database().session.query(MediaAsset).filter(MediaAsset.id == asset_id).first()


def select_bought_items(buyer_id: int) -> list[str]:
    return Database().session.query(BoughtGoods).filter(BoughtGoods.buyer_id == buyer_id).all()


def select_bought_item(unique_id: int) -> dict | None:
    result = Database().session.query(BoughtGoods).filter(BoughtGoods.unique_id == unique_id).first()
    return result.__dict__ if result else None


def bought_items_list(buyer_id: int) -> list[str]:
    return [
        item[0] for item in
        Database().session.query(BoughtGoods.item_name).filter(BoughtGoods.buyer_id == buyer_id).all()]


def get_purchase_dates() -> list[str]:
    return [d[0] for d in Database().session.query(func.date(BoughtGoods.bought_datetime)).distinct().all()]


def get_purchases_by_date(date: str) -> list[dict]:
    rows = (
        Database().session.query(BoughtGoods)
        .filter(func.date(BoughtGoods.bought_datetime) == date)
        .all()
    )
    return [r.__dict__ for r in rows]


def select_all_users() -> int:
    return Database().session.query(func.count()).filter(User).scalar()


def select_count_items() -> int:
    return Database().session.query(ItemValues).count()


def select_count_goods() -> int:
    return Database().session.query(Goods).count()


def select_count_categories() -> int:
    return Database().session.query(Categories).count()


def select_count_bought_items() -> int:
    return Database().session.query(BoughtGoods).count()


def select_today_orders(date: str) -> int | None:
    try:
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        start_of_day = datetime.datetime.combine(date_obj, datetime.time.min)
        end_of_day = datetime.datetime.combine(date_obj, datetime.time.max)

        return (
                Database().session.query(func.sum(BoughtGoods.price))
                .filter(
                    func.date(BoughtGoods.bought_datetime) >= start_of_day.date(),
                    func.date(BoughtGoods.bought_datetime) <= end_of_day.date()
                )
                .scalar() or 0
        )
    except exc.NoResultFound:
        return None


def select_all_orders() -> float:
    return Database().session.query(func.sum(BoughtGoods.price)).scalar() or 0


def select_today_operations(date: str) -> int | None:
    try:
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        start_of_day = datetime.datetime.combine(date_obj, datetime.time.min)
        end_of_day = datetime.datetime.combine(date_obj, datetime.time.max)

        return (
                Database().session.query(func.sum(Operations.operation_value))
                .filter(
                    func.date(Operations.operation_time) >= start_of_day.date(),
                    func.date(Operations.operation_time) <= end_of_day.date()
                )
                .scalar() or 0
        )
    except exc.NoResultFound:
        return None


def select_all_operations() -> float:
    return Database().session.query(func.sum(Operations.operation_value)).scalar() or 0


def select_users_balance() -> float:
    return Database().session.query(func.sum(User.balance)).scalar()


def select_user_operations(user_id: int) -> list[float]:
    return [operation[0] for operation in
            Database().session.query(Operations.operation_value).filter(Operations.user_id == user_id).all()]


def select_unfinished_operations(operation_id: str) -> list[int] | None:
    try:
        return Database().session.query(UnfinishedOperations.operation_value).filter(
            UnfinishedOperations.operation_id == operation_id).one()
    except sqlalchemy.exc.NoResultFound:
        return None


def get_unfinished_operation(operation_id: str) -> tuple[int, int, int | None] | None:
    """Return (user_id, operation_value, message_id) for unfinished operation."""
    result = (
        Database()
        .session.query(
            UnfinishedOperations.user_id,
            UnfinishedOperations.operation_value,
            UnfinishedOperations.message_id,
        )
        .filter(UnfinishedOperations.operation_id == operation_id)
        .first()
    )
    return (result.user_id, result.operation_value, result.message_id) if result else None


def get_user_unfinished_operation(user_id: int) -> tuple[str, int | None] | None:
    """Return (operation_id, message_id) for a user's unfinished operation."""
    result = (
        Database()
        .session.query(
            UnfinishedOperations.operation_id,
            UnfinishedOperations.message_id,
        )
        .filter(UnfinishedOperations.user_id == user_id)
        .first()
    )
    return (result.operation_id, result.message_id) if result else None


def check_user_referrals(user_id: int) -> list[int]:
    return Database().session.query(User).filter(User.referral_id == user_id).count()


def get_user_referral(user_id: int) -> int | None:
    result = Database().session.query(User.referral_id).filter(User.telegram_id == user_id).first()
    return result[0] if result else None


def sum_referral_operations(user_id: int) -> int:
    """Return total top-up amount from users referred by given user."""
    session = Database().session
    refs = session.query(User.telegram_id).filter(User.referral_id == user_id).all()
    total = 0
    for (ref_id,) in refs:
        ops_sum = (
            session.query(func.sum(Operations.operation_value))
            .filter(Operations.user_id == ref_id)
            .scalar()
        )
        total += ops_sum or 0
    return total


def get_promocode(code: str) -> dict | None:
    result = (Database().session.query(PromoCode)
              .filter(PromoCode.code == code, PromoCode.active.is_(True))
              .first())
    return result.__dict__ if result else None


def get_all_promocodes() -> list[PromoCode]:
    return Database().session.query(PromoCode).filter(PromoCode.active.is_(True)).all()


def get_user_profile(user_id: int) -> dict | None:
    session = Database().session
    profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        return None
    return {
        'user_id': profile.user_id,
        'city_id': profile.city_id,
        'city': profile.city.name if profile.city else None,
        'district_id': profile.district_id,
        'district': profile.district.name if profile.district else None,
        'status': profile.status,
        'last_activity': profile.last_activity,
    }


def get_cities() -> list[dict]:
    session = Database().session
    cities = session.query(City).order_by(func.lower(City.name)).all()
    return [
        {
            'id': city.id,
            'name': city.name,
            'region': city.region,
        }
        for city in cities
    ]


def get_city(city_id: int) -> dict | None:
    session = Database().session
    city = session.query(City).filter(City.id == city_id).first()
    if not city:
        return None
    return {'id': city.id, 'name': city.name, 'region': city.region}


def get_regions() -> list[str]:
    session = Database().session
    rows = session.query(City.region).filter(City.region.isnot(None)).distinct().all()
    return sorted([row[0] for row in rows if row[0]])


def get_districts(city_id: int | None = None) -> list[dict]:
    session = Database().session
    query = session.query(District)
    if city_id is not None:
        query = query.filter(District.city_id == city_id)
    districts = query.order_by(func.lower(District.name)).all()
    return [
        {
            'id': district.id,
            'name': district.name,
            'city_id': district.city_id,
        }
        for district in districts
    ]


def get_product_types() -> list[dict]:
    session = Database().session
    product_types = session.query(ProductType).order_by(func.lower(ProductType.name)).all()
    return [{'id': pt.id, 'name': pt.name} for pt in product_types]


def get_product_type(type_id: int) -> dict | None:
    session = Database().session
    product_type = session.query(ProductType).filter(ProductType.id == type_id).first()
    if not product_type:
        return None
    return {'id': product_type.id, 'name': product_type.name}


def get_product_metadata(item_name: str) -> dict | None:
    session = Database().session
    metadata = session.query(ProductMetadata).filter(ProductMetadata.item_name == item_name).first()
    if not metadata:
        return None
    return {
        'item_name': metadata.item_name,
        'product_type_id': metadata.product_type_id,
        'product_type': metadata.product_type.name if metadata.product_type else None,
        'city_id': metadata.city_id,
        'city': metadata.city.name if metadata.city else None,
        'district_id': metadata.district_id,
        'district': metadata.district.name if metadata.district else None,
    }


def get_sales_totals(days: int, bucket: str = 'day') -> list[dict]:
    session = Database().session
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
    if bucket == 'week':
        group_expr = func.strftime('%Y-%W', BoughtGoods.bought_datetime)
    elif bucket == 'month':
        group_expr = func.strftime('%Y-%m', BoughtGoods.bought_datetime)
    else:
        group_expr = func.date(BoughtGoods.bought_datetime)
    rows = (
        session.query(
            group_expr.label('period'),
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
            func.count(BoughtGoods.id).label('orders'),
        )
        .filter(BoughtGoods.bought_datetime >= cutoff_str)
        .group_by('period')
        .order_by('period')
        .all()
    )
    return [
        {
            'period': row.period,
            'revenue': int(row.revenue or 0),
            'orders': row.orders,
        }
        for row in rows
    ]


def get_total_revenue() -> int:
    session = Database().session
    total = session.query(func.sum(BoughtGoods.price)).scalar()
    return int(total or 0)


def get_sales_by_city() -> list[dict]:
    session = Database().session
    rows = (
        session.query(
            City.id,
            City.name,
            City.region,
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
            func.count(BoughtGoods.id).label('orders'),
        )
        .join(UserProfile, UserProfile.city_id == City.id)
        .join(BoughtGoods, BoughtGoods.buyer_id == UserProfile.user_id)
        .group_by(City.id)
        .order_by(func.sum(BoughtGoods.price).desc())
        .all()
    )
    data = [
        {
            'city_id': row.id,
            'city': row.name,
            'region': row.region,
            'revenue': int(row.revenue or 0),
            'orders': row.orders,
        }
        for row in rows
    ]
    unknown = (
        session.query(
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
            func.count(BoughtGoods.id).label('orders'),
        )
        .outerjoin(UserProfile, UserProfile.user_id == BoughtGoods.buyer_id)
        .filter(UserProfile.city_id.is_(None))
        .one()
    )
    unknown_revenue = int(unknown.revenue or 0)
    if unknown_revenue > 0 or unknown.orders > 0:
        data.append(
            {
                'city_id': None,
                'city': 'Unknown',
                'region': None,
                'revenue': unknown_revenue,
                'orders': unknown.orders,
            }
        )
    return data


def get_sales_by_product_type() -> list[dict]:
    session = Database().session
    rows = (
        session.query(
            ProductType.id,
            ProductType.name,
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
            func.count(BoughtGoods.id).label('orders'),
        )
        .join(ProductMetadata, ProductMetadata.product_type_id == ProductType.id)
        .join(BoughtGoods, BoughtGoods.item_name == ProductMetadata.item_name)
        .group_by(ProductType.id)
        .order_by(func.sum(BoughtGoods.price).desc())
        .all()
    )
    data = [
        {
            'product_type_id': row.id,
            'product_type': row.name,
            'revenue': int(row.revenue or 0),
            'orders': row.orders,
        }
        for row in rows
    ]
    unknown = (
        session.query(
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
            func.count(BoughtGoods.id).label('orders'),
        )
        .outerjoin(ProductMetadata, ProductMetadata.item_name == BoughtGoods.item_name)
        .filter(ProductMetadata.product_type_id.is_(None))
        .one()
    )
    unknown_revenue = int(unknown.revenue or 0)
    if unknown_revenue > 0 or unknown.orders > 0:
        data.append(
            {
                'product_type_id': None,
                'product_type': 'Uncategorized',
                'revenue': unknown_revenue,
                'orders': unknown.orders,
            }
        )
    return data


def get_top_products(limit: int = 5) -> list[dict]:
    session = Database().session
    rows = (
        session.query(
            BoughtGoods.item_name,
            func.count(BoughtGoods.id).label('orders'),
            func.coalesce(func.sum(BoughtGoods.price), 0).label('revenue'),
        )
        .group_by(BoughtGoods.item_name)
        .order_by(func.sum(BoughtGoods.price).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            'item_name': row.item_name,
            'orders': row.orders,
            'revenue': int(row.revenue or 0),
        }
        for row in rows
    ]


def _is_active(profile_status: str | None, last_activity: str | None, last_purchase: str | None, threshold: datetime.date) -> bool:
    if profile_status == 'inactive':
        return False
    if last_activity:
        try:
            last_dt = datetime.datetime.fromisoformat(last_activity)
            if last_dt.date() >= threshold:
                return True
        except ValueError:
            pass
    if last_purchase:
        try:
            purchase_date = datetime.date.fromisoformat(last_purchase)
            if purchase_date >= threshold:
                return True
        except ValueError:
            pass
    return False


def get_user_activity_counts(threshold_days: int = 30) -> dict[str, int]:
    session = Database().session
    rows = (
        session.query(
            User.telegram_id,
            User.last_purchase_date,
            UserProfile.status,
            UserProfile.last_activity,
        )
        .outerjoin(UserProfile, UserProfile.user_id == User.telegram_id)
        .all()
    )
    threshold = datetime.date.today() - datetime.timedelta(days=threshold_days)
    active = 0
    inactive = 0
    for row in rows:
        if _is_active(row.status, row.last_activity, row.last_purchase_date, threshold):
            active += 1
        else:
            inactive += 1
    return {'active': active, 'inactive': inactive}


def get_user_ids_by_status(active: bool, threshold_days: int = 30) -> list[int]:
    session = Database().session
    rows = (
        session.query(
            User.telegram_id,
            User.last_purchase_date,
            UserProfile.status,
            UserProfile.last_activity,
        )
        .outerjoin(UserProfile, UserProfile.user_id == User.telegram_id)
        .all()
    )
    threshold = datetime.date.today() - datetime.timedelta(days=threshold_days)
    result = []
    for row in rows:
        is_active = _is_active(row.status, row.last_activity, row.last_purchase_date, threshold)
        if is_active == active:
            result.append(row.telegram_id)
    return result


def get_user_ids_by_city(city_id: int) -> list[int]:
    session = Database().session
    return [
        row[0]
        for row in session.query(UserProfile.user_id).filter(UserProfile.city_id == city_id).all()
    ]


def get_user_ids_by_region(region: str) -> list[int]:
    session = Database().session
    return [
        row[0]
        for row in (
            session.query(UserProfile.user_id)
            .join(City, City.id == UserProfile.city_id)
            .filter(City.region == region)
            .all()
        )
    ]


def get_all_user_ids() -> list[int]:
    return [row[0] for row in Database().session.query(User.telegram_id).all()]


def get_user_ids_without_activity() -> list[int]:
    session = Database().session
    rows = (
        session.query(User.telegram_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.telegram_id)
        .filter(
            (UserProfile.last_activity.is_(None))
            & (User.last_purchase_date.is_(None))
        )
        .all()
    )
    return [row[0] for row in rows]
