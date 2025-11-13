"""Entry point for running the Telegram consultant bot."""
from __future__ import annotations

import logging
import os
from argparse import ArgumentParser
from pathlib import Path

from telegram.ext import Application

from .config import AppConfig, load_config
from .handlers import BotHandlers

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency safety
    load_dotenv = None

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=os.getenv("BOT_LOG_LEVEL", "INFO"),
)
logger = logging.getLogger(__name__)


def build_application(config: AppConfig, token: str) -> Application:
    app = Application.builder().token(token).build()
    handlers = BotHandlers(config)
    handlers.register(app)
    return app


def run_bot(config_path: Path, token: str) -> None:
    config = load_config(config_path)
    logger.info("Конфигурация загружена. Бот: %s", config.bot.name)
    application = build_application(config, token)
    logger.info("Бот запущен. Ожидаем сообщения...")
    try:
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Остановка по запросу пользователя")

if load_dotenv is not None:
    load_dotenv()


def parse_args() -> tuple[Path, str]:
    parser = ArgumentParser(description="Telegram бот-консультант")
    parser.add_argument(
        "--config",
        default=Path("config/bot_config.yaml"),
        type=Path,
        help="Путь к YAML файлу с настройками.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Токен Telegram (по умолчанию переменная окружения TELEGRAM_BOT_TOKEN)",
    )
    args = parser.parse_args()
    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        parser.error("Укажите токен через --token или TELEGRAM_BOT_TOKEN")
    return args.config, token


def main() -> None:
    config_path, token = parse_args()
    run_bot(config_path, token)


if __name__ == "__main__":
    main()
