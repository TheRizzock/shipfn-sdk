# Writing Shipfn automations

Shipfn turns Python functions into web forms that non-technical teammates run. A developer decorates a function with `@deploy` and pushes the repo. The platform builds it and shows each function as a form, generated from the type hints, with run history. People can also schedule runs from the web app.

The person running an automation can't see the code, a traceback or a terminal. Everything they see comes from the decorator, the docstring, the parameter names and types, and the return value. Write for them.

## The loop

1. Write or change a function decorated with `@deploy`.
2. `shipfn check` (or `shipfn check --json`) lists every problem a deploy would hit, with a fix for each. Exit code 1 means the deploy would fail.
3. `shipfn local <name> -i key=value --json` runs the function on this machine, with the same input validation as the platform.
4. Push. The platform builds and deploys on push.

Run `shipfn check` before every push. If any module fails to import, nothing is published.

## Anatomy

```python
from datetime import date
from typing import Literal

from shipfn import deploy


@deploy(title="Closed deals", secrets=["CRM_TOKEN"], timeout=120)
def closed_deals(region: Literal["NA", "EMEA", "APAC"] = "NA", since: date | None = None,
                 min_value: int = 0) -> list[dict]:
    """Deals closed in a region, newest first.

    Pulls from the CRM; amounts are in USD.
    """
    ...
```

- `name`: the function's identity on the platform. It defaults to the function name. **Renaming it creates a new automation**, and the old one's history and schedules stay behind. Pass `name="..."` to keep the identity if you rename the Python function.
- `title`: the card and page heading. It defaults to the name, turned into a sentence.
- `description`: the first paragraph of the docstring is the default. Write one plain-language sentence about what it does for the person.
- `secrets`: names of environment variables, which builders set in the web app. Read them with `os.environ["CRM_TOKEN"]`. Never hard-code credentials and never take them as inputs.
- `timeout`: in seconds. The default is 300 and the maximum is 900.
- `schedule`: a cron expression in UTC, for schedules owned by the code. Only use it when the user asks for one. Anyone can add a schedule in the web app, so you usually don't need it.

## Inputs: type hints become the form

| Type hint | Form field |
|---|---|
| `str` | text box |
| `int`, `float` | number |
| `bool` | checkbox |
| `date`, `datetime` | date or date-time picker |
| `Literal["a", "b"]` or an `Enum` | dropdown |
| `list[str]` and so on | list editor |
| `X \| None = None` | optional field |
| a Pydantic model | grouped sub-form |
| `File`, or `Annotated[File, accept(".csv")]` | file upload |

- A default value makes the field optional and prefills it. A parameter without a default is required.
- Parameter names become labels: `min_value` shows as "Min value". Choose names that read well.
- Prefer `Literal[...]` over free text whenever the valid values are known.
- Not supported: `*args`, `**kwargs`, `Callable` or arbitrary classes. `shipfn check` names the offending parameter.
- Avoid `dict` inputs. They show as a raw JSON box, so use a Pydantic model instead.
- Inputs are validated and coerced before your function runs. A `date` arrives as a `datetime.date`, and a model arrives as an instance.

## Results: the return type picks the display

| Return annotation | Shown as |
|---|---|
| `-> str` | Markdown (headings, lists, links and tables work) |
| `-> list[dict]`, a list of models, or a DataFrame | a table with CSV download |
| `-> dict` or a Pydantic model | a key-value list |
| `-> File` or `-> list[File]` | download buttons |
| `-> None` | "Done" |
| missing or anything else | raw JSON (avoid this) |

Always annotate the return type. Keep table rows flat (scalar values) and use readable keys, because the keys become column headers.

## Files

```python
from typing import Annotated

from shipfn import File, accept, deploy, save_file


@deploy(title="Clean up a contact list")
def clean_contacts(sheet: Annotated[File, accept(".csv")]) -> File:
    """Removes duplicate rows and fixes capitalisation."""
    rows = sheet.read_text().splitlines()            # also: .read_bytes(), .open(), .path, .name, .size
    save_file(f"{len(rows)} rows in".encode(), name="summary.txt")   # an extra download
    out = "/tmp/clean.csv"
    ...
    return File(out, name=f"clean-{sheet.name}")
```

- A `File` parameter is an upload field. Use `accept(...)` to limit the file types.
- Returning `File` gives the person a download. `save_file(path_or_bytes, name=...)` adds more downloads alongside any return value. It needs `name=` when you pass bytes.
- Locally, pass a file with `-i sheet=@path/to/file.csv`. Outputs land in `./shipfn-output/`.
- Limits: 100 MB per upload, and 100 MB and 20 files of output per run. Files are deleted after 24 hours.
- Functions with file inputs can't be scheduled.

## Runtime environment

- Python 3.12 in a sandbox with 512 MB of memory and 1 CPU. It runs as a non-root user and has internet access.
- Dependencies come from `requirements.txt` at the repo root, or from `[project].dependencies` in `pyproject.toml`. **Don't list `shipfn`.** The platform installs its own matching copy.
- Writable space: `/tmp`, limited to 256 MB. Every run starts fresh, so nothing persists between runs. Keep state in your own database or storage.
- Every module that imports `shipfn` and mentions `deploy` is imported at build time. Keep import-time code cheap and free of side effects: no network calls, and no reading secrets at module level. Read secrets inside the function.
- `print()` output and `logging` show as the run's logs. Tracebacks are shown only to builders, never to the person running the automation.

## Errors people will see

Raise exceptions with messages written for the person running the automation. They see `ValueError: No deals found for EMEA since 2026-01-01`, so make it say what to change. For bad input, raise `ValueError` with a message about that field.

## Commands

- `shipfn check [--json]`: problems a deploy would hit, with fixes. Exit code 1 on errors.
- `shipfn local <name> [-i key=value ...] [--json]`: run a function on this machine. Values are parsed as JSON when possible, and `@path` passes a file. `--json` prints one JSON object on stdout (`ok`, `value`, `files`, `error`, `field_errors`), and the function's own prints go to stderr.
- `shipfn manifest`: the full JSON the platform reads, including each input's JSON Schema.
- `shipfn docs`: prints this guide.
- `shipfn init`: an example automation plus agent instructions (`.claude/skills/shipfn/SKILL.md` and an `AGENTS.md` section). Run it again after upgrading the SDK to refresh the instructions.
