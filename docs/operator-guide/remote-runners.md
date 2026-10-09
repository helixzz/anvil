# Remote runner hosts

Anvil can drive benchmarks on several test servers. The main node (web, API,
database and the co-located `local` runner container) stays where it is; each
additional test host runs a lightweight **runner service** that the API dials
over TCP.

- One benchmark at a time **per host** (no PCIe / CPU / thermal contention);
  different hosts run in parallel.
- Each device belongs to the host it was last discovered on. A drive moved
  to another host keeps its history (same model + serial fingerprint).
- Rescanning one host never marks another host's drives as missing, and an
  unreachable host keeps its devices as they were.
- Environment checks and auto-tune target a selected host; a revert is
  always sent to the host that applied the change.

## Security model

The runner executes raw block-device I/O as root, so the TCP endpoint is
protected twice:

- **TLS** with a self-signed certificate generated on the runner. The API
  pins its SHA-256 fingerprint; a different certificate is refused.
- A **shared token** (64 hex chars) sent with every request and compared in
  constant time. The token is write-only in the API and never returned.

Only the Anvil API needs to reach the runner port (default `9470`); restrict
it to the main node with your firewall if the network is shared.

## Install a runner on a test host

Requirements: Ubuntu 22.04+/Debian with Python ≥ 3.11, root, and network
reachability **from the Anvil main node to the runner port**. Docker is not
needed — the runner is installed natively as a systemd service.

```bash
# on the test host, from an Anvil checkout
sudo ./scripts/install-runner.sh            # default port 9470
```

Hosts without PyPI access can install from a wheelhouse built elsewhere with
the same Python version and architecture:

```bash
# on a machine with internet
pip wheel ./runner setuptools wheel -w wheelhouse/
# copy runner/, scripts/install-runner.sh, deploy/systemd/ and wheelhouse/ to the test host, then
sudo ./scripts/install-runner.sh --wheelhouse ./wheelhouse
```

The script installs `fio`, `nvme-cli`, `smartmontools`, … via apt, creates
`/opt/anvil-runner`, generates `/etc/anvil-runner/{token,tls.crt,tls.key}`
and enables `anvil-runner.service`. It ends by printing:

```
  Address:          10.67.64.41:9470
  Token:            <64 hex chars>
  TLS fingerprint:  <sha256 hex>
```

Re-running the script upgrades the runner code and keeps the token and
certificate, so the registration stays valid.

## Register it in Anvil

**Runners → Add runner** (admin): enter a name, the address and the token.
The fingerprint is optional — if omitted, Anvil pins the certificate it sees
on first contact and shows it; compare it with the one printed by the
installer. Then **Devices → Rescan** that host.

Equivalent API call:

```bash
curl -X POST https://anvil.example/api/runners \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"gen5-bench","address":"10.67.64.41:9470","token":"…","tls_fingerprint":"…"}'
```

## Operations

| Task | How |
|---|---|
| Status / logs | `systemctl status anvil-runner`, `journalctl -u anvil-runner -f` |
| Change port | `sudo ./scripts/install-runner.sh --port 9480`, then update the address in Anvil |
| Rotate token | `sudo rm /etc/anvil-runner/token && sudo ./scripts/install-runner.sh`, then **Rotate token** in Anvil |
| Replace certificate | remove `/etc/anvil-runner/tls.*`, re-run the installer, then **Re-pin certificate** in Anvil |
| Take a host out of service | **Disable** it in Anvil (devices and history are kept) |
| Remove a host | **Delete** it in Anvil (refused while it has queued/running runs; its devices become unattached) |

If the API loses the connection to a runner mid-run (network blip), the
runner terminates fio immediately and the run is marked failed — re-queue it.
