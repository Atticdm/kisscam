"""Обработчики платежей и покупки токенов."""
from aiogram import Router, F, Bot
from aiogram.types import Message, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from services.token_service import TokenService, TOKEN_PACKAGES
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = Router()
token_service = TokenService()


@router.message(Command("tokens"))
async def cmd_tokens(message: Message):
    """Показывает баланс токенов и варианты покупки."""
    user_id = message.from_user.id
    balance = await token_service.get_balance(user_id)
    
    balance_text = (
        f"💰 Ваш баланс токенов:\n\n"
        f"🎫 Токенов: {balance['tokens']}\n"
    )
    
    if balance['free_available']:
        balance_text += "✅ У вас есть 1 бесплатная генерация\n\n"
    else:
        balance_text += "❌ Бесплатная генерация использована\n\n"
    
    balance_text += (
        "💳 Купить токены:\n\n"
        f"• 10 токенов = 200 ⭐ Stars\n"
        f"• 50 токенов = 950 ⭐ Stars\n"
        f"• 100 токенов = 1800 ⭐ Stars\n\n"
        "Используйте команду /buy для покупки токенов"
    )
    
    await message.answer(balance_text)


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    """Показывает варианты покупки токенов."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"10 токенов - 200 ⭐",
                callback_data="buy_tokens_10"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"50 токенов - 950 ⭐",
                callback_data="buy_tokens_50"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"100 токенов - 1800 ⭐",
                callback_data="buy_tokens_100"
            )
        ]
    ])
    
    buy_text = (
        "💳 Выберите пакет токенов для покупки:\n\n"
        "После выбора вы будете перенаправлены на оплату через Telegram Stars."
    )
    
    await message.answer(buy_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("buy_tokens_"))
async def buy_tokens_callback(callback: CallbackQuery, bot: Bot):
    """Обработчик выбора пакета токенов."""
    package_id = callback.data.split("_")[-1]
    package = TOKEN_PACKAGES.get(package_id)
    
    if not package:
        await callback.answer("Неверный пакет", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    # Создаем инвойс для оплаты через Telegram Stars
    try:
        # Используем Telegram Stars для оплаты
        # В aiogram 3.x для Stars используется метод send_invoice с параметром currency="XTR"
        prices = [LabeledPrice(label=package["name"], amount=package["stars"])]
        
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"Покупка {package['name']}",
            description=f"Покупка {package['tokens']} токенов для генерации видео",
            payload=f"tokens_{package_id}_{user_id}",
            provider_token="",  # Для Stars не нужен provider_token
            currency="XTR",  # XTR - это Telegram Stars
            prices=prices,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Оплатить",
                        pay=True
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data="cancel_payment"
                    )
                ]
            ])
        )
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Error creating invoice: {e}", exc_info=True)
        await callback.answer("Ошибка при создании платежа", show_alert=True)


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_callback(callback):
    """Обработчик отмены платежа."""
    await callback.message.delete()
    await callback.answer("Платеж отменен")


@router.message(F.content_type == "successful_payment")
async def successful_payment(message: Message):
    """Обработчик успешной оплаты."""
    payment = message.successful_payment
    user_id = message.from_user.id
    
    # Извлекаем информацию о пакете из payload
    # Формат: tokens_{package_id}_{user_id}
    payload_parts = payment.invoice_payload.split("_")
    
    if len(payload_parts) >= 2 and payload_parts[0] == "tokens":
        package_id = payload_parts[1]
        package = TOKEN_PACKAGES.get(package_id)
        
        if package:
            # Добавляем токены пользователю
            await token_service.add_tokens(user_id, package["tokens"])
            
            balance = await token_service.get_balance(user_id)
            
            success_text = (
                f"✅ Оплата успешна!\n\n"
                f"🎫 Вам добавлено {package['tokens']} токенов\n"
                f"💰 Ваш баланс: {balance['tokens']} токенов\n\n"
                f"Теперь вы можете генерировать видео!"
            )
            
            await message.answer(success_text)
            logger.info(f"User {user_id} purchased {package['tokens']} tokens")
        else:
            await message.answer("❌ Ошибка: неверный пакет токенов")
            logger.error(f"Invalid package_id in payment: {package_id}")
    else:
        await message.answer("❌ Ошибка при обработке платежа")
        logger.error(f"Invalid payment payload: {payment.invoice_payload}")

