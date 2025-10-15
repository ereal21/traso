import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    BigInteger,
    ForeignKey,
    Text,
    Boolean,
    VARCHAR,
    inspect,
)
from bot.database.main import Database
from sqlalchemy.orm import relationship


class Permission:
    USE = 1
    BROADCAST = 2
    SETTINGS_MANAGE = 4
    USERS_MANAGE = 8
    SHOP_MANAGE = 16
    ADMINS_MANAGE = 32
    OWN = 64
    ASSIGN_PHOTOS = 128


class Role(Database.BASE):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    default = Column(Boolean, default=False, index=True)
    permissions = Column(Integer)
    users = relationship('User', backref='role', lazy='dynamic')

    def __init__(self, name: str, permissions=None, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0
        self.name = name
        self.permissions = permissions

    @staticmethod
    def insert_roles():
        roles = {
            'USER': [Permission.USE],
            'ADMIN': [Permission.USE, Permission.BROADCAST,
                      Permission.SETTINGS_MANAGE, Permission.USERS_MANAGE,
                      Permission.SHOP_MANAGE, Permission.ASSIGN_PHOTOS],
            'OWNER': [Permission.USE, Permission.BROADCAST,
                      Permission.SETTINGS_MANAGE, Permission.USERS_MANAGE,
                      Permission.SHOP_MANAGE, Permission.ADMINS_MANAGE,
                      Permission.OWN, Permission.ASSIGN_PHOTOS],
            'ASSISTANT': [Permission.USE, Permission.ASSIGN_PHOTOS],
        }
        default_role = 'USER'
        for r in roles:
            role = Database().session.query(Role).filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            Database().session.add(role)
        Database().session.commit()

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def __repr__(self):
        return '<Role %r>' % self.name


class User(Database.BASE):
    __tablename__ = 'users'
    telegram_id = Column(BigInteger, nullable=False, unique=True, primary_key=True)
    username = Column(String(64), nullable=True)
    role_id = Column(Integer, ForeignKey('roles.id'), default=1)
    balance = Column(BigInteger, nullable=False, default=0)
    lottery_tickets = Column(Integer, nullable=False, default=0)
    purchase_streak = Column(Integer, nullable=False, default=0)
    last_purchase_date = Column(VARCHAR, nullable=True)
    streak_discount = Column(Boolean, nullable=False, default=False)
    language = Column(String(5), nullable=True)
    referral_id = Column(BigInteger, nullable=True)
    registration_date = Column(VARCHAR, nullable=False)
    user_operations = relationship("Operations", back_populates="user_telegram_id")
    user_unfinished_operations = relationship("UnfinishedOperations", back_populates="user_telegram_id")
    user_goods = relationship("BoughtGoods", back_populates="user_telegram_id")
    profile = relationship("UserProfile", back_populates="user", uselist=False)

    def __init__(self, telegram_id: int, registration_date: datetime.datetime, balance: int = 0,
                 referral_id=None, role_id: int = 1, language: str | None = None,
                 username: str | None = None, purchase_streak: int = 0,
                 last_purchase_date: str | None = None, streak_discount: bool = False):
        self.telegram_id = telegram_id
        self.username = username
        self.role_id = role_id
        self.balance = balance
        self.referral_id = referral_id
        self.registration_date = registration_date
        self.language = language
        self.purchase_streak = purchase_streak
        self.last_purchase_date = last_purchase_date
        self.streak_discount = streak_discount


class Categories(Database.BASE):
    __tablename__ = 'categories'
    name = Column(String(100), primary_key=True, unique=True, nullable=False)
    parent_name = Column(String(100), nullable=True)
    allow_discounts = Column(Boolean, nullable=False, default=True)
    allow_referral_rewards = Column(Boolean, nullable=False, default=True)
    item = relationship("Goods", back_populates="category")

    def __init__(
        self,
        name: str,
        parent_name: str | None = None,
        allow_discounts: bool = True,
        allow_referral_rewards: bool = True,
    ):
        self.name = name
        self.parent_name = parent_name
        self.allow_discounts = allow_discounts
        self.allow_referral_rewards = allow_referral_rewards


class Goods(Database.BASE):
    __tablename__ = 'goods'
    name = Column(String(100), nullable=False, unique=True, primary_key=True)
    price = Column(BigInteger, nullable=False)
    description = Column(Text, nullable=False)
    delivery_description = Column(Text, nullable=True)
    category_name = Column(String(100), ForeignKey('categories.name'), nullable=False)
    category = relationship("Categories", back_populates="item")
    values = relationship("ItemValues", back_populates="item")

    def __init__(self, name: str, price: int, description: str, category_name: str,
                 delivery_description: str | None = None):
        self.name = name
        self.price = price
        self.description = description
        self.delivery_description = delivery_description
        self.category_name = category_name


class ItemValues(Database.BASE):
    __tablename__ = 'item_values'
    id = Column(Integer, nullable=False, primary_key=True)
    item_name = Column(String(100), ForeignKey('goods.name'), nullable=False)
    value = Column(Text, nullable=True)
    is_infinity = Column(Boolean, nullable=False)
    item = relationship("Goods", back_populates="values")

    def __init__(self, name: str, value: str, is_infinity: bool):
        self.item_name = name
        self.value = value
        self.is_infinity = is_infinity


class BoughtGoods(Database.BASE):
    __tablename__ = 'bought_goods'
    id = Column(Integer, nullable=False, primary_key=True)
    item_name = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    price = Column(BigInteger, nullable=False)
    buyer_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    bought_datetime = Column(VARCHAR, nullable=False)
    unique_id = Column(BigInteger, nullable=False, unique=True)
    user_telegram_id = relationship("User", back_populates="user_goods")

    def __init__(self, name: str, value: str, price: int, bought_datetime: str, unique_id,
                 buyer_id: int = 0):
        self.item_name = name
        self.value = value
        self.price = price
        self.buyer_id = buyer_id
        self.bought_datetime = bought_datetime
        self.unique_id = unique_id


class Operations(Database.BASE):
    __tablename__ = 'operations'
    id = Column(Integer, nullable=False, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    operation_value = Column(BigInteger, nullable=False)
    operation_time = Column(VARCHAR, nullable=False)
    user_telegram_id = relationship("User", back_populates="user_operations")

    def __init__(self, user_id: int, operation_value: int, operation_time: str):
        self.user_id = user_id
        self.operation_value = operation_value
        self.operation_time = operation_time


class UnfinishedOperations(Database.BASE):
    __tablename__ = 'unfinished_operations'
    id = Column(Integer, nullable=False, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    operation_value = Column(BigInteger, nullable=False)
    operation_id = Column(String(500), nullable=False)
    message_id = Column(BigInteger, nullable=True)
    user_telegram_id = relationship("User", back_populates="user_unfinished_operations")

    def __init__(self, user_id: int, operation_value: int, operation_id: str, message_id: int | None = None):
        self.user_id = user_id
        self.operation_value = operation_value
        self.operation_id = operation_id
        self.message_id = message_id


class Achievement(Database.BASE):
    __tablename__ = 'achievements'
    code = Column(String(50), primary_key=True, unique=True)

    def __init__(self, code: str):
        self.code = code


class UserAchievement(Database.BASE):
    __tablename__ = 'user_achievements'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    achievement_code = Column(String(50), ForeignKey('achievements.code'), nullable=False)
    achieved_at = Column(VARCHAR, nullable=False)

    def __init__(self, user_id: int, achievement_code: str, achieved_at: str):
        self.user_id = user_id
        self.achievement_code = achievement_code
        self.achieved_at = achieved_at


class PromoCode(Database.BASE):
    __tablename__ = 'promo_codes'
    code = Column(String(50), primary_key=True, unique=True)
    discount = Column(Integer, nullable=False)
    expires_at = Column(VARCHAR, nullable=True)
    active = Column(Boolean, default=True)

    def __init__(self, code: str, discount: int, expires_at: str | None = None, active: bool = True):
        self.code = code
        self.discount = discount
        self.expires_at = expires_at
        self.active = active


class Reseller(Database.BASE):
    __tablename__ = 'resellers'
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), primary_key=True, unique=True)

    def __init__(self, user_id: int):
        self.user_id = user_id


class ResellerPrice(Database.BASE):
    __tablename__ = 'reseller_prices'
    id = Column(Integer, primary_key=True)
    reseller_id = Column(BigInteger, ForeignKey('resellers.user_id'), nullable=True)
    item_name = Column(String(100), ForeignKey('goods.name'), nullable=False)
    price = Column(BigInteger, nullable=False)

    def __init__(self, reseller_id: int | None, item_name: str, price: int):
        self.reseller_id = reseller_id
        self.item_name = item_name
        self.price = price


class StockNotification(Database.BASE):
    __tablename__ = 'stock_notifications'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    item_name = Column(String(100), ForeignKey('goods.name'), nullable=False)

    def __init__(self, user_id: int, item_name: str):
        self.user_id = user_id
        self.item_name = item_name


class City(Database.BASE):
    __tablename__ = 'cities'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    region = Column(String(120), nullable=True)
    districts = relationship("District", back_populates="city", cascade="all, delete-orphan")

    def __init__(self, name: str, region: str | None = None):
        self.name = name
        self.region = region


class District(Database.BASE):
    __tablename__ = 'districts'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    city_id = Column(Integer, ForeignKey('cities.id'), nullable=False)
    city = relationship("City", back_populates="districts")

    def __init__(self, name: str, city_id: int):
        self.name = name
        self.city_id = city_id


class ProductType(Database.BASE):
    __tablename__ = 'product_types'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class ProductMetadata(Database.BASE):
    __tablename__ = 'product_metadata'
    item_name = Column(String(100), ForeignKey('goods.name'), primary_key=True)
    product_type_id = Column(Integer, ForeignKey('product_types.id'), nullable=True)
    city_id = Column(Integer, ForeignKey('cities.id'), nullable=True)
    district_id = Column(Integer, ForeignKey('districts.id'), nullable=True)
    product_type = relationship("ProductType")
    city = relationship("City")
    district = relationship("District")

    def __init__(
        self,
        item_name: str,
        product_type_id: int | None = None,
        city_id: int | None = None,
        district_id: int | None = None,
    ):
        self.item_name = item_name
        self.product_type_id = product_type_id
        self.city_id = city_id
        self.district_id = district_id


class UserProfile(Database.BASE):
    __tablename__ = 'user_profiles'
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), primary_key=True)
    city_id = Column(Integer, ForeignKey('cities.id'), nullable=True)
    district_id = Column(Integer, ForeignKey('districts.id'), nullable=True)
    status = Column(String(32), nullable=False, default='active')
    last_activity = Column(VARCHAR, nullable=True)
    city = relationship("City")
    district = relationship("District")
    user = relationship("User", back_populates="profile")

    def __init__(
        self,
        user_id: int,
        city_id: int | None = None,
        district_id: int | None = None,
        status: str = 'active',
        last_activity: str | None = None,
    ):
        self.user_id = user_id
        self.city_id = city_id
        self.district_id = district_id
        self.status = status
        self.last_activity = last_activity


