# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import math
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from utilities.open_source.scenario_automation.workbook_reader import (
    WorkbookValidationError,
    read_workbook,
)


def create_workbook(
    path: Path,
    *,
    action_rows=None,
    name="powerpoint_launch",
    typing_delay_ms=100,
):
    workbook = Workbook()
    scenario = workbook.active
    scenario.title = "Scenario"
    scenario.append(["Field", "Value"])
    scenario.append(["name", name])
    scenario.append(["platform", "Windows"])
    scenario.append(["description", "Launch and close PowerPoint"])
    scenario.append(["author", "Test Author"])
    scenario.append(["capture_device", "Test Device"])
    scenario.append(["typing_delay_ms", typing_delay_ms])

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
    for row in action_rows or [
        [1, "Open PowerPoint", "Press the Windows key", 1, "", True, ""],
        [2, "", "Type PowerPoint", 1, "", True, ""],
        [3, "", "Press Enter", 5, "PowerPoint opens", True, ""],
    ]:
        actions.append(row)

    workbook.save(path)
    workbook.close()


class WorkbookReaderTests(unittest.TestCase):
    def test_reads_valid_workbook_and_inherits_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(path)

            result = read_workbook(path)

            self.assertEqual(result["scenario"]["name"], "powerpoint_launch")
            self.assertEqual(
                result["summary"],
                {"action_count": 3, "enabled_action_count": 3},
            )
            self.assertEqual(result["actions"][1]["scenario"], "Open PowerPoint")
            self.assertEqual(result["actions"][2]["inter_action_delay_seconds"], 5)
            self.assertEqual(result["actions"][0]["source_row"], 2)

    def test_rejects_non_snake_case_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(path, name="PowerPointLaunch")

            with self.assertRaisesRegex(
                WorkbookValidationError, "lowercase snake_case"
            ):
                read_workbook(path)

    def test_rejects_nonconsecutive_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(
                path,
                action_rows=[
                    [1, "Open PowerPoint", "Press the Windows key", 1, "", True, ""],
                    [3, "", "Press Enter", 5, "PowerPoint opens", True, ""],
                ],
            )

            with self.assertRaisesRegex(
                WorkbookValidationError, "Sequence must be consecutive"
            ):
                read_workbook(path)

    def test_rejects_negative_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(
                path,
                action_rows=[
                    [1, "Open PowerPoint", "Press Enter", -1, "", True, ""]
                ],
            )

            with self.assertRaisesRegex(WorkbookValidationError, "nonnegative"):
                read_workbook(path)

    def test_rejects_nonfinite_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(
                path,
                action_rows=[
                    [1, "Open PowerPoint", "Press Enter", math.inf, "", True, ""]
                ],
            )

            with self.assertRaisesRegex(WorkbookValidationError, "nonnegative"):
                read_workbook(path)

    def test_rejects_first_row_without_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(
                path,
                action_rows=[[1, "", "Press Enter", 1, "", True, ""]],
            )

            with self.assertRaisesRegex(
                WorkbookValidationError, "no preceding scenario to inherit"
            ):
                read_workbook(path)

    def test_rejects_missing_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(
                path,
                action_rows=[[1, "Open PowerPoint", "", 1, "", True, ""]],
            )

            with self.assertRaisesRegex(WorkbookValidationError, "actions is required"):
                read_workbook(path)

    def test_rejects_fractional_typing_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(path, typing_delay_ms=1.5)

            with self.assertRaisesRegex(
                WorkbookValidationError, "nonnegative integer"
            ):
                read_workbook(path)

    def test_reader_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.xlsx"
            create_workbook(path)
            before = {entry.name for entry in Path(directory).iterdir()}

            read_workbook(path)

            after = {entry.name for entry in Path(directory).iterdir()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
