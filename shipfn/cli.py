"""`shipfn manifest` and `shipfn run` are what the platform calls inside the image; the rest are for builders
(and their coding agents: `--json` gives one parseable object on stdout)."""
import argparse
import contextlib
import json
import sys
import traceback
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipfn", description="Deploy Python functions as forms for your team.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Find the problems a deploy would hit, with fixes (exit 1 on errors)")
    p_check.add_argument("--root", default=".")
    p_check.add_argument("--json", action="store_true", help="Print one JSON object instead of text")

    p_local = sub.add_parser("local", help="Run a function by name on this machine")
    p_local.add_argument("name")
    p_local.add_argument("--root", default=".")
    p_local.add_argument("--input", "-i", action="append", default=[], metavar="KEY=VALUE",
                         help="An input value; JSON is parsed when it can be (-i days=7 -i region=NA), "
                              "and @path passes a file (-i sheet=@data.csv)")
    p_local.add_argument("--json", action="store_true",
                         help="Print one JSON object on stdout (the function's own output goes to stderr)")

    p_manifest = sub.add_parser("manifest", help="Print the JSON manifest of every @deploy function")
    p_manifest.add_argument("--root", default=".")

    sub.add_parser("docs", help="Print the guide to writing automations (for people and coding agents)")

    p_init = sub.add_parser("init", help="Add an example automation and coding-agent instructions to this repo")
    p_init.add_argument("--root", default=".")
    p_init.add_argument("--no-example", action="store_true", help="Only write the agent instructions")
    p_init.add_argument("--no-agents", action="store_true", help="Skip the agent instructions")

    p_run = sub.add_parser("run", help="(Used by the platform) run one function with inputs from $SHIPFN_INPUTS")
    p_run.add_argument("entrypoint", help="module:function")
    p_run.add_argument("--root", default=".")

    args = parser.parse_args(argv)

    if args.command == "docs":
        from shipfn.init import guide

        print(guide())
        return 0

    root = Path(args.root).resolve()

    if args.command == "manifest":
        from shipfn.manifest import build_manifest

        print(json.dumps(build_manifest(root)))
        return 0

    if args.command == "run":
        from shipfn.runtime import run

        return run(args.entrypoint, root)

    if args.command == "check":
        return _check(root, args.json)

    if args.command == "local":
        return _local(root, args.name, args.input, args.json)

    if args.command == "init":
        from shipfn.init import init_project

        for path, what in init_project(root, example=not args.no_example, agents=not args.no_agents):
            print(f"  {what:<10} {path}")
        print("\nNext: `shipfn check`, then `shipfn local <name>` to try a function. Push to deploy.")
        return 0

    return 1


def _check(root: Path, as_json: bool) -> int:
    from shipfn.checks import check_project

    # Imports run user code; keep its prints off stdout so --json stays parseable
    with contextlib.redirect_stdout(sys.stderr):
        report = check_project(root)
    if as_json:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    for fn in report["functions"]:
        print(f"  {fn['name']}  ({', '.join(fn['inputs']) or 'no inputs'}) -> {fn['output_kind']}")
    if report["functions"]:
        print()
    for issue in report["issues"]:
        where = f"[{issue['function']}] " if issue.get("function") else ""
        print(f"{issue['level']}: {where}{issue['message']}")
        if issue.get("fix"):
            print(f"  fix: {issue['fix']}")
    errors = sum(i["level"] == "error" for i in report["issues"])
    warnings = len(report["issues"]) - errors
    if errors:
        print(f"\n{errors} error(s), {warnings} warning(s). A deploy would fail.")
    else:
        print(f"{'' if not report['issues'] else chr(10)}Ready to deploy"
              f"{f' ({warnings} warning(s))' if warnings else ''}.")
    return 0 if report["ok"] else 1


def _parse_inputs(pairs: list[str]) -> dict:
    inputs = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if raw.startswith("@"):  # -i sheet=@data.csv passes a file
            inputs[key] = raw[1:]
            continue
        try:
            inputs[key] = json.loads(raw)
        except json.JSONDecodeError:
            inputs[key] = raw
    return inputs


def _field_errors(exc) -> dict[str, str]:
    return {".".join(str(p) for p in err["loc"]) or "inputs": err["msg"] for err in exc.errors()}


def _local(root: Path, name: str, pairs: list[str], as_json: bool) -> int:
    from pydantic import ValidationError

    from shipfn.decorator import registry
    from shipfn.files import output_dir, saved_files
    from shipfn.manifest import build_manifest
    from shipfn.runtime import finish

    stdout = sys.stdout  # the real one, even while user code's prints are redirected

    def report(payload: dict) -> int:
        if as_json:
            print(json.dumps(payload, indent=2, default=str), file=stdout)
        return 0 if payload["ok"] else 1

    # In --json mode everything the user's code prints goes to stderr
    out = contextlib.redirect_stdout(sys.stderr) if as_json else contextlib.nullcontext()
    with out:
        manifest = build_manifest(root)
        for err in manifest["errors"]:
            print(f"warning: {err.get('module') or err.get('function')}: {err['error']}", file=sys.stderr)
        if name not in registry:
            message = f"No function named '{name}'. Found: {', '.join(sorted(registry)) or 'none'}"
            if not as_json:
                print(message, file=sys.stderr)
            return report({"ok": False, "error": message, "import_errors": manifest["errors"]})
        try:
            result = finish(registry[name].call(_parse_inputs(pairs)))
        except ValidationError as exc:
            fields = _field_errors(exc)
            if not as_json:
                print("Some inputs aren't valid:", file=sys.stderr)
                for field, msg in fields.items():
                    print(f"  {field}: {msg}", file=sys.stderr)
            return report({"ok": False, "error": "Some inputs aren't valid", "field_errors": fields})
        except Exception as exc:
            traceback.print_exc()
            return report({"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(),
                           "files": saved_files()})
        files = [{**f, "local_path": str(output_dir() / f["path"])} for f in saved_files()]

    if as_json:
        return report({"ok": True, "value": result, "files": files})
    if result is not None:
        print(result if isinstance(result, str) else json.dumps(result, indent=2))
    if files:
        print("\nFiles:", file=sys.stderr)
        for f in files:
            print(f"  {f['local_path']}  ({f['size']:,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
