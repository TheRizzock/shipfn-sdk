import functools
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from shipfn.schema import input_model, input_schema, output_kind


GROUP_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
# Commands the CLI already has; a group can't share a name with them (`shipfn <group> <action>`)
RESERVED_GROUP_NAMES = {"check", "local", "manifest", "docs", "init", "run", "help"}


class Group:
    """A set of related actions, like a Typer sub-app: `shipfn <group> <action>` locally, and one section of the
    project in the web app. Secrets listed here are given to every action in the group.

        backups = Group("backups", title="Database backups", secrets=["SPACES_KEY"])

        @backups.deploy(title="Back up now")
        def run(env: Literal["prod", "staging"] = "prod") -> str: ...
    """

    def __init__(self, name: str, *, title: str | None = None, description: str = "",
                 secrets: list[str] | None = None):
        if not GROUP_NAME.match(name):
            raise ValueError(f"Group name '{name}' must be lowercase letters, digits, '-' or '_', starting with a "
                             "letter (it's typed as `shipfn <group> <action>`)")
        if name in RESERVED_GROUP_NAMES:
            raise ValueError(f"'{name}' is a shipfn command, so it can't be a group name")
        self.name = name
        self.title = title or name.replace("_", " ").replace("-", " ").capitalize()
        self.description = description
        self.secrets = list(secrets or [])

    def deploy(self, func: Callable[..., Any] | None = None, **options: Any):
        """`@deploy` for an action in this group; takes the same options. Its full name is `<group>.<name>`."""
        return deploy(func, _group=self, **options)

    def manifest_entry(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "description": self.description}

    def __repr__(self) -> str:
        return f"Group({self.name!r})"


@dataclass
class DeployedFunction:
    """What @deploy recorded about a function; `registry` maps full names (`group.action` or `action`) to these."""

    func: Callable[..., Any]
    name: str
    title: str
    description: str
    secrets: list[str] = field(default_factory=list)
    schedule: str | None = None
    timeout: int = 300
    group: Group | None = None
    action: str = ""  # the name within its group; the same as name when there's no group

    @property
    def all_secrets(self) -> list[str]:
        """The group's secrets, then the action's own, without repeats."""
        return list(dict.fromkeys([*(self.group.secrets if self.group else []), *self.secrets]))

    @property
    def entrypoint(self) -> str:
        return f"{self.func.__module__}:{self.func.__qualname__}"

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entrypoint": self.entrypoint,
            "title": self.title,
            "description": self.description,
            "input_schema": input_schema(self.func),
            "output_kind": output_kind(self.func),
            "secrets": self.all_secrets,
            "schedule": self.schedule,
            "timeout": self.timeout,
            "group": self.group.manifest_entry() if self.group else None,
            "action": self.action,
        }

    def call(self, inputs: dict[str, Any]) -> Any:
        """Validate raw JSON inputs against the signature (coercing dates, enums, models) and call."""
        validated = input_model(self.func).model_validate(inputs)
        kwargs = {name: getattr(validated, name) for name in validated.__class__.model_fields}
        return self.func(**kwargs)


# Every @deploy in an imported module lands here; `shipfn manifest` reads it.
registry: dict[str, DeployedFunction] = {}


def deploy(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    secrets: list[str] | None = None,
    schedule: str | None = None,
    timeout: int = 300,
    _group: Group | None = None,
):
    """Deploy a function to Shipfn: teammates run it from a web form generated from its type hints.

    Works bare (`@deploy`) or with options (`@deploy(title="Weekly report", secrets=["CRM_TOKEN"])`).

    Args:
        name: Identity on the platform (defaults to the function name). Changing it creates a new
            automation, so pass the old name here if you rename the Python function.
        title: Heading people see (defaults to the name as a sentence, e.g. "Weekly report").
        description: One line shown on the card (defaults to the docstring's first paragraph).
        secrets: Environment variable names to inject at run time; values are set in the web app.
            Read them inside the function with `os.environ["NAME"]`.
        schedule: Cron expression in UTC (e.g. "0 9 * * MON"). Every input needs a default.
            Usually unnecessary: anyone can schedule a function from the web app.
        timeout: Seconds before the run is stopped (default 300, platform maximum 900).

    Inputs: str, int, float, bool, date, datetime, Literal[...]/Enum (dropdown), list[...], X | None,
    Pydantic models and File (upload). Defaults make a field optional.

    Results by return annotation: str -> Markdown, list[dict] -> table, dict/model -> key-value list,
    File/list[File] -> downloads, None -> "Done".

    To organise related functions, deploy them through a `Group` instead: `@backups.deploy(...)`.

    Run `shipfn docs` for the full guide and `shipfn check` before pushing.
    """

    def wrap(f: Callable[..., Any]) -> Callable[..., Any]:
        action = name or f.__name__
        fn_name = f"{_group.name}.{action}" if _group else action
        doc = inspect.getdoc(f) or ""
        deployed = DeployedFunction(
            func=f,
            name=fn_name,
            title=title or action.replace("_", " ").capitalize(),
            description=description or doc.split("\n\n")[0],
            secrets=list(secrets or []),
            schedule=schedule,
            timeout=timeout,
            group=_group,
            action=action,
        )
        existing = registry.get(fn_name)
        if existing and existing.entrypoint != deployed.entrypoint:
            raise ValueError(
                f"Two functions are deployed as '{fn_name}': {existing.entrypoint} and {deployed.entrypoint}. "
                "Pass name='...' to one of them."
            )
        registry[fn_name] = deployed

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)

        wrapper.__shipfn__ = deployed
        return wrapper

    return wrap(func) if func is not None else wrap
