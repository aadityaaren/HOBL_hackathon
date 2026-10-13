# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Validate an AI-authored, self-contained HOBL keyboard scenario."""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from .workbook_reader import WorkbookValidationError, read_workbook
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from workbook_reader import WorkbookValidationError, read_workbook


ID_PATTERN = re.compile(r"^[0-9ACEFHJKLMNPRTUVWXY]+$")
SCENARIO_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ALLOWED_TOP_LEVEL_TYPES = {"Information", "Run Test"}
ALLOWED_RUN_TYPES = {"Type", "Delay"}
FORBIDDEN_TEXT = ("_library", "include_path", "import_run_user_only")
SPECIAL_KEY_MIN = 0xE000
SPECIAL_KEY_MAX = 0xF8FF


class ScenarioValidationError(ValueError):
    """Raised for an invalid generated scenario."""


def _is_nonnegative_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _walk_actions(actions: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for action in actions:
        if not isinstance(action, dict):
            continue
        yield action
        children = action.get("children", [])
        if isinstance(children, list):
            yield from _walk_actions(children)


def _walk_json_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_json_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_strings(child)


def _load_supported_key_codes(errors: list[str]) -> set[str]:
    repo_root = Path(__file__).resolve().parents[3]
    key_map_path = repo_root / "ScenarioMaker" / "key_map.py"
    try:
        tree = ast.parse(
            key_map_path.read_text(encoding="utf-8"),
            filename=str(key_map_path),
        )
    except (OSError, SyntaxError) as error:
        errors.append(f"Unable to read ScenarioMaker key map: {error}")
        return set()

    codes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "map"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for value in node.value.values:
            if (
                isinstance(value, (ast.List, ast.Tuple))
                and value.elts
                and isinstance(value.elts[0], ast.Constant)
                and isinstance(value.elts[0].value, str)
            ):
                codes.add(value.elts[0].value)
    if not codes:
        errors.append("ScenarioMaker key map does not contain any supported key codes.")
    return codes


def _validate_hobl_runtime(
    scenario_name: str,
    json_path: Path,
    errors: list[str],
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    platform_folder = json_path.parent.parent.name
    module_name = f"scenarios.{platform_folder}.{scenario_name}.{scenario_name}"
    try:
        importlib.invalidate_caches()
        importlib.import_module(module_name)
        from core.app_scenario import Scenario

        scenario = Scenario.__new__(Scenario)
        scenario.load_action_json(str(json_path))
    except Exception as error:
        errors.append(f"HOBL runtime could not import and load the scenario: {error}")


def _validate_imports(
    tree: ast.AST,
    path: Path,
    allowed_roots: set[str],
    allowed_relative_modules: set[str],
    errors: list[str],
) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root not in allowed_roots:
                    errors.append(
                        f"{path.name} imports unsupported runtime dependency {alias.name!r}."
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                imported_modules = (
                    {module}
                    if module
                    else {alias.name for alias in node.names}
                )
                unsupported_modules = imported_modules - allowed_relative_modules
                if unsupported_modules:
                    errors.append(
                        f"{path.name} imports unsupported relative module(s): "
                        f"{', '.join(sorted(unsupported_modules))}."
                    )
            else:
                root = module.split(".", maxsplit=1)[0]
                if root not in allowed_roots:
                    errors.append(
                        f"{path.name} imports unsupported runtime dependency {module!r}."
                    )


def _validate_python(path: Path, scenario_name: str, errors: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"Unable to read {path.name}: {error}")
        return

    lowered = source.lower()
    for forbidden in FORBIDDEN_TEXT:
        if forbidden.lower() in lowered:
            errors.append(f"{path.name} contains forbidden reference {forbidden!r}.")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        errors.append(f"{path.name} has invalid Python syntax: {error.msg} at line {error.lineno}.")
        return
    _validate_imports(
        tree,
        path,
        {"__future__", "core", "logging", "os"},
        {"default_params"},
        errors,
    )

    expected_class = _class_name(scenario_name)
    scenario_classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Attribute) and base.attr == "Scenario":
                scenario_classes.append(node)
            elif isinstance(base, ast.Name) and base.id == "Scenario":
                scenario_classes.append(node)

    matching_classes = [node for node in scenario_classes if node.name == expected_class]
    if not matching_classes:
        errors.append(
            f"{path.name} must define {expected_class} derived from core.app_scenario.Scenario."
        )
        return

    scenario_class = matching_classes[0]
    methods = {
        node.name
        for node in scenario_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method in ("setUp", "runTest", "tearDown", "kill"):
        if method not in methods:
            errors.append(f"{path.name} is missing required method {method}().")

    has_default_params_call = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "default_params"
        and node.func.attr == "run"
        for node in ast.walk(scenario_class)
    )
    if not has_default_params_call:
        errors.append(f"{path.name} must call default_params.run().")

    has_json_load = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "load_action_json"
        for node in ast.walk(scenario_class)
    )
    if not has_json_load:
        errors.append(f"{path.name} must load its action JSON with load_action_json().")

    has_run_actions = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_actions"
        for node in ast.walk(scenario_class)
    )
    if not has_run_actions:
        errors.append(f"{path.name} must execute actions with run_actions().")


