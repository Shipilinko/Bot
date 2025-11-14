"""Handlers and routing logic for the Telegram bot."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import AppConfig, NodeConfig

logger = logging.getLogger(__name__)


@dataclass
class Reply:
    text: str
    keyboard: ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None


RETURN_TO_START_LABEL = "Вернуться в начало"

_LEAD_FIELD_LABELS = {
    "city": "Город",
    "name": "ФИО",
    "phone": "Телефон",
    "interest": "Что вас интересует",
}

_LIST_PREFIX_PATTERN = re.compile(
    r"^\s*(?:[\d]+[\.)\-:]+|[•\-*+–—])\s*",
    re.UNICODE,
)


def _normalize_lead_line(line: str) -> str:
    """Remove list-like prefixes (e.g. "1." or "•") from lead form lines."""

    cleaned = (line or "").strip()
    cleaned = _LIST_PREFIX_PATTERN.sub("", cleaned, count=1)
    return cleaned.strip()


def _parse_lead_submission(message: str) -> dict[str, str]:
    lines = [
        _normalize_lead_line(line)
        for line in (message or "").splitlines()
        if line.strip()
    ]
    data = {
        "city": lines[0] if len(lines) > 0 else "",
        "name": lines[1] if len(lines) > 1 else "",
        "phone": lines[2] if len(lines) > 2 else "",
        "interest": " ".join(lines[3:]).strip() if len(lines) > 3 else "",
    }
    return data


def _build_lead_summary(data: dict[str, str]) -> str:
    interest = data.get("interest", "").strip()
    interest_display = interest if interest else "—"
    return (
        "Спасибо! 👌\n"
        "Мы получили вашу заявку:\n\n"
        f"• Город: {data.get('city') or '—'}\n"
        f"• ФИО: {data.get('name') or '—'}\n"
        f"• Телефон: {data.get('phone') or '—'}\n"
        f"• Интересует: {interest_display}"
    )


def _build_notification_text(update: Update, data: dict[str, str], raw_message: str) -> str:
    user = update.effective_user
    chat = update.effective_chat
    username = f"@{user.username}" if user and user.username else "—"
    full_name = user.full_name if user else "—"
    chat_id = chat.id if chat else "—"
    return (
        "Новая заявка из Telegram-бота\n"
        f"Чат: {chat_id}\n"
        f"Пользователь: {full_name} ({username})\n"
        f"User ID: {user.id if user else '—'}\n\n"
        f"Город: {data.get('city') or '—'}\n"
        f"ФИО: {data.get('name') or '—'}\n"
        f"Телефон: {data.get('phone') or '—'}\n"
        f"Интерес: {data.get('interest') or '—'}\n\n"
        "Сообщение пользователя:\n"
        f"{raw_message.strip() or '—'}"
    )


def _build_keyboard(buttons: Iterable[str]) -> ReplyKeyboardMarkup | None:
    rows = [[KeyboardButton(text=btn)] for btn in buttons]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True) if rows else None


class ConversationEngine:
    """Encapsulates the decision making logic for replies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.script = config.script

    @property
    def start_node_id(self) -> str:
        return self.script.start_node

    def node_for(self, node_id: str) -> NodeConfig:
        return self.script.nodes.get(node_id, self.script.nodes[self.start_node_id])

    def match_option(self, node: NodeConfig, user_message: str):
        return self._match_option(node, user_message)

    def reply_for_node(self, node: NodeConfig) -> Reply:
        keyboard = _build_keyboard(option.label for option in node.options)
        return Reply(text=node.text, keyboard=keyboard)

    def start(self) -> tuple[str, Reply]:
        node = self.script.nodes[self.start_node_id]
        return node.id, self.reply_for_node(node)

    def resolve(self, current_node_id: str, user_message: str) -> tuple[str | None, Reply | None]:
        node = self.script.nodes.get(current_node_id, self.script.nodes[self.start_node_id])
        option = self._match_option(node, user_message)
        if option:
            next_node = self.script.nodes[option.next_node]
            return next_node.id, self.reply_for_node(next_node)
        fallback = Reply(text=self.script.fallback_text, keyboard=_build_keyboard(opt.label for opt in node.options))
        return None, fallback

    def farewell(self) -> Reply:
        return Reply(text=self.config.bot.farewell, keyboard=ReplyKeyboardRemove())

    def fallback(self, node: NodeConfig) -> Reply:
        return Reply(
            text=self.script.fallback_text,
            keyboard=_build_keyboard(option.label for option in node.options),
        )

    def _match_option(self, node: NodeConfig, user_message: str):
        normalized = (user_message or "").strip().casefold()
        for option in node.options:
            if option.label.casefold() == normalized:
                return option
        return None


