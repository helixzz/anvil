# Running a benchmark

## Prerequisites

1. The device is visible under **Devices**
2. You're logged in as `operator` or `admin` (viewers cannot start runs)
3. No other run is in progress (Anvil serializes; one device at a time)

## Start via UI

1. **Devices → click your device → New run**
2. Pick the profile
3. For destructive profiles, type the **last 6 chars of the serial**
   to confirm
4. Click **Start**

## Start via API

```bash
TOKEN=$(grep ^ANVIL_BEARER_TOKEN .env | cut -d= -f2)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "01K...",
    "profile_name": "snia_quick_pts",
    "confirm_serial_last6": "A1B2C3"
  }' \
  http://localhost:8080/api/runs
```

Returns the new run's full record including its `id`. Poll
`GET /api/runs/{id}` or subscribe to `WS /ws/runs/{id}` for live
updates.

## What Anvil captures per run

- Device fingerprint at run time (model, serial, firmware, capacity,
  PCIe capability, PCIe actual link)
- Host fingerprint (kernel, CPU, available `fio` / `nvme` versions)
- SMART before the first fio phase, SMART after the last
- Every fio `json+` sample (per-second metrics per phase)
- Temperature from every SMART sample during the run

## Aborting

Click **Abort run** on the Run Detail page. The queue sends SIGTERM
to fio in the runner container; the run finishes its current sample,
then writes `status=aborted` with `error_message="aborted by user"`.

## Thermal auto-abort

The `endurance_soak` profile watches the drive temperature every 5
seconds. If 6 consecutive samples report ≥ 75 °C, the run aborts
itself with:

```
thermal_abort: temperature ≥ 75 °C for 6 consecutive SMART samples
```

This is deliberate — throttling kicks in on most NVMes near 75 °C
and any data after that point is compromised as a benchmark result.
