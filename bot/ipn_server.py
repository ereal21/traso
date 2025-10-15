from flask import Flask, request, abort
import datetime
import hmac
import hashlib
import asyncio
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.localization import t

from bot.misc import EnvKeys, TgConfig
from bot.database import Database
from bot.database.models.main import UnfinishedOperations
from bot.database.methods import (
    finish_operation,
    create_operation,
    update_balance,
    get_user_referral,
    get_user_language,
)
from bot.logger_mesh import logger

app = Flask(__name__)


def verify_signature(data: bytes, signature: str | None) -> bool:
    if not EnvKeys.NOWPAYMENTS_IPN_SECRET:
        return True
    if not signature:
        return False
    calc = hmac.new(
        EnvKeys.NOWPAYMENTS_IPN_SECRET.encode(),
        data,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(calc, signature)


@app.route("/nowpayments-ipn", methods=["POST"])
@app.route("/", methods=["POST"])  # fallback if IPN path omitted
def nowpayments_ipn():
    if not verify_signature(request.data, request.headers.get("x-nowpayments-sig")):
        abort(400)

    # try to parse JSON regardless of Content-Type header
    data = request.get_json(force=True, silent=True) or {}
    payment_id = str(data.get("payment_id"))
    status = data.get("payment_status")
    if not payment_id or not status:
        return "", 400

    if status in ("finished", "confirmed", "sending", "paid", "partially_paid"):
        session = Database().session
        record = (
            session.query(UnfinishedOperations)
            .filter(UnfinishedOperations.operation_id == payment_id)
            .first()
        )
        if record:
            value = record.operation_value
            user_id = record.user_id
            message_id = record.message_id
            finish_operation(payment_id)
            formatted_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            create_operation(user_id, value, formatted_time)
            update_balance(user_id, value)

            # Referral bonuses apply only to purchases, not balance top-ups

            logger.info(
                "NOWPayments IPN confirmed payment %s for user %s", payment_id, user_id
            )

            # notify user and delete invoice
            bot = Bot(token=EnvKeys.TOKEN, parse_mode="HTML")
            lang = get_user_language(user_id) or 'en'
            markup = InlineKeyboardMarkup().add(
                InlineKeyboardButton(t(lang, 'back_home'), callback_data='home_menu')
            )
            asyncio.run(bot.delete_message(chat_id=user_id, message_id=message_id))
            asyncio.run(
                bot.send_message(
                    chat_id=user_id,
                    text=t(lang, 'payment_successful', amount=value),
                    reply_markup=markup,
                )
            )
    return "", 200
