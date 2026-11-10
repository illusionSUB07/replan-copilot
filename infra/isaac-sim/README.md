# Isaac Sim GPU workstation (AWS)

One on-demand GPU instance that runs the official Isaac Sim container with the WebRTC livestream, so the plant scene in `omniverse/out/plant.usda` can be opened interactively and camera frames rendered headless for the perception step. Nothing here runs by itself: `launch.sh` prints the cost and asks for `yes` before creating anything.

## Recommendation

**g6e.2xlarge in eu-central-1 (Frankfurt), about $2.80/h on demand.** 1x NVIDIA L40S (48 GB, RT cores), 8 vCPU, 64 GiB RAM.

- NVIDIA's own AWS guide names g6e.2xlarge (or g7e.8xlarge) as the instance to pick [1].
- It meets the Isaac Sim "good" column (8 cores, 64 GB RAM) and the "ideal" 48 GB VRAM [2]. GPUs without RT cores (A100, H100) are not supported [2].
- Frankfurt keeps WebRTC latency low from Germany. For batch rendering only, us-east-1 is 20% cheaper.

On-demand Linux prices from the AWS Price List API (checked 2026-11-10, USD/h):

| Type | GPU | vCPU / RAM | eu-central-1 | us-east-1 |
|---|---|---|---|---|
| g6e.xlarge | L40S 48 GB | 4 / 32 GiB | 2.33 | 1.86 |
| **g6e.2xlarge** | L40S 48 GB | 8 / 64 GiB | **2.80** | 2.24 |
| g6e.4xlarge | L40S 48 GB | 16 / 128 GiB | 3.76 | 3.00 |
| g6.2xlarge | L4 24 GB | 8 / 32 GiB | 1.22 | 0.98 |
| g6.4xlarge | L4 24 GB | 16 / 64 GiB | 1.65 | 1.32 |
| g5.2xlarge | A10G 24 GB | 8 / 32 GiB | 1.52 | 1.21 |

The cheaper fallback is g6.4xlarge (L4, 64 GiB RAM, $1.65/h): fine for frame rendering, slower for interactive use. The 150 GB gp3 disk costs about $14/month in Frankfurt ($0.0952/GB-month) and keeps billing while the instance is stopped, until `destroy.sh`.

## Quota

G-family instances count against the EC2 quota **Running On-Demand G and VT instances** (code `L-DB2E81BA`, measured in vCPUs, per region). g6e.2xlarge needs 8. Check yours:

```bash
aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA --region eu-central-1 --query Quota.Value
```

If it is below 8, request at least 8 (16 leaves room for g6e.4xlarge) in the Service Quotas console, or with `aws service-quotas request-service-quota-increase --service-code ec2 --quota-code L-DB2E81BA --desired-value 16`.

## How it is set up

- **AMI:** AWS Deep Learning Base OSS NVIDIA Driver GPU AMI (Ubuntu 24.04), resolved from its public SSM parameter. It ships Docker and the NVIDIA Container Toolkit, and recent releases carry driver 595.91.07 [5], above the 595.58.03 Isaac Sim recommends [2].
- **Isaac Sim:** the NGC container `nvcr.io/nvidia/isaac-sim:6.2.0` (current release; override with `ISAAC_TAG`), run as user 1234 with host networking and the documented cache mounts [3]. A systemd unit `isaac-sim` starts `runheadless.sh` with the instance's public IP on every boot [4].
- **Network:** a security group in the default VPC that opens 22/tcp, 49100/tcp (WebRTC signaling) and 47998/udp (WebRTC media) only to the IP you launch from [1][4]. The stream has no authentication, so keep it that way [4].
- **Access:** SSH with an existing EC2 key pair (`KEY_NAME`).
- **Auto-stop:** a cron job stops the instance after `IDLE_MIN` (default 45) minutes with no SSH or WebRTC connection and no `isaac-render` container, and every boot schedules a hard stop after `MAX_HOURS` (default 4). Shutdown means *stop*, not terminate, so worst case per boot is 4 h x $2.80 = $11.21.
- **Tags:** `owner=personal`, `project=replan-copilot`, `Name=replan-copilot-isaac-sim` on instance, volume and security group.

The NVIDIA Marketplace AMI ("Isaac Sim" Ubuntu/Windows workstation with DCV desktop) is also available in both regions [1], but needs a Marketplace subscription and is not used here.

## Steps

1. Install the **Isaac Sim WebRTC Streaming Client** for your OS [4], and AWS CLI v2.
2. Log in and pick the profile: `aws sso login --profile <profile>`, then `export AWS_PROFILE=<profile>`.
3. Check the quota (above). Have an EC2 key pair in the region: `export KEY_NAME=<key-name>`.
4. Optional overrides: `AWS_REGION` (eu-central-1), `INSTANCE_TYPE` (g6e.2xlarge), `ISAAC_TAG` (6.2.0), `DISK_GB` (150), `MAX_HOURS` (4), `IDLE_MIN` (45).
5. `./infra/isaac-sim/launch.sh`, read the estimate, type `yes`. It prints the public IP.
6. Wait about 10 min for the image pull and first shader compile (`ssh ubuntu@<ip> journalctl -fu isaac-sim`), then connect the streaming client to the IP.
7. Copy the repo and render frames:

```bash
rsync -av --exclude .venv --exclude .git ./ ubuntu@<ip>:work/
ssh ubuntu@<ip> sudo isaac-run isaac-render /isaac-sim/python.sh /work/infra/isaac-sim/render_frames.py --every 10
rsync -av ubuntu@<ip>:work/frames/ ./frames/
```

`render_frames.py` opens `omniverse/out/plant.usda`, sets the timeline to every K-th time code between the stage's start and end, and writes `frames/<camera>/<timecode>.png` for each camera under `/World/Cameras`. It follows the Replicator render product + `rgb` annotator pattern [6][7]. Options: `--usd`, `--out`, `--every`, `--width`, `--height`, `--subframes`. The livestream keeps running alongside; `sudo systemctl stop isaac-sim` frees the GPU if needed.

8. `./infra/isaac-sim/stop.sh` when done (disk kept), or `./infra/isaac-sim/destroy.sh` to terminate the instance and delete the security group. Restart a stopped instance from the console or `aws ec2 start-instances`; the public IP changes.

## Sources

1. NVIDIA, Isaac Sim AWS Deployment: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_advanced_cloud_setup_aws.html
2. NVIDIA, Isaac Sim Requirements: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
3. NVIDIA, Isaac Sim Container Installation: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
4. NVIDIA, Isaac Sim Livestream Clients: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/manual_livestream_clients.html
5. AWS, Deep Learning Base GPU AMI (Ubuntu 24.04): https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-base-gpu-ami-ubuntu-24-04.html
6. NVIDIA, Replicator Getting Started Scripts: https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/tutorial_replicator_getting_started.html
7. NVIDIA, Isaac Sim Python Environment (standalone `SimulationApp`): https://docs.isaacsim.omniverse.nvidia.com/5.1.0/python_scripting/manual_standalone_python.html
8. NGC catalog, Isaac Sim container: https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-sim
