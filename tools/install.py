#!/usr/bin/env python3
"""Copy the two GHES templates into an existing checkout or staging directory."""

import argparse
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates" / "ghes"
TEMPLATE_FILES = (
    ".github/workflows/copilot-review.yml",
    ".github/scripts/build_review_payload.py",
)


class InstallError(Exception):
    """A target cannot safely receive the templates."""


def is_link(path: Path) -> bool:
    try:
        attributes = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(attributes.st_mode) or bool(
        getattr(attributes, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def check_destination(target: Path, relative: str) -> Path:
    current = target
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        if is_link(current):
            raise InstallError(f"Refusing linked target path: {relative}")
        if current.exists():
            if index < len(parts) - 1 and not current.is_dir():
                raise InstallError(f"Parent is not a directory: {relative}")
            if index == len(parts) - 1 and not current.is_file():
                raise InstallError(f"Destination is not a regular file: {relative}")
    return current


def install(target: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    target = target.expanduser()
    if not target.is_dir():
        raise InstallError("Target must be an existing directory")
    target = target.resolve(strict=True)
    if target == ROOT:
        raise InstallError("Refusing to install into the distribution repository")

    plan: list[tuple[str, Path, bytes, bool]] = []
    conflicts = []
    for relative in TEMPLATE_FILES:
        source = TEMPLATE_ROOT / relative
        if is_link(source) or not source.is_file():
            raise InstallError(f"Missing or linked template: {relative}")
        data = source.read_bytes()
        destination = check_destination(target, relative)
        exists = destination.exists()
        if exists and destination.read_bytes() != data:
            conflicts.append(relative)
        plan.append((relative, destination, data, exists))

    if conflicts:
        raise InstallError(
            "Existing files have different content; nothing was copied:\n  "
            + "\n  ".join(conflicts)
            + "\nExport to an empty staging directory and compare manually."
        )

    result = []
    for relative, destination, data, exists in plan:
        if exists:
            status = "unchanged"
        elif dry_run:
            status = "would-copy"
        else:
            check_destination(target, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation also refuses a file created after preflight.
            with destination.open("xb") as output:
                output.write(data)
            status = "copied"
        result.append((status, relative))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", type=Path, required=True,
        help="Existing local client checkout or empty staging directory",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check all paths and report the plan without creating anything",
    )
    args = parser.parse_args()
    try:
        if not args.target.is_dir():
            raise InstallError("Target must be an existing directory")
        result = install(args.target, dry_run=args.dry_run)
    except (InstallError, OSError) as error:
        parser.exit(
            1, f"Installation stopped: {error}\n"
            "Existing files were never overwritten. A filesystem error may "
            "leave newly copied files; rerun after resolving it.\n",
        )
    for status, relative in result:
        print(f"{status.upper():10} {relative}")


if __name__ == "__main__":
    main()
