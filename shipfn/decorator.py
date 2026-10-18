import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from shipfn.schema import input_model, input_schema, output_kind


@dataclass
class DeployedFunction:
    func: Callable[..., Any]
    name: str
    title: str
    description: str
    secrets: list[str] = field(default_factory=list)
    schedule: str | None = None
    timeout: int = 300

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
            "secrets": self.secrets,
            "schedule": self.schedule,
            "timeout": self.timeout,
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
):
    """Mark a function as deployable. Works bare (`@deploy`) or with options (`@deploy(...)`)."""

    def wrap(f: Callable[..., Any]) -> Callable[..., Any]:
        fn_name = name or f.__name__
        doc = inspect.getdoc(f) or ""
        deployed = DeployedFunction(
            func=f,
            name=fn_name,
            title=title or fn_name.replace("_", " ").capitalize(),
            description=description or doc.split("\n\n")[0],
            secrets=list(secrets or []),
            schedule=schedule,
            timeout=timeout,
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
