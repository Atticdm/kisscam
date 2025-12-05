"""Обработчики команд бота."""
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.terms import AGREEMENT_SHORT, TERMS_OF_SERVICE, AGREEMENT_BUTTON_TEXT, DECLINE_BUTTON_TEXT

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    
    # Проверяем, согласился ли пользователь уже
    user_data = await state.get_data()
    agreed = user_data.get("terms_agreed", False)
    
    if agreed:
        # Пользователь уже согласился, показываем обычное приветствие
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
        agreement_text = (
            "👋 Привет! Я бот Kisscam!\n\n"
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
