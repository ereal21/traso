import datetime
import random
import sqlalchemy.exc

from bot.database import Database
from bot.database.models import (
    User,
    ItemValues,
    Goods,
    Categories,
    BoughtGoods,
    Operations,
    UnfinishedOperations,
    PromoCode,
    UserAchievement,
    StockNotification,
    Reseller,
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
from bot.database.methods.read import get_role_id_by_name
from bot.logger_mesh import logger


def _ensure_profile(session, telegram_id: int) -> None:
    if session.query(UserProfile).filter(UserProfile.user_id == telegram_id).first() is None:
        session.add(UserProfile(user_id=telegram_id))
        session.commit()


def ensure_owner_account(owner_id_value) -> None:
    """Ensure the OWNER role is assigned to the account declared in the environment."""

    if not owner_id_value:
        logger.warning("ensure_owner_account: OWNER_ID missing; cannot sync owner role.")
        return

    try:
        owner_id = int(owner_id_value)
    except (TypeError, ValueError):
        logger.error("ensure_owner_account: OWNER_ID=%r is not a valid integer.", owner_id_value)
        return

    session = Database().session
    owner_role_id = get_role_id_by_name('OWNER')
    if owner_role_id is None:
        logger.error("ensure_owner_account: OWNER role is not present in the database.")
        return

    admin_role_id = (
        get_role_id_by_name('ADMIN')
        or get_role_id_by_name('USER')
        or 1
    )

    updates_required = False

    # Demote any legacy owner accounts that do not match the configured OWNER_ID.
    legacy_owners = session.query(User).filter(User.role_id == owner_role_id, User.telegram_id != owner_id).all()
    for legacy in legacy_owners:
        legacy.role_id = admin_role_id
        updates_required = True
        logger.info("ensure_owner_account: Demoted legacy owner %s to role %s.", legacy.telegram_id, admin_role_id)

    owner_user = session.query(User).filter(User.telegram_id == owner_id).first()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if owner_user is None:
        owner_user = User(
            telegram_id=owner_id,
            role_id=owner_role_id,
            registration_date=now,
            referral_id=None,
            language=None,
            username=None,
        )
        session.add(owner_user)
        updates_required = True
        logger.info("ensure_owner_account: Created OWNER account for %s.", owner_id)
    elif owner_user.role_id != owner_role_id:
        owner_user.role_id = owner_role_id
        updates_required = True
        logger.info("ensure_owner_account: Updated %s to OWNER role.", owner_id)

    if updates_required:
        session.commit()

    _ensure_profile(session, owner_id)
    logger.info("ensure_owner_account: OWNER_ID synchronized to %s.", owner_id)


def create_user(
    telegram_id: int,
    registration_date,
    referral_id,
    role: int = 1,
    language: str | None = None,
    username: str | None = None,
) -> None:
    session = Database().session
    try:
        user = session.query(User).filter(User.telegram_id == telegram_id).one()
        if user.username != username:
            user.username = username
            session.commit()
        _ensure_profile(session, telegram_id)
    except sqlalchemy.exc.NoResultFound:
        if referral_id != '':
            session.add(
                User(
                    telegram_id=telegram_id,
                    role_id=role,
                    registration_date=registration_date,
                    referral_id=referral_id,
                    language=language,
                    username=username,
                )
            )
            session.commit()
        else:
            session.add(
                User(
                    telegram_id=telegram_id,
                    role_id=role,
                    registration_date=registration_date,
                    referral_id=None,
                    language=language,
                    username=username,
                )
            )
            session.commit()
        _ensure_profile(session, telegram_id)


def create_item(item_name: str, item_description: str, item_price: int, category_name: str,
                delivery_description: str | None = None) -> None:
    session = Database().session
    session.add(
        Goods(name=item_name, description=item_description, price=item_price,
              category_name=category_name, delivery_description=delivery_description))
    session.commit()


def add_values_to_item(item_name: str, value: str, is_infinity: bool) -> None:
    session = Database().session
    if is_infinity is False:
        session.add(
            ItemValues(name=item_name, value=value, is_infinity=False))
    else:
        session.add(
            ItemValues(name=item_name, value=value, is_infinity=True))
    session.commit()


def create_category(category_name: str, parent: str | None = None,
                    allow_discounts: bool = True, allow_referral_rewards: bool = True) -> None:
    session = Database().session
    session.add(
        Categories(
            name=category_name,
            parent_name=parent,
            allow_discounts=allow_discounts,
            allow_referral_rewards=allow_referral_rewards,
        )
    )
    session.commit()


def create_operation(user_id: int, value: int, operation_time: str) -> None:
    session = Database().session
    session.add(
        Operations(user_id=user_id, operation_value=value, operation_time=operation_time))
    session.commit()


def start_operation(user_id: int, value: int, operation_id: str, message_id: int | None = None) -> None:
    session = Database().session
    session.add(
        UnfinishedOperations(user_id=user_id, operation_value=value, operation_id=operation_id, message_id=message_id))
    session.commit()


def add_bought_item(item_name: str, value: str, price: int, buyer_id: int,
                    bought_time: str) -> int:
    session = Database().session
    unique_id = random.randint(1000000000, 9999999999)
    session.add(
        BoughtGoods(name=item_name, value=value, price=price, buyer_id=buyer_id, bought_datetime=bought_time,
                    unique_id=str(unique_id)))
    session.commit()
    return unique_id


def create_promocode(code: str, discount: int, expires_at: str | None) -> None:
    session = Database().session
    session.add(PromoCode(code=code, discount=discount, expires_at=expires_at, active=True))
    session.commit()


def grant_achievement(user_id: int, code: str, achieved_at: str) -> None:
    session = Database().session
    session.add(UserAchievement(user_id=user_id, achievement_code=code, achieved_at=achieved_at))
    session.commit()


def add_stock_notification(user_id: int, item_name: str) -> None:
    session = Database().session
    session.add(StockNotification(user_id=user_id, item_name=item_name))
    session.commit()


def create_reseller(user_id: int) -> None:
    session = Database().session
    session.add(Reseller(user_id=user_id))
    session.commit()


def create_city(name: str, region: str | None = None) -> int:
    session = Database().session
    city = City(name=name, region=region)
    session.add(city)
    session.commit()
    return city.id


def create_district(city_id: int, name: str) -> int:
    session = Database().session
    district = District(name=name, city_id=city_id)
    session.add(district)
    session.commit()
    return district.id


def create_product_type(name: str) -> int:
    session = Database().session
    product_type = ProductType(name=name)
    session.add(product_type)
    session.commit()
    return product_type.id


def create_or_update_product_metadata(
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
        metadata.product_type_id = product_type_id
        metadata.city_id = city_id
        metadata.district_id = district_id
    session.commit()


def create_review_entry(
    user_id: int,
    item_name: str | None,
    service_rating: int,
    product_rating: int,
    comment: str | None = None,
) -> int:
    session = Database().session
    review = Review(
        user_id=user_id,
        item_name=item_name,
        service_rating=service_rating,
        product_rating=product_rating,
        comment=comment,
    )
    session.add(review)
    session.commit()
    return review.id


def create_reservation_record(
    user_id: int,
    item_name: str,
    item_value: str | None,
    is_infinity: bool,
    operation_id: str | None,
    expires_at: str | None = None,
) -> int:
    session = Database().session
    reservation = Reservation(
        user_id=user_id,
        item_name=item_name,
        item_value=item_value,
        is_infinity=is_infinity,
        operation_id=operation_id,
        expires_at=expires_at,
    )
    session.add(reservation)
    session.commit()
    return reservation.id


def create_manual_payment_record(
    user_id: int,
    amount: int,
    currency: str,
    created_by: int,
    note: str | None = None,
) -> int:
    session = Database().session
    payment = ManualPayment(
        user_id=user_id,
        amount=amount,
        currency=currency,
        created_by=created_by,
        note=note,
    )
    session.add(payment)
    session.commit()
    return payment.id


def create_media_asset_record(
    file_id: str,
    file_type: str,
    created_by: int,
    caption: str | None = None,
    title: str | None = None,
    file_unique_id: str | None = None,
) -> int:
    session = Database().session
    asset = MediaAsset(
        file_id=file_id,
        file_type=file_type,
        created_by=created_by,
        caption=caption,
        title=title,
        file_unique_id=file_unique_id,
    )
    session.add(asset)
    session.commit()
    return asset.id
