import datetime

import datetime

from bot.database.models import (
    User,
    ItemValues,
    Goods,
    Categories,
    PromoCode,
    StockNotification,
    ResellerPrice,
    UserProfile,
    City,
    District,
    ProductType,
    ProductMetadata,
    Review,
    Reservation,
    ManualPayment,
    MediaAsset,
)
from bot.database import Database


def set_role(telegram_id: str, role: int) -> None:
    Database().session.query(User).filter(User.telegram_id == telegram_id).update(
        values={User.role_id: role})
    Database().session.commit()


def update_balance(telegram_id: int | str, summ: int) -> None:
    old_balance = User.balance
    new_balance = old_balance + summ
    Database().session.query(User).filter(User.telegram_id == telegram_id).update(
        values={User.balance: new_balance})
    Database().session.commit()


def update_user_language(telegram_id: int, language: str) -> None:
    Database().session.query(User).filter(User.telegram_id == telegram_id).update(
        values={User.language: language})
    Database().session.commit()


def update_lottery_tickets(telegram_id: int, delta: int) -> None:
    Database().session.query(User).filter(User.telegram_id == telegram_id).update(
        values={User.lottery_tickets: User.lottery_tickets + delta}, synchronize_session=False)
    Database().session.commit()


def reset_lottery_tickets() -> None:
    Database().session.query(User).update({User.lottery_tickets: 0})
    Database().session.commit()


def buy_item_for_balance(telegram_id: str, summ: int) -> int:
    old_balance = User.balance
    new_balance = old_balance - summ
    Database().session.query(User).filter(User.telegram_id == telegram_id).update(
        values={User.balance: new_balance})
    Database().session.commit()
    return Database().session.query(User.balance).filter(User.telegram_id == telegram_id).one()[0]


def update_item(item_name: str, new_name: str, new_description: str, new_price: int,
                new_category_name: str, new_delivery_description: str | None) -> None:
    Database().session.query(ItemValues).filter(ItemValues.item_name == item_name).update(
        values={ItemValues.item_name: new_name}
    )
    Database().session.query(Goods).filter(Goods.name == item_name).update(
        values={Goods.name: new_name,
                Goods.description: new_description,
                Goods.price: new_price,
                Goods.category_name: new_category_name,
                Goods.delivery_description: new_delivery_description}
    )
    Database().session.commit()


def update_category(category_name: str, new_name: str) -> None:
    Database().session.query(Goods).filter(Goods.category_name == category_name).update(
        values={Goods.category_name: new_name})
    Database().session.query(Categories).filter(Categories.name == category_name).update(
        values={Categories.name: new_name})
    Database().session.commit()


def update_promocode(code: str, discount: int | None = None, expires_at: str | None = None) -> None:
    """Update promo code discount or expiry date."""
    values = {}
    if discount is not None:
        values[PromoCode.discount] = discount
    if expires_at is not None or expires_at is None:
        values[PromoCode.expires_at] = expires_at
    if not values:
        return
    Database().session.query(PromoCode).filter(PromoCode.code == code).update(values=values)
    Database().session.commit()


def set_reseller_price(reseller_id: int | None, item_name: str, price: int) -> None:
    session = Database().session
    entry = session.query(ResellerPrice).filter_by(
        reseller_id=reseller_id, item_name=item_name
    ).first()
    if entry:
        entry.price = price
    else:
        session.add(ResellerPrice(reseller_id=reseller_id, item_name=item_name, price=price))
    session.commit()


def clear_stock_notifications(item_name: str) -> None:
    Database().session.query(StockNotification).filter(
        StockNotification.item_name == item_name
    ).delete(synchronize_session=False)
    Database().session.commit()


def process_purchase_streak(telegram_id: int) -> None:
    """Update streak data after a successful purchase."""
    session = Database().session
    user = session.query(User).filter(User.telegram_id == telegram_id).one()
    today = datetime.date.today()

    if user.streak_discount:
        user.streak_discount = False
        user.purchase_streak = 0

    if user.last_purchase_date:
        last_date = datetime.date.fromisoformat(user.last_purchase_date)
        diff = (today - last_date).days
        if diff == 1:
            user.purchase_streak += 1
        elif diff > 1:
            user.purchase_streak = 1
    else:
        user.purchase_streak = 1

    user.last_purchase_date = today.isoformat()

    if user.purchase_streak >= 3:
        user.purchase_streak = 0
        user.streak_discount = True

    session.commit()