def _validate_default_params(path: Path, errors: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"Unable to read {path.name}: {error}")
        return
    lowered = source.lower()
    for forbidden in FORBIDDEN_TEXT:
        if forbidden.lower() in lowered:
            errors.append(f"{path.name} contains forbidden reference {forbidden!r}.")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        errors.append(f"{path.name} has invalid Python syntax: {error.msg} at line {error.lineno}.")
        return
    _validate_imports(tree, path, {"__future__", "core"}, set(), errors)


def _validate_init(path: Path, scenario_name: str, errors: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        errors.append(f"Unable to read {path.name}: {error}")
        return
    expected = f"from .{scenario_name} import *"
    if source != expected:
        errors.append(f"__init__.py must contain exactly: {expected}")


def _validate_action_common(
    action: dict[str, Any],
    location: str,
    seen_ids: set[str],
    errors: list[str],
) -> None:
    action_id = action.get("id")
    if not isinstance(action_id, str) or not ID_PATTERN.fullmatch(action_id):
        errors.append(f"{location} has an invalid Scenario Maker action ID: {action_id!r}.")
    elif action_id in seen_ids:
        errors.append(f"Duplicate action ID found: {action_id}.")
    else:
        seen_ids.add(action_id)

    if not isinstance(action.get("description"), str):
        errors.append(f"{location} must contain a string description.")
    if not isinstance(action.get("enabled"), bool):
        errors.append(f"{location} must contain a boolean enabled value.")
    elif not action["enabled"]:
        errors.append(f"{location} must be enabled; disabled workbook actions must be omitted.")
    if not isinstance(action.get("children"), list):
        errors.append(f"{location} must contain a children list.")

    for forbidden in ("include_path",):
        if forbidden in action:
            errors.append(f"{location} contains forbidden field {forbidden!r}.")


def _validate_json(
    path: Path,
    expected_action_count: int | None,
    supported_key_codes: set[str],
    errors: list[str],
) -> tuple[int, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        errors.append(f"Unable to read {path.name}: {error}")
        return 0, 0
    except json.JSONDecodeError as error:
        errors.append(f"{path.name} has invalid JSON at line {error.lineno}: {error.msg}.")
        return 0, 0

    if not isinstance(data, list):
        errors.append(f"{path.name} must contain a top-level JSON list.")
        return 0, 0

    top_level_types = [
        action.get("type") if isinstance(action, dict) else None
        for action in data
    ]
    if top_level_types != ["Information", "Run Test"]:
        errors.append(
            "Top-level actions must be exactly Information followed by Run Test."
        )

    lowered_json_strings = [value.lower() for value in _walk_json_strings(data)]
    for forbidden in FORBIDDEN_TEXT:
        if any(forbidden.lower() in value for value in lowered_json_strings):
            errors.append(f"{path.name} contains forbidden reference {forbidden!r}.")

    seen_ids: set[str] = set()
    information_actions = []
    run_sections = []
    generated_actions: list[dict[str, Any]] = []

    for index, action in enumerate(data):
        location = f"top-level action {index + 1}"
        if not isinstance(action, dict):
            errors.append(f"{location} must be a JSON object.")
            continue
        _validate_action_common(action, location, seen_ids, errors)
        action_type = action.get("type")
        if action_type not in ALLOWED_TOP_LEVEL_TYPES:
            errors.append(
                f"{location} has unsupported top-level type {action_type!r}; "
                "only Information and Run Test are allowed."
            )
        if action_type == "Information":
            information_actions.append(action)
        elif action_type == "Run Test":
            run_sections.append(action)

    if len(information_actions) != 1:
        errors.append(f"Scenario must contain exactly one Information action; found {len(information_actions)}.")
    if len(run_sections) != 1:
        errors.append(f"Scenario must contain exactly one Run Test section; found {len(run_sections)}.")

    if run_sections:
        children = run_sections[0].get("children", [])
        if isinstance(children, list):
            generated_actions = children
            for index, action in enumerate(children):
                location = f"Run Test action {index + 1}"
                if not isinstance(action, dict):
                    errors.append(f"{location} must be a JSON object.")
                    continue
                _validate_action_common(action, location, seen_ids, errors)
                action_type = action.get("type")
                if action_type not in ALLOWED_RUN_TYPES:
                    errors.append(
                        f"{location} has unsupported type {action_type!r}; "
                        "only Type and Delay are allowed."
                    )
                    continue
                if action.get("children") != []:
                    errors.append(f"{location} must not contain nested actions.")
                if action_type == "Type":
                    text = action.get("text")
                    if not isinstance(text, str) or not text:
                        errors.append(f"{location} must contain nonempty text.")
                    elif supported_key_codes:
                        unsupported_codes = sorted(
                            {
                                character
                                for character in text
                                if SPECIAL_KEY_MIN <= ord(character) <= SPECIAL_KEY_MAX
                                and character not in supported_key_codes
                            }
                        )
                        if unsupported_codes:
                            formatted = ", ".join(
                                f"U+{ord(character):04X}"
                                for character in unsupported_codes
                            )
                            errors.append(
                                f"{location} contains unsupported special key code(s): {formatted}."
                            )
                    if "typing_delay" not in action:
                        errors.append(f"{location} must contain typing_delay.")
                    else:
                        typing_delay = action["typing_delay"]
                        is_parameter = (
                            isinstance(typing_delay, str)
                            and typing_delay.startswith("[")
                            and typing_delay.endswith("]")
                            and len(typing_delay) > 2
                        )
                        if not is_parameter and not _is_nonnegative_number(typing_delay):
                            errors.append(
                                f"{location} typing_delay must be nonnegative or a parameter."
                            )
                    if not _is_nonnegative_number(action.get("delay")):
                        errors.append(f"{location} must contain a nonnegative delay.")
                elif action_type == "Delay":
                    if not _is_nonnegative_number(action.get("delay")):
                        errors.append(f"{location} must contain a nonnegative delay duration.")
    all_actions = list(_walk_actions(data))
    if any(action.get("type") == "Include" for action in all_actions):
        errors.append("Scenario contains a forbidden Include action.")
    if expected_action_count is not None and len(generated_actions) != expected_action_count:
        errors.append(
            f"Workbook contains {expected_action_count} enabled actions, but Run Test contains "
            f"{len(generated_actions)} actions."
        )
    return len(generated_actions), len(seen_ids)


def validate_scenario(
    scenario_dir: str | Path,
    workbook_path: str | Path | None = None,
    hobl_runtime_check: bool = False,
) -> dict[str, Any]:
    """Validate a generated scenario without changing any files."""

    directory = Path(scenario_dir).expanduser().resolve()
    errors: list[str] = []
    if not directory.is_dir():
        raise ScenarioValidationError(f"Scenario directory not found: {directory}")

    scenario_name = directory.name
    if not SCENARIO_NAME_PATTERN.fullmatch(scenario_name):
        errors.append(
            f"Scenario directory name must use lowercase snake_case: {scenario_name!r}."
        )

    expected_files = {
        "__init__.py",
        f"{scenario_name}.py",
        f"{scenario_name}.json",
        "default_params.py",
    }
    actual_files = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "desktop.ini"
    }
    missing_files = sorted(expected_files - actual_files)
    unexpected_files = sorted(actual_files - expected_files)
    if missing_files:
        errors.append(f"Missing required file(s): {', '.join(missing_files)}.")
    if unexpected_files:
        errors.append(
            f"Unexpected file(s) in self-contained MVP scenario: {', '.join(unexpected_files)}."
        )
    if any(path.is_dir() and path.name != "__pycache__" for path in directory.iterdir()):
        errors.append("Scenario must not contain nested directories.")

    workbook = None
    if workbook_path is not None:
        try:
            workbook = read_workbook(workbook_path)
        except WorkbookValidationError as error:
            errors.append(f"Workbook validation failed: {error}")
        else:
            workbook_scenario = workbook["scenario"]
            if workbook_scenario["name"] != scenario_name:
                errors.append(
                    f"Workbook scenario name {workbook_scenario['name']!r} does not "
                    f"match directory {scenario_name!r}."
                )
            expected_parent = (
                "windows"
                if workbook_scenario["platform"] == "Windows"
                else "macos"
            )
            if directory.parent.name.lower() != expected_parent:
                errors.append(
                    f"Workbook platform {workbook_scenario['platform']} requires the "
                    f"scenario under scenarios\\{expected_parent}."
                )

    python_path = directory / f"{scenario_name}.py"
    json_path = directory / f"{scenario_name}.json"
    default_params_path = directory / "default_params.py"
    init_path = directory / "__init__.py"

    if python_path.is_file():
        _validate_python(python_path, scenario_name, errors)
    if default_params_path.is_file():
        _validate_default_params(default_params_path, errors)
    if init_path.is_file():
        _validate_init(init_path, scenario_name, errors)

    expected_action_count = None
    if workbook is not None:
        expected_action_count = workbook["summary"]["enabled_action_count"]
    action_count = 0
    action_id_count = 0
    supported_key_codes = _load_supported_key_codes(errors)
    if json_path.is_file():
        action_count, action_id_count = _validate_json(
            json_path, expected_action_count, supported_key_codes, errors
        )
        if hobl_runtime_check and not errors:
            _validate_hobl_runtime(scenario_name, json_path, errors)

    if errors:
        raise ScenarioValidationError("\n".join(errors))

    return {
        "scenario": scenario_name,
        "directory": str(directory),
        "generated_action_count": action_count,
        "unique_action_id_count": action_id_count,
        "include_actions": 0,
        "reusable_library_references": 0,
        "external_runtime_dependencies": 0,
        "status": "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an AI-authored self-contained HOBL scenario."
    )
    parser.add_argument("scenario_dir", help="Path to the generated scenario folder.")
    parser.add_argument(
        "--workbook",
        help="Optional source workbook used to validate scenario name, platform, and step count.",
    )
    parser.add_argument(
        "--hobl-runtime-check",
        action="store_true",
        help="Import the generated module and load its JSON through the HOBL runtime.",
    )
    args = parser.parse_args(argv)

    try:
        result = validate_scenario(
            args.scenario_dir,
            args.workbook,
            hobl_runtime_check=args.hobl_runtime_check,
        )
    except ScenarioValidationError as error:
        for line in str(error).splitlines():
            print(f" ERROR - {line}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
