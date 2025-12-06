"""Обработчики платежей и покупки токенов."""
from aiogram import Router, F, Bot
from aiogram.types import Message, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, PreCheckoutQuery
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
    
    if balance['free_remaining'] > 0:
        balance_text += f"✅ Осталось бесплатных генераций: {balance['free_remaining']}\n"
    else:
        balance_text += f"❌ Бесплатные генерации использованы ({balance['free_used']}/3)\n"
    
    promo_generations = balance.get('promo_generations', 0) or 0
    if promo_generations > 0:
        balance_text += f"🎁 Промокодных генераций: {promo_generations}\n"
    
    balance_text += "\n"
    
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
            # Для Telegram Stars не нужен reply_markup - кнопка оплаты добавляется автоматически
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


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """
    Обработчик предварительной проверки платежа.
    Обязателен для Telegram Stars - без него платежи не проходят.
    """
    try:
        # Проверяем payload
        payload = pre_checkout_query.invoice_payload
        payload_parts = payload.split("_")
        
        if len(payload_parts) >= 2 and payload_parts[0] == "tokens":
            package_id = payload_parts[1]
            package = TOKEN_PACKAGES.get(package_id)
            
            if package:
                # Проверяем, что сумма совпадает
                total_amount = pre_checkout_query.total_amount
                expected_amount = package["stars"]
                
                if total_amount == expected_amount:
                    # Подтверждаем платеж
                    await bot.answer_pre_checkout_query(
                        pre_checkout_query_id=pre_checkout_query.id,
                        ok=True
                    )
                    logger.info(
                        f"Pre-checkout approved for user {pre_checkout_query.from_user.id}, "
                        f"package {package_id}, amount {total_amount}"
                    )
                else:
                    # Отклоняем если сумма не совпадает
                    await bot.answer_pre_checkout_query(
                        pre_checkout_query_id=pre_checkout_query.id,
                        ok=False,
                        error_message=f"Неверная сумма платежа. Ожидается {expected_amount} Stars."
                    )
                    logger.warning(
                        f"Pre-checkout rejected: amount mismatch. "
                        f"Expected {expected_amount}, got {total_amount}"
                    )
            else:
                # Отклоняем если пакет не найден
                await bot.answer_pre_checkout_query(
                    pre_checkout_query_id=pre_checkout_query.id,
                    ok=False,
                    error_message="Неверный пакет токенов"
                )
                logger.error(f"Invalid package_id in pre-checkout: {package_id}")
        else:
            # Отклоняем если payload неверный
            await bot.answer_pre_checkout_query(
                pre_checkout_query_id=pre_checkout_query.id,
                ok=False,
                error_message="Неверный формат платежа"
            )
            logger.error(f"Invalid payload in pre-checkout: {payload}")
            
    except Exception as e:
        logger.error(f"Error in pre-checkout handler: {e}", exc_info=True)
        # Отклоняем при ошибке
        try:
            await bot.answer_pre_checkout_query(
                pre_checkout_query_id=pre_checkout_query.id,
                ok=False,
                error_message="Произошла ошибка при обработке платежа"
            )
        except Exception:
            pass


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

