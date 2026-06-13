# Deploying edgemesh — cloud, edge, anywhere

edgemesh is a stdlib-only Python gateway with no model weights, so it deploys
almost anywhere a Python 3.10+ runtime or a container runs. Pick the target:

## Local / workstation
```bash
./install.sh          # Linux/macOS   (install.ps1 on Windows)
edgemesh setup        # guided config
edgemesh serve        # gateway on http://127.0.0.1:8780
```

## Docker (single host)
```bash
docker compose up -d  # gateway on :8780, config persisted in ./edgemesh-config
```
On Linux, uncomment `network_mode: host` in `docker-compose.yml` so the gateway
can discover backends bound to the host's `localhost` (e.g. Ollama on 11434).

## systemd (Linux edge node / server)
```bash
sudo cp deploy/edgemesh.service /etc/systemd/system/edgemesh@.service
sudo systemctl daemon-reload
sudo systemctl enable --now edgemesh@$USER
```

## Cloud (any VM)
Any cloud VM works — there is nothing GPU-specific in the gateway itself:
```bash
# on the VM
curl -fsSL https://raw.githubusercontent.com/cognis-digital/edgemesh/main/install.sh | sh
edgemesh serve --host 0.0.0.0 --port 8780
```
Put it behind your reverse proxy / security group and point OpenAI clients at it.
GPU backends (vLLM, Ollama, TGI, NIM) run wherever your accelerators are; edgemesh
just meshes their `/v1` endpoints — they can be on the same VM, other VMs, or
on-prem boxes registered with `edgemesh add` / `edgemesh join`.

## Building a cluster across devices
1. Pick one machine as the **coordinator**: `edgemesh serve` (note its LAN IP).
2. On every other device (any OS): `edgemesh join http://<coordinator-ip>:8780`.
   Each node registers its local backends; the coordinator's `/v1` catalog spans
   the whole mesh. Force a specific node/model with `node-name.backend::model`.
