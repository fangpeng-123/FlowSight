"""Project-local Reading Subject Catalog.

Reading subjects are Agent-authored, advisory groupings layered onto the
parser-derived graph.  The parser graph remains the source of structural truth;
this module only validates subject ownership and annotates matching module
nodes so the browser can expose the explicit deep-read action.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from flowsight import schema as S

CATALOG_VERSION = 1
CATALOG_PATH = Path(".flowsight") / "reading-subjects.json"
LOCKS_PATH = Path(".flowsight") / "reading-subject-locks.json"
EXCLUDED_ROOT_NAMES = frozenset(
    {
        ".git", ".hg", ".svn", ".tox", ".mypy_cache", ".pytest_cache",
        "__pycache__", "node_modules", "build", "dist", ".eggs",
    }
)


class CatalogValidationError(ValueError):
    """The Agent-authored catalog is unsafe or inconsistent."""


@dataclass(frozen=True)
class ReadingSubject:
    id: str
    label: str
    root: str
    member_files: tuple[str, ...]
    exclusions: tuple[str, ...]
    rationale: str
    locked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "root": self.root,
            "member_files": list(self.member_files),
            "exclusions": list(self.exclusions),
            "rationale": self.rationale,
            "locked": self.locked,
        }


@dataclass(frozen=True)
class ReadingSubjectCatalog:
    version: int = CATALOG_VERSION
    subjects: tuple[ReadingSubject, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "subjects": [s.to_dict() for s in self.subjects]}


def load_catalog(
    project_path: str | os.PathLike[str],
    *,
    previous: ReadingSubjectCatalog | None = None,
) -> ReadingSubjectCatalog:
    """Load and validate ``.flowsight/reading-subjects.json``.

    A missing catalog is an empty advisory layer, preserving existing FlowSight
    behavior.  Locked subjects from ``previous`` win over a later Agent refresh
    and survive if the refresh omits them.
    """

    project = Path(project_path).resolve()
    incoming = _read_catalog(project, project / CATALOG_PATH)
    persisted = _read_catalog(project, project / LOCKS_PATH)
    subjects = _merge_locked(persisted, incoming)
    subjects = _merge_locked(previous, ReadingSubjectCatalog(subjects=subjects))
    _validate_unique(subjects)
    result = ReadingSubjectCatalog(version=CATALOG_VERSION, subjects=subjects)
    _persist_locks(project, result)
    return result


def apply_catalog(doc: S.GraphDocument, catalog: ReadingSubjectCatalog) -> None:
    """Attach advisory subjects to exact parser module nodes in ``doc``."""

    modules_by_root: dict[str, S.Node] = {}
    files_by_id = {n.id: n for n in doc.nodes if n.type == S.FILE}
    assignments: list[tuple[ReadingSubject, list[S.Node]]] = []
    for node in doc.nodes:
        if node.type == S.MODULE:
            dotted = str(node.attrs.get("dotted", ""))
            modules_by_root[dotted.replace(".", "/")] = node
            node.attrs.pop("reading_subject", None)
        elif node.type == S.FILE:
            node.attrs.pop("reading_subject_id", None)
            node.attrs.pop("reading_subject", None)

    for subject in catalog.subjects:
        missing_graph_files = [path for path in subject.member_files if f"file:{path}" not in files_by_id]
        if missing_graph_files:
            raise CatalogValidationError(
                f"subject {subject.id!r} member files do not map to parser file nodes: "
                + ", ".join(missing_graph_files)
            )
        exact_module = modules_by_root.get(subject.root)
        anchors = [exact_module] if exact_module is not None else [
            files_by_id[f"file:{path}"] for path in subject.member_files
        ]
        assignments.append((subject, anchors))

    for subject, anchors in assignments:
        for path in subject.member_files:
            files_by_id[f"file:{path}"].attrs["reading_subject_id"] = subject.id
        for anchor in anchors:
            anchor.attrs["reading_subject"] = subject.to_dict()

    doc.project["reading_subjects"] = [subject.to_dict() for subject in catalog.subjects]


def _catalog_from_dict(project: Path, raw: Any) -> ReadingSubjectCatalog:
    if not isinstance(raw, dict):
        raise CatalogValidationError("catalog must be a JSON object")
    version = raw.get("version")
    if version != CATALOG_VERSION:
        raise CatalogValidationError(
            f"unsupported catalog version {version!r}; expected {CATALOG_VERSION}"
        )
    raw_subjects = raw.get("subjects")
    if not isinstance(raw_subjects, list):
        raise CatalogValidationError("catalog subjects must be a list")

    subjects = tuple(_subject_from_dict(project, item, index) for index, item in enumerate(raw_subjects))
    _validate_unique(subjects)
    return ReadingSubjectCatalog(version=version, subjects=subjects)


def _read_catalog(project: Path, path: Path) -> ReadingSubjectCatalog:
    if not path.is_file():
        return ReadingSubjectCatalog()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"invalid catalog JSON at {path}: {exc}") from exc
    return _catalog_from_dict(project, raw)


def _subject_from_dict(project: Path, raw: Any, index: int) -> ReadingSubject:
    prefix = f"subject[{index}]"
    if not isinstance(raw, dict):
        raise CatalogValidationError(f"{prefix} must be an object")

    root = _normalize_relative(raw.get("root"), f"{prefix}.root")
    subject_id = raw.get("id")
    if subject_id != root:
        raise CatalogValidationError(
            f"{prefix} stable id must equal normalized root {root!r}"
        )
    label = _required_text(raw.get("label"), f"{prefix}.label")
    rationale = _required_text(raw.get("rationale"), f"{prefix}.rationale")
    locked = raw.get("locked", False)
    if not isinstance(locked, bool):
        raise CatalogValidationError(f"{prefix}.locked must be a boolean")

    if any(part.startswith(".") or part in EXCLUDED_ROOT_NAMES for part in PurePosixPath(root).parts):
        raise CatalogValidationError(f"{prefix}.root is excluded by project policy: {root!r}")
    _require_project_path(project, root, kind="root folder", directory=True)
    raw_members = raw.get("member_files")
    if not isinstance(raw_members, list) or not raw_members:
        raise CatalogValidationError(f"{prefix}.member_files must be a non-empty list")
    members = tuple(
        _normalize_relative(member, f"{prefix}.member_files[{member_index}]")
        for member_index, member in enumerate(raw_members)
    )
    if len(set(os.path.normcase(member) for member in members)) != len(members):
        raise CatalogValidationError(f"{prefix} contains a duplicate member file")
    for member in members:
        _require_project_path(project, member, kind="member file", directory=False)

    raw_exclusions = raw.get("exclusions", [])
    if not isinstance(raw_exclusions, list):
        raise CatalogValidationError(f"{prefix}.exclusions must be a list")
    exclusions = tuple(
        _normalize_relative(exclusion, f"{prefix}.exclusions[{exclusion_index}]")
        for exclusion_index, exclusion in enumerate(raw_exclusions)
    )
    root_prefix = root + "/"
    if any(exclusion != root and not exclusion.startswith(root_prefix) for exclusion in exclusions):
        raise CatalogValidationError(f"{prefix}.exclusions must stay within subject root {root!r}")
    for member in members:
        if any(member == exclusion or member.startswith(exclusion + "/") for exclusion in exclusions):
            raise CatalogValidationError(f"{prefix} member file is excluded: {member!r}")

    return ReadingSubject(
        id=subject_id,
        label=label,
        root=root,
        member_files=members,
        exclusions=exclusions,
        rationale=rationale,
        locked=locked,
    )


def _normalize_relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{field} must be a non-empty string")
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:/", candidate)
        or any(part == ".." for part in path.parts)
    ):
        raise CatalogValidationError(f"{field} is outside the project: {value!r}")
    normalized = path.as_posix().rstrip("/")
    if normalized in {"", "."}:
        raise CatalogValidationError(f"{field} must name a folder or file inside the project")
    return normalized


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _require_project_path(project: Path, relative: str, *, kind: str, directory: bool) -> None:
    resolved = (project / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise CatalogValidationError(f"{kind} is outside the project: {relative!r}") from exc
    valid = resolved.is_dir() if directory else resolved.is_file()
    if not valid:
        qualifier = "missing root folder" if directory else "missing member file"
        raise CatalogValidationError(f"{qualifier}: {relative!r}")


def _merge_locked(
    previous: ReadingSubjectCatalog | None,
    incoming: ReadingSubjectCatalog,
) -> tuple[ReadingSubject, ...]:
    if previous is None:
        return incoming.subjects
    locked = {subject.id: subject for subject in previous.subjects if subject.locked}
    merged = [locked.pop(subject.id, subject) for subject in incoming.subjects]
    merged.extend(subject for subject in previous.subjects if subject.id in locked)
    return tuple(merged)


def _persist_locks(project: Path, catalog: ReadingSubjectCatalog) -> None:
    locked = tuple(subject for subject in catalog.subjects if subject.locked)
    if not locked:
        return
    path = project / LOCKS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = ReadingSubjectCatalog(subjects=locked).to_dict()
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _validate_unique(subjects: tuple[ReadingSubject, ...]) -> None:
    ids: set[str] = set()
    owners: dict[str, str] = {}
    for subject in subjects:
        if subject.id in ids:
            raise CatalogValidationError(f"duplicate subject id: {subject.id!r}")
        ids.add(subject.id)
        for member in subject.member_files:
            key = os.path.normcase(member)
            owner = owners.get(key)
            if owner is not None:
                raise CatalogValidationError(
                    f"duplicate primary ownership for {member!r}: {owner!r} and {subject.id!r}"
                )
            owners[key] = subject.id
