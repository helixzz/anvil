# First run

After installing Anvil and logging in as the bootstrap admin, the
happy path to your first benchmark is:

## 1. Discover the device

Navigate to **Devices**. Click **Rescan**. Every NVMe namespace the
runner can see is listed with its model, serial, firmware, PCIe
capability, and current path.

!!! warning "Raw devices only"
    Anvil refuses any device that has a mounted partition. If your
    candidate drive is mounted, unmount it first.

## 2. Open the device detail page

Click the device. You'll see:

- PCIe capability vs. current link state (Gen / width; degraded-link
  warning if mismatch)
- Historical runs against this device
- SMART snapshot

## 3. Start a run

Click **New run**. Pick one of:

- **`sweep_quick`** — 5-minute block-size sweep; good smoke test
- **`sweep_full`** — 45-minute block-size × iodepth sweep
- **`snia_quick_pts`** — SNIA SSS-PTS Quick (5 rounds); produces
  SteadyStateAnalysis in the report
- **`endurance_soak`** — 2-hour sustained write; triggers thermal
  auto-abort on overheat

Destructive profiles prompt for the last 6 characters of the device
serial as a confirmation token. This is deliberate — Anvil will
overwrite the drive.

## 4. Watch it run

Anvil streams live metrics via WebSocket. You'll see:

- Phase progress (preflight → running → complete)
- Per-second IOPS / bandwidth / latency / temperature
- SMART before/after diff when the run finishes

## 5. Read the report

Every complete run has:

- A **Run Detail** page with interactive charts
- An **Export HTML** button (zero-JS, print-to-PDF friendly)
- An **Export JSON** button (lossless archive)
- A **Share link** button (operator+admin only) that creates a
  revocable public URL with the device serial redacted

See [reading a report](../user-guide/reports.md) for what each section
means.