def update_user_profile(
    user_id: int,
    city_id: int | None = None,
    district_id: int | None = None,
    status: str | None = None,
    last_activity: str | None = None,
) -> None:
    session = Database().session
    profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
    if city_id is not None:
        profile.city_id = city_id
        if district_id is not None:
            profile.district_id = district_id
        elif profile.district_id is not None:
            # Reset district if city changes but district not provided
            profile.district_id = None
    elif district_id is not None:
        profile.district_id = district_id
    if status is not None:
        profile.status = status
    if last_activity is not None:
        profile.last_activity = last_activity
    session.commit()


def update_city(city_id: int, name: str | None = None, region: str | None = None) -> None:
    values = {}
    if name is not None:
        values[City.name] = name
    if region is not None or region is None:
        values[City.region] = region
    if not values:
        return
    Database().session.query(City).filter(City.id == city_id).update(values)
    Database().session.commit()


def update_district(district_id: int, name: str | None = None, city_id: int | None = None) -> None:
    values = {}
    if name is not None:
        values[District.name] = name
    if city_id is not None:
        values[District.city_id] = city_id
    if not values:
        return
    Database().session.query(District).filter(District.id == district_id).update(values)
    Database().session.commit()


def update_product_type(type_id: int, name: str) -> None:
    Database().session.query(ProductType).filter(ProductType.id == type_id).update({ProductType.name: name})
    Database().session.commit()


def update_product_metadata(
    item_name: str,
    product_type_id: int | None = None,
    city_id: int | None = None,
    district_id: int | None = None,
) -> None:
    session = Database().session
    metadata = session.query(ProductMetadata).filter(ProductMetadata.item_name == item_name).first()
    if metadata is None:
        metadata = ProductMetadata(
            item_name=item_name,
            product_type_id=product_type_id,
            city_id=city_id,
            district_id=district_id,
        )
        session.add(metadata)
    else:
        if product_type_id is not None or product_type_id is None:
            metadata.product_type_id = product_type_id
        if city_id is not None:
            metadata.city_id = city_id
            if district_id is not None:
                metadata.district_id = district_id
            elif metadata.district_id is not None:
                metadata.district_id = None
        elif district_id is not None:
            metadata.district_id = district_id
    session.commit()


def update_review_status(review_id: int, status: str, moderator_id: int | None = None) -> None:
    session = Database().session
    review = session.query(Review).filter(Review.id == review_id).first()
    if review is None:
        return
    review.status = status
    if moderator_id is not None:
        review.moderated_by = moderator_id
        review.moderated_at = datetime.datetime.utcnow().isoformat()
    session.commit()


def release_reservation(reservation_id: int) -> None:
    session = Database().session
    reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
    if reservation is None:
        return
    if reservation.status == 'active' and not reservation.is_infinity and reservation.item_value:
        session.add(
            ItemValues(
                name=reservation.item_name,
                value=reservation.item_value,
                is_infinity=False,
            )
        )
    reservation.status = 'released'
    reservation.released_at = datetime.datetime.utcnow().isoformat()
    session.commit()


def complete_reservation(reservation_id: int) -> None:
    session = Database().session
    reservation = session.query(Reservation).filter(Reservation.id == reservation_id).first()
    if reservation is None:
        return
    reservation.status = 'completed'
    reservation.released_at = datetime.datetime.utcnow().isoformat()
    session.commit()


def mark_reservation_completed_by_operation(operation_id: str | None) -> None:
    if not operation_id:
        return
    session = Database().session
    reservation = session.query(Reservation).filter(Reservation.operation_id == operation_id).first()
    if reservation:
        complete_reservation(reservation.id)


def release_reservation_by_operation(operation_id: str | None) -> None:
    if not operation_id:
        return
    session = Database().session
    reservation = session.query(Reservation).filter(Reservation.operation_id == operation_id).first()
    if reservation:
        release_reservation(reservation.id)


def update_manual_payment_status(payment_id: int, status: str) -> None:
    Database().session.query(ManualPayment).filter(ManualPayment.id == payment_id).update(
        {ManualPayment.status: status}
    )
    Database().session.commit()


def update_media_asset_title(asset_id: int, title: str | None = None, caption: str | None = None) -> None:
    values = {}
    if title is not None:
        values[MediaAsset.title] = title
    if caption is not None:
        values[MediaAsset.caption] = caption
    if not values:
        return
    Database().session.query(MediaAsset).filter(MediaAsset.id == asset_id).update(values)
    Database().session.commit()
