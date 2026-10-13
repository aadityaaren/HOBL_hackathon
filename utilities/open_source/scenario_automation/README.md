# HOBL Scenario Automation

This folder contains read-only helpers and the standard workbook template used by the `hobl-scenario-author` Copilot CLI custom agent.

## Scope

The custom agent creates one new, self-contained keyboard scenario from an Excel workbook. It writes every step directly into the scenario JSON and does not create or use reusable `_library` components.

The helper programs do not generate or modify scenario files:

- `workbook_reader.py` extracts and structurally validates workbook contents.
- `scenario_validator.py` validates files authored directly by Copilot.

## Start the custom agent

From the repository root:

```text
copilot
/restart
/agent hobl-scenario-author
```

Then provide the workbook:

```text
Generate a HOBL scenario from @C:\path\to\scenario.xlsx
```

`hobl-scenario-author` is a **custom agent**, not a skill. Do not run
`skill(hobl-scenario-author)` or `/skills hobl-scenario-author`.

After adding or changing the agent file, use `/restart` or exit and reopen
Copilot CLI before selecting it. You can also start it directly:

```powershell
copilot --agent hobl-scenario-author --prompt `
    "Generate a HOBL scenario from @C:\path\to\scenario.xlsx"
```

## Workbook

Start with `templates\HOBL_Scenario_Automation_Template.xlsx`.

The `Scenario` sheet uses field/value rows:

| Field | Required |
|---|---|
| `name` | Yes; lowercase `snake_case` |
| `platform` | Yes; `Windows` or `macOS` |
| `description` | Yes |
| `author` | No |
| `capture_device` | No |
| `typing_delay_ms` | Yes; nonnegative |

The `Actions` sheet contains:

| Column | Meaning |
|---|---|
| `sequence` | Consecutive action number, starting at 1 |
| `scenario` | High-level description; enter it on the first row of a block and leave continuation rows blank |
| `actions` | One keyboard or wait operation without numbering |
| `inter-action_delay_seconds` | Nonnegative delay after this action |
| `expected_result` | Review-only expected outcome |
| `enabled` | `TRUE` or `FALSE`; blank means enabled |
| `notes` | Optional author context |

Example:

| sequence | scenario | actions | inter-action_delay_seconds |
|---:|---|---|---:|
| 1 | Launch PowerPoint | Press the Windows key | 1 |
| 2 |  | Type PowerPoint | 1 |
| 3 |  | Press Enter | 5 |

Each row must contain exactly one operation. A blank `scenario` cell inherits the nearest nonblank scenario above it.

## Read a workbook

Use the repository embedded Python when present. Otherwise resolve pyenv Python with `pyenv which python`.

```powershell
<python> utilities\open_source\scenario_automation\workbook_reader.py `
    C:\path\to\scenario.xlsx
```

The command writes normalized JSON to stdout and does not create files.

## Validate an authored scenario

```powershell
<python> utilities\open_source\scenario_automation\scenario_validator.py `
    scenarios\windows\powerpoint_launch `
    --workbook C:\path\to\scenario.xlsx `
    --hobl-runtime-check
```

Validation rejects includes, reusable-library references, external assets, unsupported action types, malformed files, and workbook/action-count mismatches.
