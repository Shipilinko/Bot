"""Entry point for running the Telegram consultant bot."""
from __future__ import annotations

import logging
import os
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Iterable, Tuple

import yaml
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


def run_bot(config: AppConfig, token: str) -> None:
    logger.info("Конфигурация загружена. Бот: %s", config.bot.name)
    application = build_application(config, token)
    logger.info("Бот запущен. Ожидаем сообщения...")
    try:
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Остановка по запросу пользователя")

if load_dotenv is not None:
    load_dotenv()


def parse_args() -> tuple[ArgumentParser, Namespace]:
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
    parser.add_argument(
        "--secrets",
        default=Path("config/secrets.yaml"),
        type=Path,
        help="YAML файл с токеном и ID чатов (по умолчанию config/secrets.yaml).",
    )
    args = parser.parse_args()
    return parser, args


def _parse_chat_ids(raw: Iterable[object]) -> list[int]:
    chat_ids: list[int] = []
    for index, item in enumerate(raw):
        if isinstance(item, int):
            chat_ids.append(item)
            continue
        if isinstance(item, str):
            stripped = item.strip()
            if not stripped:
                continue
            try:
                chat_ids.append(int(stripped))
            except ValueError as exc:
                raise ValueError(
                    f"Значение notify_chat_ids[{index}] в файле secrets должно быть числом"
                ) from exc
            continue
        raise ValueError(
            "notify_chat_ids в файле secrets может содержать только числа или строки"
        )
    return chat_ids


def load_secrets(path: Path) -> Tuple[str | None, list[int]]:
    if not path.exists():
        return None, []
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    telegram_section = data.get("telegram") or {}
    if not isinstance(telegram_section, dict):
        raise ValueError("Секция telegram в файле secrets должна быть объектом")
    token_raw = telegram_section.get("token", "")
    token = str(token_raw).strip() if token_raw is not None else ""
    notify_raw = telegram_section.get("notify_chat_ids", []) or []
    if not isinstance(notify_raw, (list, tuple)):
        raise ValueError("notify_chat_ids в файле secrets должен быть списком")
    chat_ids = _parse_chat_ids(notify_raw)
    return token or None, chat_ids


def main() -> None:
    parser, args = parse_args()
    secrets_token, secrets_chat_ids = load_secrets(args.secrets)
    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN") or secrets_token
    if not token:
        parser.error(
            "Укажите токен через --token, TELEGRAM_BOT_TOKEN или config/secrets.yaml"
        )
    config = load_config(args.config)
    if secrets_chat_ids:
        config.bot.notify_chat_ids = secrets_chat_ids
    run_bot(config, token)


if __name__ == "__main__":
    main()
