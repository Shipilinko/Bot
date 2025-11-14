"""Инструменты для загрузки и валидации конфигурации бота."""
from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass
class OptionConfig:
    """Вариант ответа, который видит пользователь."""

    label: str
    next_node: str


@dataclass
class CaptureConfig:
    """Описание действий при свободном вводе пользователя."""

    kind: str
    next_node: str | None = None


@dataclass
class NodeConfig:
    """Сценарный узел с текстом и набором вариантов выбора."""

    id: str
    text: str
    options: List[OptionConfig] = field(default_factory=list)
    capture: CaptureConfig | None = None


@dataclass
class ScriptConfig:
    """Определяет дерево сценария диалога."""

    start_node: str
    fallback_text: str
    nodes: Dict[str, NodeConfig]


@dataclass
class BotBehaviourConfig:
    """Основные параметры бота."""

    name: str
    farewell: str
    notify_chat_ids: List[int] = field(default_factory=list)


@dataclass
class AppConfig:
    """Готовая конфигурация приложения."""

    bot: BotBehaviourConfig
    script: ScriptConfig


_ENV_TOKEN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def _resolve_env_value(value: object, *, allow_empty: bool = False) -> str:
    """Поддерживает плейсхолдеры формата ${ENV_VAR}."""

    if not isinstance(value, str):
        raise TypeError("Ожидалась строка для подстановки переменной окружения")
    stripped = value.strip()
    match = _ENV_TOKEN.fullmatch(stripped)
    if match:
        env_name = match.group(1)
        resolved = os.getenv(env_name, "")
        if not resolved and not allow_empty:
            warnings.warn(
                f"Переменная окружения {env_name} не задана. "
                "Связанные настройки будут пропущены.",
                stacklevel=2,
            )
        return resolved
    return stripped


def _parse_chat_ids(raw: List[object]) -> List[int]:
    chat_ids: List[int] = []
    for index, item in enumerate(raw):
        if isinstance(item, int):
            chat_ids.append(item)
            continue
        if isinstance(item, str):
            resolved = _resolve_env_value(item)
            if not resolved:
                continue
            try:
                chat_ids.append(int(resolved))
            except ValueError as exc:  # pragma: no cover - конфигурационные ошибки
                raise ValueError(
                    f"Значение bot.notify_chat_ids[{index}] должно быть числом"
                ) from exc
            continue
        raise ValueError(
            "Список bot.notify_chat_ids может содержать только числа или строки"
        )
    return chat_ids


def _parse_capture(raw: dict, node_id: str) -> CaptureConfig:
    kind = str(raw.get("type") or raw.get("kind") or "").strip()
    if not kind:
        raise ValueError(
            f"Узел '{node_id}' содержит блок capture без типа (capture.type)"
        )
    next_raw = raw.get("next") if raw.get("next") is not None else raw.get("next_node")
    next_node = str(next_raw).strip() if next_raw is not None else ""
    return CaptureConfig(kind=kind, next_node=next_node or None)


def _parse_bot(raw: dict) -> BotBehaviourConfig:
    if "name" not in raw:
        raise ValueError("Не задано имя бота (bot.name)")
    farewell = str(raw.get("farewell", "Буду рад снова помочь!"))
    notify_raw = raw.get("notify_chat_ids", []) or []
    if not isinstance(notify_raw, list):
        raise ValueError("Параметр bot.notify_chat_ids должен быть списком")
    notify_chat_ids = _parse_chat_ids(notify_raw)
    return BotBehaviourConfig(
        name=str(raw["name"]),
        farewell=farewell,
        notify_chat_ids=notify_chat_ids,
    )


def _parse_option(raw: dict, node_id: str, index: int) -> OptionConfig:
    label = str(raw.get("label", "")).strip()
    next_raw = raw.get("next")
    if next_raw is None:
        next_raw = raw.get("next_node")
    next_node = str(next_raw).strip() if next_raw is not None else ""
    if not label:
        raise ValueError(f"Узел '{node_id}' содержит вариант без текста (index={index})")
    if not next_node:
        raise ValueError(f"Вариант '{label}' из узла '{node_id}' не указывает следующий узел")
    return OptionConfig(label=label, next_node=next_node)


def _parse_node(raw: dict) -> NodeConfig:
    node_id = str(raw.get("id", "")).strip()
    if not node_id:
        raise ValueError("Каждый узел сценария должен иметь идентификатор (script.nodes[].id)")
    text = str(raw.get("text", "")).strip()
    if not text:
        raise ValueError(f"Узел '{node_id}' не содержит текста ответа")
    options = [_parse_option(option, node_id, index) for index, option in enumerate(raw.get("options", []))]
    capture_cfg = raw.get("capture")
    capture = _parse_capture(capture_cfg, node_id) if capture_cfg else None
    return NodeConfig(id=node_id, text=text, options=options, capture=capture)


def _parse_script(raw: dict) -> ScriptConfig:
    if not raw:
        raise ValueError("Сценарий (script) должен быть определён в конфигурации")
    start_node = str(raw.get("start_node", "")).strip()
    if not start_node:
        raise ValueError("Не указан стартовый узел сценария (script.start_node)")
    fallback_text = str(raw.get("fallback_text", "Пожалуйста, выберите один из вариантов на клавиатуре."))
    raw_nodes = raw.get("nodes", []) or []
    if not raw_nodes:
        raise ValueError("Сценарий должен содержать хотя бы один узел (script.nodes)")
    nodes = [_parse_node(node_raw) for node_raw in raw_nodes]
    nodes_by_id = {node.id: node for node in nodes}
    if start_node not in nodes_by_id:
        raise ValueError("Стартовый узел сценария отсутствует в script.nodes")
    for node in nodes:
        for option in node.options:
            if option.next_node not in nodes_by_id:
                raise ValueError(
                    f"Узел '{node.id}' содержит переход на отсутствующий узел '{option.next_node}'"
                )
        if node.capture and node.capture.next_node and node.capture.next_node not in nodes_by_id:
            raise ValueError(
                f"Узел '{node.id}' с capture ссылается на отсутствующий узел '{node.capture.next_node}'"
            )
    return ScriptConfig(start_node=start_node, fallback_text=fallback_text, nodes=nodes_by_id)


def load_config(path: str | Path) -> AppConfig:
    """Загружает конфигурацию бота из YAML файла."""

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Файл конфигурации {cfg_path} не найден")
    with cfg_path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}

    bot_cfg = _parse_bot(data.get("bot", {}))
    script = _parse_script(data.get("script", {}))
    return AppConfig(bot=bot_cfg, script=script)


__all__ = [
    "AppConfig",
    "BotBehaviourConfig",
    "CaptureConfig",
    "NodeConfig",
    "OptionConfig",
    "ScriptConfig",
    "load_config",
]
