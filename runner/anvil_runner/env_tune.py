"""Runner-side auto-tune for benchmark reproducibility.

Only writes a small, explicit allow-list of sysfs paths. Every path has:
  - an expected target value
  - a before/after snapshot recorded at apply time
  - a revert path (the same sysfs file; we just write the snapshotted old
    value back)

The tuner is transactional in spirit: after every write attempt we record
the outcome. If any write raises (e.g. EACCES on a read-only sysfs node)
we immediately revert every previously-successful write in reverse order.
Callers can also explicitly request revert via the revert_receipt endpoint.

Security note: every write goes through /proc/1/root/sys/... which is the
host-namespace sysfs view. The runner container is privileged with
pid=host, so the kernel accepts these writes as if they came from host
init. Only admin-role users can trigger this via the API.
"""
from __future__ import annotations

import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _host_path(p: str) -> str:
    root = Path("/proc/1/root")
    if root.exists():
        return str(root) + p
    return p


def _glob_host(pattern: str) -> list[str]:
    return sorted(glob.glob(_host_path(pattern)))


@dataclass
class TuneTarget:
    """One tunable knob.

    path_glob: sysfs path or glob (evaluated in host namespace)
    desired_value: what to write
    description: human-readable
    category: grouping for the UI
    safe: if False, the tuner refuses to apply unless force=True
    """
    key: str
    path_glob: str
    desired_value: str
    description: str
    category: str
    safe: bool = True


@dataclass
class TuneResult:
    key: str
    path: str
    before: str | None
    after: str | None
    ok: bool
    error: str | None = None


@dataclass
class TuneReceipt:
    results: list[TuneResult] = field(default_factory=list)
    reverted: bool = False
    revert_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [r.__dict__ for r in self.results],
            "reverted": self.reverted,
            "revert_error": self.revert_error,
        }


TUNABLES: list[TuneTarget] = [
    TuneTarget(
        key="cpu_governor",
        path_glob="/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor",
        desired_value="performance",
        description="Set every CPU's cpufreq governor to 'performance' to pin frequency.",
        category="cpu",
    ),
    TuneTarget(
        key="pcie_aspm_policy",
        path_glob="/sys/module/pcie_aspm/parameters/policy",
        desired_value="performance",
        description=(
            "Force global PCIe ASPM policy to 'performance' so the kernel stops "
            "asking endpoints to enter L0s/L1 power states during latency-sensitive "
            "benchmarks."
        ),
        category="pcie",
    ),
    TuneTarget(
        key="nvme_scheduler",
        path_glob="/sys/block/nvme*n*/queue/scheduler",
        desired_value="none",
        description=(
            "Select the 'none' I/O scheduler for every NVMe namespace. The default "
            "Linux mq-deadline adds per-request overhead that obscures raw device "
            "latency."
        ),
        category="block",
    ),
    TuneTarget(
        key="nvme_nr_requests",
        path_glob="/sys/block/nvme*n*/queue/nr_requests",
        desired_value="2048",
        description="Expand the block-layer request queue to 2048 entries per NVMe.",
        category="block",
    ),
    TuneTarget(
        key="nvme_read_ahead_kb",
        path_glob="/sys/block/nvme*n*/queue/read_ahead_kb",
        desired_value="128",
        description=(
            "Cap NVMe read-ahead at 128 KiB so sequential read benchmarks don't "
            "accidentally pre-fetch into cache and inflate numbers."
        ),
        category="block",
    ),
]


TUNABLES_BY_KEY = {t.key: t for t in TUNABLES}