class Review(Database.BASE):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    item_name = Column(String(120), nullable=True)
    service_rating = Column(Integer, nullable=False)
    product_rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default='pending')
    created_at = Column(VARCHAR, nullable=False)
    moderated_at = Column(VARCHAR, nullable=True)
    moderated_by = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=True)
    user = relationship('User', foreign_keys=[user_id])
    moderator = relationship('User', foreign_keys=[moderated_by], uselist=False)

    def __init__(
        self,
        user_id: int,
        item_name: str | None,
        service_rating: int,
        product_rating: int,
        comment: str | None,
        status: str = 'pending',
        created_at: str | None = None,
    ):
        self.user_id = user_id
        self.item_name = item_name
        self.service_rating = service_rating
        self.product_rating = product_rating
        self.comment = comment
        self.status = status
        self.created_at = created_at or datetime.datetime.utcnow().isoformat()


class Reservation(Database.BASE):
    __tablename__ = 'reservations'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    item_name = Column(String(100), nullable=False)
    item_value = Column(Text, nullable=True)
    is_infinity = Column(Boolean, nullable=False, default=False)
    operation_id = Column(String(255), nullable=True, unique=True)
    status = Column(String(16), nullable=False, default='active')
    reserved_at = Column(VARCHAR, nullable=False)
    expires_at = Column(VARCHAR, nullable=True)
    released_at = Column(VARCHAR, nullable=True)
    user = relationship('User')

    def __init__(
        self,
        user_id: int,
        item_name: str,
        item_value: str | None,
        is_infinity: bool,
        operation_id: str | None,
        expires_at: str | None = None,
        status: str = 'active',
    ):
        self.user_id = user_id
        self.item_name = item_name
        self.item_value = item_value
        self.is_infinity = is_infinity
        self.operation_id = operation_id
        self.expires_at = expires_at
        self.status = status
        self.reserved_at = datetime.datetime.utcnow().isoformat()


