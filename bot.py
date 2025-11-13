"""Telegram bot skeleton for a consultation assistant."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Final

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ConsultationKnowledgeBase:
    """Container for reusable responses that you can easily extend later."""

    greeting_template: str = (
        "👋 Привет, {name}! Я помогу разобраться с вопросами по нашему продукту."
    )
    default_response: str = (
        "Пока у меня нет ответа на этот вопрос. Скоро я научусь, а пока обращайся"
        " к оператору или уточни запрос."
    )
    exact_matches: dict[str, str] = field(
        default_factory=lambda: {
            "цены": "Наши базовые тарифы начинаются от 990 ₽ в месяц."
            " Напиши, если нужна подробная смета!",
            "как начать": "Чтобы начать, зарегистрируйся на сайте и следуй подсказкам мастера",
        }
    )
    keyword_matches: dict[str, str] = field(
        default_factory=lambda: {
            "оплата": "Мы принимаем банковские карты и переводы по счету.",
            "поддерж": "Команда поддержки отвечает в чате ежедневно с 9:00 до 21:00.",
        }
    )

    def make_greeting(self, name: str | None) -> str:
        """Generate greeting text using the configured template."""

        safe_name = name or "друг"
        return self.greeting_template.format(name=safe_name)

    def build_help_message(self) -> str:
        """Return text describing current bot capabilities."""

        base_help = [
            "Я могу ответить на типовые вопросы. Просто напиши вопрос текстом.",
            "Команды:",
            "• /start — приветствие и краткая инструкция.",
            "• /help — показать это сообщение.",
        ]

        if self.exact_matches:
            base_help.append(
                "\nПримеры запросов, на которые у меня уже есть ответ: "
                + ", ".join(self.exact_matches.keys())
            )

        return "\n".join(base_help)

    def make_response(self, message: str) -> str:
        """Return the most relevant response for the provided message."""

        normalized = message.strip().lower()
        if not normalized:
            return "Напиши, пожалуйста, вопрос текстом, и я постараюсь помочь."

        if normalized in self.exact_matches:
            return self.exact_matches[normalized]

        for keyword, reply in self.keyword_matches.items():
            if keyword in normalized:
                return reply

        return self.default_response


KNOWLEDGE_BASE = ConsultationKnowledgeBase()


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greet the user when the /start command is issued."""

    user_first_name = update.effective_user.first_name if update.effective_user else None
    greeting = KNOWLEDGE_BASE.make_greeting(user_first_name)
    await update.message.reply_text(greeting)


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to the /help command with editable hints."""

    await update.message.reply_text(KNOWLEDGE_BASE.build_help_message())


async def handle_message(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consult users by generating answers via the knowledge base."""

    if not update.message or not update.message.text:
        return

    response = KNOWLEDGE_BASE.make_response(update.message.text)
    await update.message.reply_text(response)


def build_application(token: str) -> Application:
    """Create and configure the Telegram Application instance."""

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application


def main() -> None:
    """Run the Telegram bot."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    token: Final[str | None] = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        LOGGER.error("Environment variable TELEGRAM_BOT_TOKEN is not set.")
        raise RuntimeError("Please set the TELEGRAM_BOT_TOKEN environment variable.")

    application = build_application(token)

    LOGGER.info("Bot is starting. Press Ctrl+C to stop.")
    try:
        application.run_polling()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Bot stopped by user.")


if __name__ == "__main__":
    main()
