import os

from bot.database import Database
from bot.database.models import (
    Categories,
    City,
    District,
    Goods,
    ItemValues,
    MediaAsset,
    ProductMetadata,
    ProductType,
    PromoCode,
    Reseller,
    ResellerPrice,
    UnfinishedOperations,
    UserProfile,
)
from bot.utils.files import sanitize_name


def delete_item(item_name: str) -> None:
    session = Database().session
    values = session.query(ItemValues.value).filter(ItemValues.item_name == item_name).all()
    for val in values:
        if os.path.isfile(val[0]):
            os.remove(val[0])
    session.query(Goods).filter(Goods.name == item_name).delete()
    session.query(ItemValues).filter(ItemValues.item_name == item_name).delete()
    session.query(ProductMetadata).filter(ProductMetadata.item_name == item_name).delete()
    session.commit()
    folder = os.path.join('assets', 'uploads', sanitize_name(item_name))
    if os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)


def delete_only_items(item_name: str) -> None:
    session = Database().session
    values = session.query(ItemValues.value).filter(ItemValues.item_name == item_name).all()
    for val in values:
        if os.path.isfile(val[0]):
            os.remove(val[0])
    session.query(ItemValues).filter(ItemValues.item_name == item_name).delete()
    session.query(ProductMetadata).filter(ProductMetadata.item_name == item_name).delete()
    session.commit()
    folder = os.path.join('assets', 'uploads', sanitize_name(item_name))
    if os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)


def delete_category(category_name: str) -> None:
    session = Database().session
    subs = session.query(Categories.name).filter(Categories.parent_name == category_name).all()
    for sub in subs:
        delete_category(sub.name)
    goods = session.query(Goods.name).filter(Goods.category_name == category_name).all()
    for item in goods:
        delete_item(item.name)
    session.query(Categories).filter(Categories.name == category_name).delete()
    session.commit()


def finish_operation(operation_id: str) -> None:
    Database().session.query(UnfinishedOperations).filter(
        UnfinishedOperations.operation_id == operation_id
    ).delete()
    Database().session.commit()


def buy_item(item_id: str, infinity: bool = False) -> None:
    if not infinity:
        session = Database().session
        session.query(ItemValues).filter(ItemValues.id == item_id).delete()
        session.commit()


def delete_promocode(code: str) -> None:
    session = Database().session
    session.query(PromoCode).filter(PromoCode.code == code).delete()
    session.commit()


def delete_reseller(user_id: int) -> None:
    session = Database().session
    session.query(ResellerPrice).filter(ResellerPrice.reseller_id == user_id).delete()
    session.query(Reseller).filter(Reseller.user_id == user_id).delete()
    session.commit()


def delete_city(city_id: int) -> None:
    session = Database().session
    session.query(UserProfile).filter(UserProfile.city_id == city_id).update(
        {UserProfile.city_id: None, UserProfile.district_id: None}, synchronize_session=False
    )
    session.query(ProductMetadata).filter(ProductMetadata.city_id == city_id).update(
        {ProductMetadata.city_id: None, ProductMetadata.district_id: None}, synchronize_session=False
    )
    session.query(District).filter(District.city_id == city_id).delete()
    session.query(City).filter(City.id == city_id).delete()
    session.commit()


def delete_district(district_id: int) -> None:
    session = Database().session
    session.query(UserProfile).filter(UserProfile.district_id == district_id).update(
        {UserProfile.district_id: None}, synchronize_session=False
    )
    session.query(ProductMetadata).filter(ProductMetadata.district_id == district_id).update(
        {ProductMetadata.district_id: None}, synchronize_session=False
    )
    session.query(District).filter(District.id == district_id).delete()
    session.commit()


def delete_product_type(type_id: int) -> None:
    session = Database().session
    session.query(ProductMetadata).filter(ProductMetadata.product_type_id == type_id).update(
        {ProductMetadata.product_type_id: None}, synchronize_session=False
    )
    session.query(ProductType).filter(ProductType.id == type_id).delete()
    session.commit()


def delete_media_asset(asset_id: int) -> None:
    session = Database().session
    session.query(MediaAsset).filter(MediaAsset.id == asset_id).delete()
    session.commit()