class BotHandlers:
    """Связывает ConversationEngine с telegram.ext."""

    def __init__(self, config: AppConfig) -> None:
        self.engine = ConversationEngine(config)
        self.notify_chat_ids = config.bot.notify_chat_ids

    def register(self, app: Application) -> None:
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("menu", self.menu))
        app.add_handler(CommandHandler("stop", self.stop))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        node_id, reply = self.engine.start()
        context.user_data["node_id"] = node_id
        await self._send_reply(update, reply)

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.start(update, context)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply_text = (
            "Выберите подходящий вариант на клавиатуре. Команда /menu возвращает к началу сценария,"
            " а /stop завершает диалог."
        )
        if update.effective_chat:
            await update.effective_chat.send_message(reply_text)

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply = self.engine.farewell()
        context.user_data.pop("node_id", None)
        await self._send_reply(update, reply)

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        message_text = update.message.text or ""
        current_node_id = context.user_data.get("node_id", self.engine.start_node_id)
        node = self.engine.node_for(current_node_id)
        option = self.engine.match_option(node, message_text)
        if option:
            next_node = self.engine.node_for(option.next_node)
            context.user_data["node_id"] = next_node.id
            await self._send_reply(update, self.engine.reply_for_node(next_node))
            return
        if node.capture and message_text.strip():
            next_node_id, reply = await self._handle_capture(node, update, context)
            context.user_data["node_id"] = next_node_id
            await self._send_reply(update, reply)
            return
        await self._send_reply(update, self.engine.fallback(node))

    async def _send_reply(self, update: Update, reply: Reply | None) -> None:
        if not reply or not update.effective_chat:
            return
        await update.effective_chat.send_message(reply.text, reply_markup=reply.keyboard)

    async def _handle_capture(
        self,
        node: NodeConfig,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> tuple[str, Reply]:
        if not node.capture:
            return node.id, self.engine.fallback(node)
        kind = node.capture.kind
        if kind != "lead_form":  # pragma: no cover - для будущих расширений
            logger.warning("Неизвестный тип capture '%s'", kind)
            return node.id, self.engine.fallback(node)
        message_text = update.message.text or ""
        data = _parse_lead_submission(message_text)
        missing_fields = [
            _LEAD_FIELD_LABELS[field]
            for field in ("city", "name", "phone", "interest")
            if not data.get(field)
        ]
        if missing_fields:
            prompt_lines = [
                "Кажется, в сообщении не хватает данных:",
                *[f"• {field}" for field in missing_fields],
                "",
                "Пожалуйста, отправьте данные одним сообщением в формате:",
                "Город",
                "ФИО",
                "Номер телефона",
                "Что вас интересует?",
            ]
            keyboard = self.engine.reply_for_node(node).keyboard
            return node.id, Reply(text="\n".join(prompt_lines).strip(), keyboard=keyboard)
        await self._notify_managers(update, context, data, message_text)
        summary = _build_lead_summary(data)
        start_keyboard = self.engine.reply_for_node(
            self.engine.node_for(self.engine.start_node_id)
        ).keyboard
        keyboard = start_keyboard or _build_keyboard([RETURN_TO_START_LABEL])
        next_node_id = node.capture.next_node or self.engine.start_node_id
        return next_node_id, Reply(text=summary, keyboard=keyboard)

    async def _notify_managers(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: dict[str, str],
        raw_message: str,
    ) -> None:
        if not self.notify_chat_ids:
            return
        if not context.application:
            logger.warning("Приложение Telegram не инициализировано, уведомление не отправлено")
            return
        text = _build_notification_text(update, data, raw_message)
        for chat_id in self.notify_chat_ids:
            try:
                await context.application.bot.send_message(chat_id, text)
            except Exception as exc:  # pragma: no cover - зависит от Telegram API
                logger.warning("Не удалось отправить уведомление в чат %s: %s", chat_id, exc)


__all__ = ["BotHandlers", "ConversationEngine"]
