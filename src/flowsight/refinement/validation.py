"""Validate JSON shapes before applying Architecture semantic checks."""

from typing import Any


def validate_architecture_shape(specification: Any, reverse_map: Any) -> None:
    if not isinstance(specification, dict):
        raise ValueError("Architecture specification must be an object")
    if not isinstance(reverse_map, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in reverse_map.items()
    ):
        raise ValueError("reverse ID map must be a JSON string map")
    meta = specification.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("Architecture meta must be an object")
    collections = {name: specification.get(name, [])
                   for name in ("components", "connections", "boundaries", "cards")}
    collections["views"] = meta.get("views", [])
    for field, value in collections.items():
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError(f"Architecture {field} must be a list of objects")
    for component in specification.get("components", []):
        if not isinstance(component.get("id"), str) or not component["id"]:
            raise ValueError("Architecture component IDs must be non-empty strings")
        sources = component.get("sources", [])
        if not isinstance(sources, list) or not all(isinstance(source, dict) for source in sources):
            raise ValueError("Architecture sources must be a list of objects")
    for connection in specification.get("connections", []):
        if not all(isinstance(connection.get(end), str) for end in ("from", "to")):
            raise ValueError("Architecture connection endpoints must be strings")
    for boundary in specification.get("boundaries", []):
        wraps = boundary.get("wraps", [])
        if not isinstance(wraps, list) or not all(isinstance(item, str) for item in wraps):
            raise ValueError("Architecture boundary wraps must be a list of component IDs")