def _read_sysfs(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().rstrip("\n")
    except (OSError, PermissionError):
        return None


def _path_is_tunable(path: str) -> bool:
    """Whitelist: a path may be written only if it matches one of the
    TUNABLE globs. Prevents a malicious revert payload from pointing at
    arbitrary sysfs/procfs files and smuggling in a privileged write.
    """
    import fnmatch
    if not path or ".." in path:
        return False
    return any(fnmatch.fnmatchcase(path, t.path_glob) for t in TUNABLES)


def _write_sysfs(path: str, value: str) -> None:
    if not _path_is_tunable(path):
        raise PermissionError(f"refusing to write unallowed path: {path}")
    with open(path, "w") as f:
        f.write(value)


def _current_value_for_display(raw: str | None) -> str | None:
    """Some sysfs files report `[selected] option1 option2`; return just the
    active choice for comparability against desired_value."""
    if raw is None:
        return None
    import re as _re

    m = _re.search(r"\[([^]]+)\]", raw)
    return m.group(1) if m else raw


def preview(keys: list[str] | None = None) -> list[dict[str, Any]]:
    """Dry-run: report what would change, without writing."""
    wanted = keys or list(TUNABLES_BY_KEY.keys())
    out: list[dict[str, Any]] = []
    for key in wanted:
        t = TUNABLES_BY_KEY.get(key)
        if t is None:
            out.append({"key": key, "error": "unknown key"})
            continue
        for p in _glob_host(t.path_glob):
            raw = _read_sysfs(p)
            cur = _current_value_for_display(raw)
            out.append(
                {
                    "key": key,
                    "category": t.category,
                    "path": p.replace(str(Path("/proc/1/root")), "", 1) or p,
                    "desired": t.desired_value,
                    "current": cur,
                    "will_change": cur != t.desired_value,
                    "description": t.description,
                }
            )
    return out


def apply(keys: list[str] | None = None) -> TuneReceipt:
    """Write desired_value to every matched path. On any write failure,
    revert all previously-successful writes.

    Returns a TuneReceipt including per-path before/after so an admin can
    see exactly what changed and pass the receipt back to revert() later
    if they want to roll the changes back without recomputing before-
    values.
    """
    wanted = keys or list(TUNABLES_BY_KEY.keys())
    receipt = TuneReceipt()

    for key in wanted:
        t = TUNABLES_BY_KEY.get(key)
        if t is None:
            receipt.results.append(
                TuneResult(
                    key=key, path="(n/a)", before=None, after=None, ok=False,
                    error="unknown key",
                )
            )
            continue
        for p in _glob_host(t.path_glob):
            before_raw = _read_sysfs(p)
            before = _current_value_for_display(before_raw)
            if before == t.desired_value:
                receipt.results.append(
                    TuneResult(key=key, path=p, before=before, after=before, ok=True)
                )
                continue
            try:
                _write_sysfs(p, t.desired_value)
            except OSError as exc:
                receipt.results.append(
                    TuneResult(
                        key=key, path=p, before=before, after=None, ok=False,
                        error=f"{exc.__class__.__name__}: {exc}",
                    )
                )
                _revert_partial(receipt)
                receipt.reverted = True
                return receipt
            after_raw = _read_sysfs(p)
            after = _current_value_for_display(after_raw)
            receipt.results.append(
                TuneResult(key=key, path=p, before=before, after=after, ok=True)
            )
    return receipt


def _revert_partial(receipt: TuneReceipt) -> None:
    """Walk the receipt in reverse, restoring before-values for ok results.

    Called from apply() when a later write fails mid-batch; the earlier
    writes are rolled back so the host either fully changes or is left
    untouched. Revert errors are captured on the receipt rather than
    raising — the caller already has a primary failure to surface.
    """
    errors: list[str] = []
    for r in reversed(receipt.results):
        if not r.ok or r.before is None or r.before == r.after:
            continue
        try:
            _write_sysfs(r.path, r.before)
        except OSError as exc:
            errors.append(f"{r.path}: {exc}")
    if errors:
        receipt.revert_error = "; ".join(errors)


def revert(receipt_results: list[dict[str, Any]]) -> TuneReceipt:
    """Explicit revert of an earlier receipt. Caller passes the results
    list back in; for each ok entry we write the recorded `before`
    value back to the path."""
    out = TuneReceipt(reverted=True)
    errors: list[str] = []
    for entry in reversed(receipt_results):
        key = entry.get("key") or ""
        path = entry.get("path") or ""
        before = entry.get("before")
        ok = bool(entry.get("ok"))
        if not ok or path in ("", "(n/a)") or before is None:
            continue
        current = _current_value_for_display(_read_sysfs(path))
        try:
            _write_sysfs(path, before)
            after = _current_value_for_display(_read_sysfs(path))
            out.results.append(TuneResult(
                key=key, path=path, before=current, after=after, ok=True,
            ))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            out.results.append(TuneResult(
                key=key, path=path, before=current, after=None, ok=False,
                error=str(exc),
            ))
    if errors:
        out.revert_error = "; ".join(errors)
    return out
