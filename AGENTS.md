# Code Style

These conventions apply to project-owned Python, QML, installer scripts, and tests.
KiPng targets KiCad 10.0 on Windows with 64-bit Python 3.10–3.13 and PySide6.
Preserve behavior during style changes and leave generated files and downloaded
dependencies untouched.

## Formatting and Naming

- Use four-space indentation in Python and QML. Format Python with Ruff using
  [`pyproject.toml`](pyproject.toml), which sets a 100-character line length.
- Keep source files at or below 250 lines. Split larger files by responsibility.
  The test suite checks this limit.
- Use `snake_case` for Python modules, functions, and variables, `PascalCase`
  for classes and protocols, and `UPPER_SNAKE_CASE` for module-level constants.
  Use `PascalCase` for QML component filenames and `lowerCamelCase` for QML
  IDs, properties, functions, and signals.
- Separate logical steps with a blank line. Keep related statements together
  and put explanatory comments directly above the code they describe.

## Structure and Dependencies

- Keep `plugin/preview.py` as the thin KiCad launcher, with the manifest,
  icons, and runtime dependency list in `plugin/`.
- Use `src/kipng/app.py` to assemble the preview and manage its lifetime.
  Put shared data types, errors, and interfaces in `contracts/`, board capture
  and model export in `export/`, and Qt widgets and QML in `ui/`.
- Use `BoardSource` and `ModelExporter` where the application needs to swap
  implementations or substitute a test double. Keep KiCad IPC, subprocesses,
  and file operations out of the viewport code.
- The installer assembles the runtime package beside the KiCad manifest.
  Verify imports and QML asset paths from the installed layout when changing
  package structure.

## Comments and Contracts

- Use Python docstrings for module purpose and public contracts, and `#`
  comments for local implementation decisions. Use `//` comments in QML.
- Use type annotations on shared interfaces. Document ownership, lifetime,
  cancellation, and errors where callers need that information. Explain
  KiCad, Qt, or GLB constraints beside the code that handles them.
- Keep widget changes on the Qt GUI thread. Use the existing worker and
  cancellation flow for board capture and export, and release the viewport
  before removing its temporary model.
- Keep the original board and project files intact during preview. Use temporary
  copies and preserve project-relative model resolution.

## Control Flow

Use early returns for guards and keep the normal path at the outer indentation
level. Use context managers or `finally` blocks for temporary files and
subprocess cleanup. Preserve cancellation and actionable error messages.

```python
def show_workspace(self) -> None:
    if not self.viewport_timeout.isActive() or self.cancelled.is_set():
        return

    self.viewport_timeout.stop()
    self.stack.setCurrentWidget(self.workspace)
    self.loading.hide()
```

## Test Readability

- Break each multi-step test into logical blocks with a blank line between
  them. Give each block a short `#` comment immediately above it that names
  the scenario, action, or behavior being checked.
- Separate fixture setup, the operation under test, and its assertions.
  For tests with several transitions, group each action with the assertions
  for that transition and label the group.
- Inside test doubles and callbacks, separate argument checks, simulated
  behavior, and side effects into labeled blocks when they serve different
  purposes. Group assertions by the behavior they verify.
- Keep the scenario visible in the test. Extract repeated mechanics into
  fixtures or helpers, and give those helpers names that explain their role.
  A short, single-purpose test can read plainly without section comments.

```python
def test_unsaved_project_can_stage_in_fallback_directory(tmp_path):
    # Stage the unsaved board in the fallback directory.
    snapshot = BoardSnapshot("new board", None, "")
    with board.stage_board(snapshot, tmp_path) as staged:
        assert staged.parent == tmp_path
        assert staged.read_text(encoding="utf-8") == "new board"

    # The temporary board is removed when staging ends.
    assert not list(tmp_path.iterdir())
```

## Validation

Run the relevant checks from the workspace root. Development setup is in
[README.md](README.md).

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Tests should use temporary directories and run without a live KiCad session.
Use test doubles at IPC and exporter boundaries where needed and keep Qt tests
compatible with the offscreen platform. The
[Windows CI workflow](.github/workflows/ci.yml) checks Python 3.10 and 3.13.
For changes affecting KiCad integration, installation, or viewport behavior,
also smoke-test the affected path in KiCad 10.0 when available. Report live
KiCad checks separately from automated tests.
