# One-click environment auto-tune

Anvil's **System → Environment** page checks the host's benchmark
posture. When it finds a setting that's known to perturb NVMe
numbers, the **Auto-tune** card proposes a concrete fix for each
violation. Admins can apply them all with one click and revert just
as cleanly.

## Tunables

| Key | Target | Why |
|---|---|---|
| `cpu_governor` | `performance` | Prevents cpufreq ramp-down during idle gaps between fio phases |
| `pcie_aspm_policy` | `performance` | Stops PCIe ASPM from parking the link at L0s/L1 |
| `nvme_scheduler` | `none` | Removes mq-deadline per-request overhead |
| `nvme_nr_requests` | `2048` | Expands block-layer queue to saturate high-QD fio jobs |
| `nvme_read_ahead_kb` | `128` | Caps read-ahead so sequential reads aren't cache-pre-fetched |

## How it works

1. **Preview** — `GET /api/environment/tune/preview` expands the
   tunable globs (every CPU, every NVMe namespace) and reports every
   path that would change, with its current and desired values.
2. **Apply** — `POST /api/environment/tune/apply` writes each path
   and persists a **receipt** server-side in `tune_receipts`. The
   response carries `receipt_id` plus the full per-path result list.
3. **Revert** — `POST /api/environment/tune/revert` takes only
   `{receipt_id}`; Anvil loads the stored receipt and writes the
   original values back.

## Security

The runner enforces a **sysfs-glob allowlist** inside its low-level
`_write_sysfs()`:

- `/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
- `/sys/module/pcie_aspm/parameters/policy`
- `/sys/block/nvme*n*/queue/scheduler`
- `/sys/block/nvme*n*/queue/nr_requests`
- `/sys/block/nvme*n*/queue/read_ahead_kb`

Any write outside these globs — including attempts with `..`
traversal — is refused with `PermissionError`.

The receipt system is the **outer** security boundary: the API
server never accepts client-supplied paths on `/revert`, only a
receipt ID that looks up the previously-approved path list.

## Operational notes

- Reverts are idempotent per receipt; double-revert returns
  `409 Conflict`.
- Reverting doesn't always restore the exact prior state — if the
  kernel rejected one of your desired values (e.g. scheduler
  `none` on a drive that doesn't support it), that path stays in
  its post-apply state.
- If you lose the `receipt_id` (e.g. the UI state evaporated on
  refresh), the receipts table is queryable by an admin; sort by
  `created_at` descending.
