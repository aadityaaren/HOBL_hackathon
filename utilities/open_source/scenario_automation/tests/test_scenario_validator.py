# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from utilities.open_source.scenario_automation.scenario_validator import (
    ScenarioValidationError,
    validate_scenario,
)


SCENARIO_PY = """\
import core.app_scenario
import os
from . import default_params

class PowerpointLaunch(core.app_scenario.Scenario):
    default_params.run()
    actions = None

    def setUp(self):
        actions_json = os.path.join(os.path.dirname(__file__), "powerpoint_launch.json")
        self.actions = self.load_action_json(actions_json)
        core.app_scenario.Scenario.setUp(self)

    def runTest(self):
        run_test = self._find_next_type("Run Test", json=self.actions)
        if run_test:
            self.run_actions(run_test["children"])

    def tearDown(self):
        core.app_scenario.Scenario.tearDown(self)

    def kill(self):
        return
"""

DEFAULT_PARAMS_PY = """\
from core.parameters import Params

def run():
    Params.setCalculated('scenario_section', __package__.split('.')[-1])
    return
"""


def scenario_json(include=False):
    child = {
        "children": [],
        "delay": "1",
        "description": "Open PowerPoint - Press Win+S",
        "enabled": True,
        "id": "W2HK7K",
        "text": "\ue03ds",
        "type": "Type",
        "typing_delay": "[typing_delay]",
    }
    if include:
        child = {
            "children": [],
            "delay": "0",
            "description": "Forbidden include",
            "enabled": True,
            "id": "W2HK7K",
            "include_path": "scenarios\\windows\\_library\\productivity",
            "type": "Include",
        }
    return [
        {
            "author": "Test Author",
            "capture_device": "Test Device",
            "children": [],
            "create_date": "2026-09-09",
            "description": "Launch PowerPoint",
            "enabled": True,
            "id": "U14J6M",
            "type": "Information",
        },
        {
            "children": [child],
            "description": "",
            "enabled": True,
            "id": "U14N1V",
            "type": "Run Test",
        },
    ]


def create_scenario(root: Path, *, include=False):
    directory = root / "scenarios" / "windows" / "powerpoint_launch"
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text(
        "from .powerpoint_launch import *", encoding="utf-8"
    )
    (directory / "powerpoint_launch.py").write_text(SCENARIO_PY, encoding="utf-8")
    (directory / "default_params.py").write_text(
        DEFAULT_PARAMS_PY, encoding="utf-8"
    )
    (directory / "powerpoint_launch.json").write_text(
        json.dumps(scenario_json(include=include), indent=4), encoding="utf-8"
    )
    return directory


def create_workbook(path: Path, action_count=1):
    workbook = Workbook()
    scenario = workbook.active
    scenario.title = "Scenario"
    scenario.append(["field", "value"])
    scenario.append(["name", "powerpoint_launch"])
    scenario.append(["platform", "Windows"])
    scenario.append(["description", "Launch PowerPoint"])
    scenario.append(["typing_delay_ms", 100])

    actions = workbook.create_sheet("Actions")
    actions.append(
        [
            "sequence",
            "scenario",
            "actions",
            "inter-action_delay_seconds",
            "expected_result",
            "enabled",
            "notes",
        ]
    )
    for sequence in range(1, action_count + 1):
        actions.append(
            [
                sequence,
                "Open PowerPoint" if sequence == 1 else "",
                "Press Win+S",
                1,
                "",
                True,
                "",
            ]
        )
    workbook.save(path)
    workbook.close()


class ScenarioValidatorTests(unittest.TestCase):
    def test_accepts_valid_self_contained_scenario(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))

            result = validate_scenario(directory)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["include_actions"], 0)
            self.assertEqual(result["reusable_library_references"], 0)

    def test_rejects_include_action(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root), include=True)

            with self.assertRaisesRegex(
                ScenarioValidationError, "forbidden|unsupported"
            ):
                validate_scenario(directory)

    def test_rejects_unexpected_external_file(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            (directory / "image_external.png").write_bytes(b"not an image")

            with self.assertRaisesRegex(ScenarioValidationError, "Unexpected file"):
                validate_scenario(directory)

    def test_rejects_duplicate_action_ids(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            path = directory / "powerpoint_launch.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data[1]["id"] = data[0]["id"]
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ScenarioValidationError, "Duplicate action ID"):
                validate_scenario(directory)

    def test_rejects_unsupported_special_key_code(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            path = directory / "powerpoint_launch.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data[1]["children"][0]["text"] = "\ue099"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(
                ScenarioValidationError, "unsupported special key"
            ):
                validate_scenario(directory)

    def test_rejects_reversed_top_level_sections(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            path = directory / "powerpoint_launch.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data.reverse()
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(
                ScenarioValidationError, "Information followed by Run Test"
            ):
                validate_scenario(directory)

    def test_rejects_nested_library_reference(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            path = directory / "powerpoint_launch.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data[0]["metadata"] = {"reference": "scenarios\\windows\\_library\\sample"}
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ScenarioValidationError, "_library"):
                validate_scenario(directory)

    def test_rejects_external_python_import(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            path = directory / "powerpoint_launch.py"
            path.write_text(
                f"import requests\n{path.read_text(encoding='utf-8')}",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ScenarioValidationError, "unsupported runtime dependency"
            ):
                validate_scenario(directory)

    def test_validates_action_count_against_flat_workbook_rows(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            directory = create_scenario(root_path)
            workbook_path = root_path / "scenario.xlsx"
            create_workbook(workbook_path)

            result = validate_scenario(directory, workbook_path)

            self.assertEqual(result["generated_action_count"], 1)

    def test_rejects_workbook_action_count_mismatch(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            directory = create_scenario(root_path)
            workbook_path = root_path / "scenario.xlsx"
            create_workbook(workbook_path, action_count=2)

            with self.assertRaisesRegex(
                ScenarioValidationError, "2 enabled actions"
            ):
                validate_scenario(directory, workbook_path)

    def test_validator_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as root:
            directory = create_scenario(Path(root))
            before = {
                path.name: path.read_bytes()
                for path in directory.iterdir()
                if path.is_file()
            }

            validate_scenario(directory)

            after = {
                path.name: path.read_bytes()
                for path in directory.iterdir()
                if path.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
