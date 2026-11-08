"""Compare two integrity manifests part by part and aspect by aspect."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ocx_integrity.errors import ProfileMismatchError
from ocx_integrity.manifest import Manifest, ordered_ids
from ocx_integrity.profile import ASPECTS


@dataclass
class ChangeReport:
    root_a: str
    root_b: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, list[str]] = field(default_factory=dict)
    unchanged_count: int = 0

    @property
    def clean(self) -> bool:
        return (
            self.root_a == self.root_b and not self.added and not self.removed and not self.changed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "root_a": self.root_a,
            "root_b": self.root_b,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": {pid: list(a) for pid, a in self.changed.items()},
            "unchanged_count": self.unchanged_count,
        }


def diff_manifests(a: Manifest, b: Manifest) -> ChangeReport:
    if a.profile != b.profile:
        raise ProfileMismatchError(f"cannot diff profile {a.profile!r} against {b.profile!r}")
    report = ChangeReport(root_a=a.root, root_b=b.root)
    report.added = ordered_ids(set(b.parts) - set(a.parts))
    report.removed = ordered_ids(set(a.parts) - set(b.parts))
    for pid in ordered_ids(set(a.parts) & set(b.parts)):
        ea, eb = a.parts[pid].aspects, b.parts[pid].aspects
        aspects = [x for x in ASPECTS if ea.get(x) != eb.get(x)]
        if aspects or a.parts[pid].part_hash != b.parts[pid].part_hash:
            report.changed[pid] = aspects
        else:
            report.unchanged_count += 1
    return report


def format_report(report: ChangeReport) -> str:
    lines = [f"root A: {report.root_a}", f"root B: {report.root_b}"]
    if report.clean:
        lines.append(f"match: {report.unchanged_count} parts unchanged")
        return "\n".join(lines)
    if report.added:
        lines.append(f"added ({len(report.added)}): {', '.join(report.added)}")
    if report.removed:
        lines.append(f"removed ({len(report.removed)}): {', '.join(report.removed)}")
    if report.changed:
        lines.append(f"changed ({len(report.changed)}):")
        lines += [f"  {pid}: {', '.join(aspects)}" for pid, aspects in report.changed.items()]
    lines.append(f"unchanged: {report.unchanged_count}")
    return "\n".join(lines)
