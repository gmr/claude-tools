import inspect
import types
import typing

import jsonschema_models as jsm

from claude_tools import models


def _type_to_schema(value: typing.Any) -> jsm.Schema:
    for param_type in (str, int, float, bool, type(None)):
        if value is param_type:
            return jsm.Schema.model_validate({'type': value})

    origin = typing.get_origin(value)
    args = typing.get_args(value)

    if value is list and origin is None and not args:
        return jsm.Schema.model_validate({'type': 'array'})
    elif value is dict and origin is None and not args:
        return jsm.Schema.model_validate({'type': 'object'})
    elif origin is dict and len(args) == 2:
        return jsm.Schema.model_validate(
            {
                'type': 'object',
                'additional_properties': _type_to_schema(args[1]),
            }
        )
    elif origin is list:
        items = (
            _handle_union_type(value)
            if len(args) > 1
            else _type_to_schema(args[0])
        )
        return jsm.Schema.model_validate({'type': 'array', 'items': items})
    elif origin is typing.Literal:
        return jsm.Schema.model_validate({'type': type(args[0]), 'enum': args})
    elif origin is typing.Union or origin is types.UnionType:
        return _handle_union_type(value)

    raise RuntimeError(f'Unsupported type {value} / {origin} / {args}')


def _handle_union_type(param_type: typing.Any) -> jsm.Schema:
    """Helper function to handle Union types, including Optional."""
    simple = True
    simple_types = []
    any_of_types = []
    for arg in typing.get_args(param_type):
        value = _type_to_schema(arg)
        any_of_types.append(value)
        simple_types.append(value.type)
        if len(value.model_dump(exclude_none=True).keys()) > 1:
            simple = False
    schema = {'type': simple_types}
    if not simple:
        schema = {'anyOf': any_of_types}
    return jsm.Schema.model_validate(schema)


def to_schema(func: typing.Callable) -> jsm.Schema:
    """Convert a function's signature to JSON Schema.

    Args:
        func: Function to inspect

    Returns:
        Dictionary containing JSON Schema

    """
    sig = inspect.signature(func)
    type_hints = typing.get_type_hints(func)
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        if name in ('self', 'cls') or param.annotation is models.Request:
            continue
        param_schema = {}
        if name in type_hints:
            param_schema = _type_to_schema(type_hints[name])
        param_schema.title = name.capitalize()
        if param.default is inspect.Parameter.empty:
            required.append(name)
        properties[name] = param_schema
    schema = {'type': 'object', 'properties': properties}
    if required:
        schema['required'] = required
    return jsm.Schema.model_validate(schema)
