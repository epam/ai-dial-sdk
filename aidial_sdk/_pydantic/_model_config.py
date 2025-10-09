"""
Helper classes that unify model configuration between Pydantic v1 and v2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from aidial_sdk._pydantic import PYDANTIC_V2, BaseModel

_Model = TypeVar("_Model", bound=BaseModel)


class ModelConfigWrapper:
    _model_config: ModelConfigBase

    def __init__(self, model_config: ModelConfigBase):
        self._model_config = model_config

    def __getitem__(self, field: str) -> Any:
        return self._model_config.get_field(field, None)

    def __setitem__(self, field: str, value: Any) -> None:
        self._model_config.set_field(field, value)

    def post_process_schema(
        self, on_schema: Callable[[Dict[str, Any]], None]
    ) -> None:
        attr_name = self._model_config.schema_extra_field
        old_schema_extra = self[attr_name]

        def _schema_extra(
            schema: Dict[str, Any], model: Type[BaseModel]
        ) -> None:
            if old_schema_extra:
                old_schema_extra(schema, model)
            on_schema(schema)

        self[attr_name] = _schema_extra

    @classmethod
    def create(
        cls, base_cls: Optional[Type[_Model]], namespace: Dict[str, Any]
    ) -> ModelConfigWrapper:
        if PYDANTIC_V2:
            return cls(_ConfigV2.create(base_cls, namespace))
        else:
            return cls(_ConfigV1.create(base_cls, namespace))


class ModelConfigBase(ABC):
    @abstractmethod
    def set_field(self, field: str, value: Any) -> None:
        pass

    @abstractmethod
    def get_field(self, field: str, default: Any) -> Any:
        pass

    @property
    @abstractmethod
    def schema_extra_field(self) -> str:
        pass

    @classmethod
    @abstractmethod
    def create(
        cls, base_cls: Optional[Type[_Model]], namespace: Dict[str, Any]
    ) -> ModelConfigBase:
        pass


class _ConfigV1(ModelConfigBase):
    config_cls: Type

    def __init__(self, config_cls: Type):
        self.config_cls = config_cls

    def set_field(self, field: str, value: Any) -> None:
        setattr(self.config_cls, field, value)

    def get_field(self, field: str, default: Any) -> Any:
        return getattr(self.config_cls, field, default)

    @property
    def schema_extra_field(self) -> str:
        return "schema_extra"

    @classmethod
    def create(
        cls, base_cls: Optional[Type[_Model]], namespace: Dict[str, Any]
    ) -> ModelConfigBase:
        if (config_cls := namespace.get("Config")) is None:
            conf_base_cls = (
                None if base_cls is None else getattr(base_cls, "Config", None)
            )

            config_cls = type("Config", (conf_base_cls or object,), {})

            if module := namespace.get("__module__"):
                config_cls.__module__ = module
            if qualname := namespace.get("__qualname__"):
                config_cls.__qualname__ = f"{qualname}.{config_cls.__name__}"

            namespace["Config"] = config_cls

        return cls(config_cls)


class _ConfigV2(ModelConfigBase):
    model_config: Dict

    def __init__(self, model_config: Dict):
        self.model_config = model_config

    def set_field(self, field: str, value: Any) -> None:
        self.model_config[field] = value

    def get_field(self, field: str, default: Any) -> Any:
        return self.model_config.get(field, default)

    @property
    def schema_extra_field(self) -> str:
        return "json_schema_extra"

    @classmethod
    def create(
        cls, base_cls: Optional[Type[_Model]], namespace: Dict[str, Any]
    ) -> ModelConfigBase:
        base_model_config = (
            {} if base_cls is None else getattr(base_cls, "model_config", {})
        )

        curr_model_config = namespace.get("model_config") or {}

        model_config = namespace["model_config"] = {
            **base_model_config,
            **curr_model_config,
        }

        return cls(model_config)
