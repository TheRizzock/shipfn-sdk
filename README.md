# shipfn

Turn Python functions into forms, schedules and run history your whole team can use. Decorate a function with `@deploy`, push the repo, and people run it from the Shipfn web app — no Python needed on their end.

```bash
pip install "shipfn @ git+https://github.com/<owner>/shipfn-sdk"
# or pin a release:
pip install "shipfn @ git+https://github.com/<owner>/shipfn-sdk@v0.1.0"
```

(Once it's on PyPI this becomes `pip install shipfn`.)

```python
from typing import Literal
from shipfn import deploy

@deploy(title="Weekly report", secrets=["SALES_API_TOKEN"], schedule="0 9 * * MON")
def weekly_report(region: Literal["NA", "EMEA", "APAC"] = "NA", days: int = 7) -> list[dict]:
    """Deals closed in the last N days."""
    ...
```

- **Inputs** come from the type hints: `str`, `int`, `float`, `bool`, `date`, `Literal[...]`/`Enum` (dropdowns), `list[...]`, optional (`X | None`) and Pydantic models. Defaults become prefilled values.
- **Results** are shown by return type: `str` as Markdown, `list[dict]` (or a DataFrame) as a table with CSV download, `dict`/Pydantic model as a key-value list, `None` as "done".
- **Files in**: a `File` parameter becomes an upload field. Your function gets a `File` with `.path`, `.name`, `.read_text()`, `.read_bytes()` and `.open()`. Limit the picker with `Annotated[File, accept(".csv", ".xlsx")]`.
- **Files out**: return a `File` (or a `list[File]`) and people get download buttons. To hand back files alongside another result, call `save_file(path_or_bytes, name=...)`. Files are kept for 24 hours by default.
- **Secrets** you list are injected as environment variables at run time (`os.environ["SALES_API_TOKEN"]`); set their values in the Shipfn console.
- **Schedules** are cron expressions, in UTC.

```python
from typing import Annotated
from shipfn import deploy, File, accept, save_file

@deploy(title="Clean up a sales sheet")
def clean(sheet: Annotated[File, accept(".csv")]) -> File:
    rows = sheet.read_text().splitlines()
    save_file(f"{len(rows)} rows".encode(), name="summary.txt")   # an extra download
    out = "/tmp/clean.csv"
    ...
    return File(out, name=f"clean-{sheet.name}")
```

Try a function on your machine before pushing:

```bash
shipfn check           # problems a deploy would hit, with fixes (exit 1 on errors)
shipfn weekly_report --region EMEA --days 30   # every function is also a CLI command
shipfn local weekly_report -i region=EMEA -i days=30
shipfn local clean -i sheet=@sales.csv     # @path passes a file; outputs land in ./shipfn-output/
shipfn manifest        # what the platform will see
```

## Coding agents

The SDK carries its own guide for Claude Code, Cursor, Codex and other agents:

```bash
shipfn init            # an example automation, .claude/skills/shipfn/SKILL.md and an AGENTS.md section
shipfn docs            # print the full guide
```

`shipfn check --json` and `shipfn local ... --json` print one JSON object on stdout, so an agent can check and run functions and read the result. Re-run `shipfn init` after upgrading the SDK to refresh the instructions. Your own files and the rest of AGENTS.md are left alone.

On the platform, builds use the server's own copy of this package, so you don't need to add `shipfn` to your `requirements.txt` (it's fine if you do).

## Developing the SDK

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The platform (shipfn-api) depends on this package and copies the installed version into every build, so a release only reaches deployed functions once the API is updated to it. See [RELEASING.md](RELEASING.md).
