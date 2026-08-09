# Handoff: GPU passthrough into Docker containers

Needs root. ~5 minutes. Nothing in this repository changes as a result.

## Symptom

```
$ docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
docker: Error response from daemon: could not select device driver "" with capabilities: [[gpu]]
```

`resources.gpu: true` modules therefore fall back to CPU inside containers.
LoFTR is ~20x slower that way (4.8s → ~90s for 9 pairs), which is not a working
configuration.

## Cause

The driver is fine. The missing piece is the **container runtime shim**, which is a
separate package from the driver and is not installed.

| check | result |
|---|---|
| `nvidia-smi` | 8 × RTX A6000, driver 580.159.03 |
| `docker info \| grep Runtimes` | `io.containerd.runc.v2 runc` — no `nvidia` |
| `/etc/docker/daemon.json` | does not exist |
| `which nvidia-ctk` | not found |
| `dpkg -l \| grep nvidia-container` | zero packages |
| `apt-cache policy nvidia-container-toolkit` | **empty — no repo provides it** |

Host: Ubuntu 24.04 noble, Docker 29.1.3 (Ubuntu-packaged, not Docker CE).

## Fix

The last row above is why this is four steps and not one: the package is not in
Ubuntu's archive, so `apt-get install nvidia-container-toolkit` fails on its own.
Add NVIDIA's repo first.

```bash
# 1. Add the NVIDIA container toolkit repo (not in Ubuntu's archive)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Wire it into the daemon (writes /etc/docker/daemon.json)
sudo nvidia-ctk runtime configure --runtime=docker

# 4. Restart
sudo systemctl restart docker
```

## Verify

```bash
docker info | grep -i runtimes          # expect "nvidia" in the list
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi   # expect 8 GPUs
```

Then, from the repo:

```bash
.venv/bin/python -m pytest tests/test_docker.py -q
```

## Risk and rollback

Low. Step 3 edits `/etc/docker/daemon.json` (currently absent) to add a runtime; it
does not change the default runtime, so existing non-GPU containers are unaffected.
Step 4 restarts the daemon, which **stops running containers** — check `docker ps`
first. To undo: `sudo nvidia-ctk runtime configure --runtime=docker --unset` (or
delete the file), then restart.

## What changes in this repo afterwards

Nothing. `DockerBackend` already passes `--gpus` and `GpuBroker` already leases
devices exclusively; both have been exercised against these GPUs through
`SubprocessBackend`. After the fix, GPU modules stop silently falling back to CPU
and the subprocess workaround — which gives up the per-module dependency isolation
that the architecture exists for — can be dropped.

To make a silent CPU fallback an error instead of a warning while this is
outstanding:

```python
DockerBackend(mounts=[...], cpu_fallback=False)
```

## Not blocked by this

Image builds and CPU containers are unaffected. All 14 module images build, and the
full classical chain runs end to end in containers with metrics identical to the
host run (0.551px pose, 0.2476px final on 16 DTU images). Only `docker run --gpus`
is refused.