class ManualPayment(Database.BASE):
    __tablename__ = 'manual_payments'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    amount = Column(BigInteger, nullable=False)
    currency = Column(String(16), nullable=False, default='EUR')
    note = Column(Text, nullable=True)
    created_at = Column(VARCHAR, nullable=False)
    created_by = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    status = Column(String(16), nullable=False, default='completed')
    user = relationship('User', foreign_keys=[user_id])
    admin = relationship('User', foreign_keys=[created_by])

    def __init__(
        self,
        user_id: int,
        amount: int,
        currency: str,
        created_by: int,
        note: str | None = None,
        status: str = 'completed',
    ):
        self.user_id = user_id
        self.amount = amount
        self.currency = currency
        self.note = note
        self.status = status
        self.created_by = created_by
        self.created_at = datetime.datetime.utcnow().isoformat()


class MediaAsset(Database.BASE):
    __tablename__ = 'media_assets'
    id = Column(Integer, primary_key=True)
    file_id = Column(String(255), nullable=False)
    file_unique_id = Column(String(255), nullable=True)
    file_type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=True)
    caption = Column(Text, nullable=True)
    created_by = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    created_at = Column(VARCHAR, nullable=False)
    user = relationship('User')

    def __init__(
        self,
        file_id: str,
        file_type: str,
        created_by: int,
        caption: str | None = None,
        title: str | None = None,
        file_unique_id: str | None = None,
    ):
        self.file_id = file_id
        self.file_type = file_type
        self.caption = caption
        self.title = title
        self.created_by = created_by
        self.file_unique_id = file_unique_id
        self.created_at = datetime.datetime.utcnow().isoformat()


def register_models():
    engine = Database().engine
    inspector = inspect(engine)
    if 'reseller_prices' in inspector.get_table_names():
        for column in inspector.get_columns('reseller_prices'):
            if column['name'] == 'reseller_id' and not column['nullable']:
                ResellerPrice.__table__.drop(engine)
                break
    Database.BASE.metadata.create_all(engine)
    Role.insert_roles()
