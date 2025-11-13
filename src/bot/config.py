"""Инструменты для загрузки и валидации конфигурации бота."""
from __future__ import annotations

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
class NodeConfig:
    """Сценарный узел с текстом и набором вариантов выбора."""

    id: str
    text: str
    options: List[OptionConfig] = field(default_factory=list)


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


@dataclass
class AppConfig:
    """Готовая конфигурация приложения."""

    bot: BotBehaviourConfig
    script: ScriptConfig


def _parse_bot(raw: dict) -> BotBehaviourConfig:
    if "name" not in raw:
        raise ValueError("Не задано имя бота (bot.name)")
    farewell = str(raw.get("farewell", "Буду рад снова помочь!"))
    return BotBehaviourConfig(name=str(raw["name"]), farewell=farewell)


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
    return NodeConfig(id=node_id, text=text, options=options)


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
    "NodeConfig",
    "OptionConfig",
    "ScriptConfig",
    "load_config",
]
