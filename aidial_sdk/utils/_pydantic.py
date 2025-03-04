from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Type

from pydantic import BaseModel

from aidial_sdk.pydantic import PYDANTIC_V2


class ConfigWrapper(ABC):
    @abstractmethod
    def _set_field(self, field: str, value: Any) -> None:
        pass

    @abstractmethod
    def _get_field(self, field: str, default: Any) -> Any:
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        pass

    @property
    @abstractmethod
    def schema_extra_field(self) -> str:
        pass

    def __getitem__(self, field: str) -> Any:
        return self._get_field(field, None)

    def __setitem__(self, field: str, value: Any) -> None:
        self._set_field(field, value)

    def post_process_schema(
        self, on_schema: Callable[[Dict[str, Any]], None]
    ) -> None:
        attr_name = self.schema_extra_field
        old_schema_extra = self[attr_name]

        def _schema_extra(
            schema: Dict[str, Any], model: Type[BaseModel]
        ) -> None:
            if old_schema_extra:
                old_schema_extra(schema, model)
            on_schema(schema)

        self[attr_name] = _schema_extra

    @staticmethod
    def create(namespace: Dict[str, Any]) -> ConfigWrapper:
        if PYDANTIC_V2:
            model_config = namespace["model_config"] = (
                namespace.get("model_config") or {}
            )
            return _ConfigV2(model_config)
        else:
            if (config_cls := namespace.get("Config")) is None:
                config_cls = type("Config", (object,), {})

                if module := namespace.get("__module__"):
                    config_cls.__module__ = module
                if qualname := namespace.get("__qualname__"):
                    config_cls.__qualname__ = (
                        f"{qualname}.{config_cls.__name__}"
                    )

                namespace["Config"] = config_cls

            return _ConfigV1(config_cls)


class _ConfigV1(ConfigWrapper):
    config_cls: type

    def __init__(self, config_cls: type):
        self.config_cls = config_cls

    def _set_field(self, field: str, value: Any) -> None:
        setattr(self.config_cls, field, value)

    def _get_field(self, field: str, default: Any) -> Any:
        return getattr(self.config_cls, field, default)

    @property
    def schema_extra_field(self) -> str:
        return "schema_extra"

    def to_dict(self) -> dict:
        return dict(self.config_cls.__dict__)


class _ConfigV2(ConfigWrapper):
    model_config: dict

    def __init__(self, model_config: dict):
        self.model_config = model_config

    def _set_field(self, field: str, value: Any) -> None:
        self.model_config[field] = value

    def _get_field(self, field: str, default: Any) -> Any:
        return self.model_config.get(field, default)

    @property
    def schema_extra_field(self) -> str:
        return "json_schema_extra"

    def to_dict(self) -> dict:
        return self.model_config
