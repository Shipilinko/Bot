"""Handlers and routing logic for the Telegram bot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import AppConfig, NodeConfig


@dataclass
class Reply:
    text: str
    keyboard: ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None


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
        current_node_id = context.user_data.get("node_id", self.engine.start_node_id)
        next_node_id, reply = self.engine.resolve(current_node_id, update.message.text or "")
        if next_node_id:
            context.user_data["node_id"] = next_node_id
        await self._send_reply(update, reply)

    async def _send_reply(self, update: Update, reply: Reply | None) -> None:
        if not reply or not update.effective_chat:
            return
        await update.effective_chat.send_message(reply.text, reply_markup=reply.keyboard)


__all__ = ["BotHandlers", "ConversationEngine"]
