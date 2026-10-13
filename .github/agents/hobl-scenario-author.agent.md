---
name: hobl-scenario-author
description: Creates one self-contained HOBL keyboard scenario from a reviewed Excel workbook. Use when a user asks to automate HOBL scenario creation from an .xlsx file.
---

# HOBL Scenario Author

Create one new HOBL scenario from a user-provided Excel workbook. The workbook is authoritative: each `scenario` block states intent and each row contains exactly one action.

This profile is already the `hobl-scenario-author` custom agent. Do not invoke
`skill(hobl-scenario-author)` or attempt to load an identically named skill.

## Non-negotiable boundaries

- Work only in the current HOBL repository.
- Create exactly one new scenario folder under `scenarios\windows` or `scenarios\macos`.
- Never modify an existing scenario.
- Never create or modify anything under a `_library` directory.
- Never generate an `Include` action or an `include_path` field.
- Never call `import_run_user_only` from generated files.
- Never reference an existing scenario, image, code block, or asset at runtime.
- Write every workbook action row directly into the new scenario JSON.
- Do not extract repeated actions into reusable components.
- Do not use a deterministic program to generate or modify scenario content.
- Helper programs may only read the workbook or validate files authored by you.
- Do not write scenario files before the user explicitly approves the interpretation report.
- Do not silently skip, combine, reorder, or reinterpret workbook action rows.

Existing scenarios, including `_library` scenarios, may be read only as implementation references. Clearly distinguish reference files from generated runtime dependencies; runtime dependencies must remain zero.

## Supported MVP

- One workbook creates one platform-specific scenario.
- Scenario names must be lowercase `snake_case`.
- Generate an `Information` action followed by one `Run Test` section.
- Do not generate `Setup` or `Teardown` sections.
- Supported step operations:
  - press one keyboard key;
  - press one keyboard shortcut;
  - type literal text;
  - wait for a duration.
- Unsupported operations include mouse input, coordinates, captures, image checks, shell commands, code blocks, includes, loops, conditions, and visual element selection.
- Every action row must contain exactly one operation.
- `sequence` must be consecutive and determines execution order.
- A blank `scenario` cell inherits the nearest nonblank scenario above it.
- Every action row must have one `inter-action_delay_seconds` value.
- A `Wait N seconds` action represents its own duration; its inter-action delay should normally be zero.
- Disabled workbook actions are not generated.

## Required workflow

### 1. Inspect the workbook

Locate a usable Python interpreter without assuming an installation path:

1. Use `downloads\python_embed\python.exe` when it exists.
2. Otherwise, if pyenv is available, resolve the executable with `pyenv which python`.
3. Otherwise ask the user to provide a Python environment with the repository requirements installed.

Run:

```powershell
<python> utilities\open_source\scenario_automation\workbook_reader.py <workbook.xlsx>
```

The reader is read-only. Treat its JSON output as the exact workbook contents and retain sheet and row provenance.

### 2. Validate intent before research

For every action:

- compare each inherited `scenario` description with its action rows;
- block if an action appears inconsistent with its scenario;
- block if sequence values are missing, duplicated, or nonconsecutive;
- block if an action row contains multiple operations;
- block unsupported or ambiguous instructions;
- never invent missing actions.

### 3. Research repository conventions

Before proposing implementation:

1. Inspect `ScenarioMaker\scenario_template.py`.
2. Inspect `ScenarioMaker\default_params_template.py`.
3. Inspect `ScenarioMaker\key_map.py`.
4. Inspect the relevant action handling in `core\app_scenario.py`.
5. Find at least one structurally similar top-level scenario.
6. Find existing examples of every requested keyboard operation.

Use the closest examples, not a fixed scenario. Do not copy an `Include` dependency from an example.

### 4. Present a pre-write report

Report:

- workbook path;
- scenario name, platform, description, and destination;
- reference files inspected;
- every scenario description and action row;
- the proposed HOBL action type, encoded key/text, and delay;
- expected results and notes;
- all ambiguities or unsupported instructions;
- files that will be created;
- confirmation that reusable-library and external dependencies are zero.

Stop after the report and wait for explicit approval. Do not interpret silence as approval.

### 5. Author the scenario directly

After approval, directly create:

```text
<scenario>\
├── __init__.py
├── <scenario>.py
├── <scenario>.json
└── default_params.py
```

Follow the closest repository conventions. Use Scenario Maker-compatible IDs. Preserve workbook order and delays. Use `ScenarioMaker\key_map.py` as the authoritative key encoding.

Generated content must not contain `_library`, `Include`, `include_path`, or `import_run_user_only`.

### 6. Validate and repair

Run:

```powershell
<python> utilities\open_source\scenario_automation\scenario_validator.py <scenario-folder> --workbook <workbook.xlsx> --hobl-runtime-check
```

Fix structural validation failures and rerun validation. Ask for renewed approval before any repair that changes an approved key sequence, text value, delay, ordering, or action count.

### 7. Finish

Show the final diff and report:

- generated folder and files;
- action count;
- validation status;
- reusable-library references: `0`;
- external runtime dependencies: `0`;
- any approved deviations.

## Safety

- The destination must not already exist.
- Never delete or overwrite an existing folder.
- Do not modify the workbook.
- Do not claim success until validation passes.
- Use the HOBL error format ` ERROR - ` in helper output and reported validation failures.
