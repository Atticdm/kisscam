"""Обработчики команд бота."""
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.terms import AGREEMENT_SHORT, TERMS_OF_SERVICE, AGREEMENT_BUTTON_TEXT, DECLINE_BUTTON_TEXT, TERMS_VERSION
from services.terms_service import TermsService
from services.promo_service import PromoService, PromoCodeError

router = Router()
terms_service = TermsService()
promo_service = PromoService()


@router.callback_query(F.data == "agree_terms")
async def agree_terms_callback(callback: CallbackQuery):
    """Обработчик согласия с правилами."""
    user_id = callback.from_user.id
    
    # Сохраняем согласие в базе данных
    await terms_service.agree_to_terms(user_id)
    
    welcome_text = (
        "✅ Спасибо за согласие с правилами!\n\n"
        "👋 Привет! Я бот Kisscam!\n\n"
        "Я могу создавать видео, где люди целуются из ваших фотографий.\n\n"
        "📸 Как использовать:\n"
        "• Отправьте одну фотографию с парой или группой людей - они будут целоваться друг с другом\n"
        "• Отправьте две фотографии с людьми - они объединятся и будут целоваться\n\n"
        "Начните с отправки фотографии!\n\n"
        "📋 Правила: /terms\n"
        "❓ Помощь: /help"
    )
    
    await callback.message.edit_text(welcome_text)
    await callback.answer("Согласие принято!")


@router.callback_query(F.data == "decline_terms")
async def decline_terms_callback(callback: CallbackQuery):
    """Обработчик отказа от правил."""
    decline_text = (
        "❌ Вы не согласились с правилами использования.\n\n"
        "Для использования бота необходимо принять правила.\n\n"
        "Если передумаете, используйте команду /start"
    )
    await callback.message.edit_text(decline_text)
    await callback.answer("Для использования бота необходимо согласиться с правилами")


@router.callback_query(F.data == "show_full_terms")
async def show_full_terms_callback(callback: CallbackQuery):
    """Показывает полные правила в отдельном сообщении."""
    await callback.message.answer(TERMS_OF_SERVICE)
    
    # Показываем кнопки согласия снова
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=AGREEMENT_BUTTON_TEXT, callback_data="agree_terms"),
            InlineKeyboardButton(text=DECLINE_BUTTON_TEXT, callback_data="decline_terms")
        ]
    ])
    
    await callback.message.answer(
        "Прочитали правила? Подтвердите согласие:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    
    # Проверяем, согласился ли пользователь с текущей версией правил
    terms_info = await terms_service.get_terms_info(user_id)
    agreed = terms_info["agreed"]
    
    if agreed:
        # Пользователь уже согласился с текущей версией правил
        welcome_text = (
            "👋 Привет! Я бот Kisscam!\n\n"
            "Я могу создавать видео, где люди целуются из ваших фотографий.\n\n"
            "📸 Как использовать:\n"
            "• Отправьте одну фотографию с парой или группой людей - они будут целоваться друг с другом\n"
            "• Отправьте две фотографии с людьми - они объединятся и будут целоваться\n\n"
            "Начните с отправки фотографии!\n\n"
            "📋 Правила: /terms\n"
            "❓ Помощь: /help"
        )
        await message.answer(welcome_text)
    else:
        # Показываем соглашение и требуем подтверждения
        # Если правила обновились, сообщаем об этом
        if terms_info["terms_version"] is not None and terms_info["terms_version"] < TERMS_VERSION:
            update_notice = "\n⚠️ Правила были обновлены. Пожалуйста, ознакомьтесь с новыми правилами и подтвердите согласие.\n\n"
        else:
            update_notice = ""
        
        agreement_text = (
            "👋 Привет! Я бот Kisscam!\n\n"
            f"{update_notice}"
            f"{AGREEMENT_SHORT}\n\n"
            "Для использования бота необходимо согласиться с правилами."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=AGREEMENT_BUTTON_TEXT, callback_data="agree_terms"),
                InlineKeyboardButton(text=DECLINE_BUTTON_TEXT, callback_data="decline_terms")
            ],
            [
                InlineKeyboardButton(text="📋 Полные правила", callback_data="show_full_terms")
            ]
        ])
        
        await message.answer(agreement_text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text = (
        "📖 Помощь по использованию бота Kisscam\n\n"
        "🎬 Что я умею:\n"
        "• Создаю короткие видео (3-5 секунд) с целующимися людьми\n"
        "• Работаю с одной или двумя фотографиями\n\n"
        "📸 Инструкции:\n"
        "1. Отправьте фотографию с людьми\n"
        "2. Если хотите объединить людей с разных фото - отправьте вторую фотографию\n"
        "3. Дождитесь обработки (обычно 30-60 секунд)\n"
        "4. Получите готовое видео!\n\n"
        "⚠️ Ограничения:\n"
        "• Максимальный размер файла: 10 МБ\n"
        "• Поддерживаемые форматы: JPG, PNG\n"
        "• Лимит: 10 запросов в час\n\n"
        "📋 Правила использования: /terms\n\n"
        "Если возникли проблемы, попробуйте отправить фотографию заново."
    )
    await message.answer(help_text)


@router.message(Command("terms"))
async def cmd_terms(message: Message):
    """Обработчик команды /terms - показывает полные правила."""
    await message.answer(TERMS_OF_SERVICE)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Обработчик команды /menu - показывает меню команд."""
    menu_text = (
        "📋 Меню команд бота Kisscam:\n\n"
        "🚀 Основные команды:\n"
        "• /start - Запустить бота\n"
        "• /help - Помощь по использованию\n"
        "• /menu - Показать это меню\n\n"
        "💰 Токены и покупки:\n"
        "• /tokens - Проверить баланс токенов\n"
        "• /buy - Купить токены\n"
        "• /promo - Использовать промокод\n\n"
        "📋 Информация:\n"
        "• /terms - Правила использования\n\n"
        "📸 Использование:\n"
        "Просто отправьте фотографию с людьми, и я создам видео с целующимися персонажами!\n"
        "Можно отправить одну или две фотографии."
    )
    
    await message.answer(menu_text)


@router.message(Command("promo"))
async def cmd_promo(message: Message):
    """Обработчик команды /promo - применение промокода."""
    user_id = message.from_user.id
    command_parts = message.text.split(maxsplit=1)
    
    if len(command_parts) < 2:
        await message.answer(
            "🎁 Использование промокода\n\n"
            "Используйте команду в формате:\n"
            "/promo <код>\n\n"
            "Пример:\n"
            "/promo scam10"
        )
        return
    
    code = command_parts[1].strip()
    
    try:
        result = await promo_service.apply_promo_code(user_id, code)
        
        success_msg = (
            f"✅ Промокод успешно применен!\n\n"
            f"🎁 Добавлено генераций: {result['generations_added']}\n"
            f"📊 Всего промокодных генераций: {result['total_promo_generations']}\n\n"
            f"Теперь вы можете использовать эти генерации для создания видео!"
        )
        
        await message.answer(success_msg)
        
    except PromoCodeError as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    except Exception as e:
        logger.error(f"Error applying promo code: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при применении промокода.\n"
            "Попробуйте позже или проверьте правильность кода."
        )
