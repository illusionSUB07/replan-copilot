#!/usr/bin/env bash
# Launch one GPU instance running the Isaac Sim container with WebRTC livestream. Asks before creating anything.
set -euo pipefail

: "${AWS_PROFILE:?set AWS_PROFILE}"
: "${KEY_NAME:?set KEY_NAME to an existing EC2 key pair in the region}"
export AWS_PROFILE
REGION="${AWS_REGION:-eu-central-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.2xlarge}"
ISAAC_TAG="${ISAAC_TAG:-6.2.0}"
DISK_GB="${DISK_GB:-150}"
MAX_HOURS="${MAX_HOURS:-4}"
SUBNET_ID="${SUBNET_ID:-}"  # optional: pin an availability zone when one is out of capacity
IDLE_MIN="${IDLE_MIN:-45}"
NAME=replan-copilot-isaac-sim
TAGS="{Key=Name,Value=$NAME},{Key=owner,Value=personal},{Key=project,Value=replan-copilot}"
AMI_PARAM=/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-24.04/latest/ami-id
aws() { command aws --region "$REGION" "$@"; }

existing=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -n "$existing" ]]; then
  echo "Instance already exists: $existing (start it in the console or run destroy.sh first)" >&2
  exit 1
fi

my_ip=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
ami=$(aws ssm get-parameter --name "$AMI_PARAM" --query Parameter.Value --output text)
root_dev=$(aws ec2 describe-images --image-ids "$ami" --query 'Images[0].RootDeviceName' --output text)
price=$(aws pricing get-products --region us-east-1 --service-code AmazonEC2 --output json --filters \
  "Type=TERM_MATCH,Field=instanceType,Value=$INSTANCE_TYPE" "Type=TERM_MATCH,Field=regionCode,Value=$REGION" \
  Type=TERM_MATCH,Field=operatingSystem,Value=Linux Type=TERM_MATCH,Field=tenancy,Value=Shared \
  Type=TERM_MATCH,Field=preInstalledSw,Value=NA Type=TERM_MATCH,Field=capacitystatus,Value=Used |
  python3 -c 'import json,sys; d=json.loads(json.load(sys.stdin)["PriceList"][0]); print(next(iter(next(iter(d["terms"]["OnDemand"].values()))["priceDimensions"].values()))["pricePerUnit"]["USD"])' ||
  echo unknown)

cat <<EOF
Region          $REGION
Instance type   $INSTANCE_TYPE (on-demand Linux: \$$price/h)
AMI             $ami (AWS Deep Learning Base OSS NVIDIA Driver, Ubuntu 24.04)
Image           nvcr.io/nvidia/isaac-sim:$ISAAC_TAG
Disk            ${DISK_GB} GB gp3 (billed while stopped too, about \$0.10/GB-month)
Access          ports 22, 49100/tcp, 47998/udp open only to $my_ip/32, key pair $KEY_NAME
Safeguards      shutdown after $IDLE_MIN min idle, hard stop after $MAX_HOURS h of uptime
EOF
if [[ "$price" != unknown ]]; then
  python3 -c "print(f'Worst case per boot: \${$price * $MAX_HOURS:.2f} ($MAX_HOURS h x \${$price}/h)')"
fi
read -r -p "Type 'yes' to create these resources: " answer
[[ "$answer" == yes ]] || { echo "Aborted, nothing created."; exit 1; }

vpc=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
sg=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" "Name=vpc-id,Values=$vpc" --query 'SecurityGroups[0].GroupId' --output text)
if [[ "$sg" == None ]]; then
  sg=$(aws ec2 create-security-group --group-name "$NAME" --description "Isaac Sim livestream, caller IP only" --vpc-id "$vpc" \
    --tag-specifications "ResourceType=security-group,Tags=[$TAGS]" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id "$sg" --ip-permissions \
    "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$my_ip/32}]" \
    "IpProtocol=tcp,FromPort=49100,ToPort=49100,IpRanges=[{CidrIp=$my_ip/32}]" \
    "IpProtocol=udp,FromPort=47998,ToPort=47998,IpRanges=[{CidrIp=$my_ip/32}]" >/dev/null
fi

user_data=$(printf '#!/bin/bash\nIMAGE=nvcr.io/nvidia/isaac-sim:%s\nMAX_HOURS=%s\nIDLE_MIN=%s\n' "$ISAAC_TAG" "$MAX_HOURS" "$IDLE_MIN"
cat <<'EOF'
set -euxo pipefail
H=/home/ubuntu
mkdir -p $H/docker/isaac-sim/{cache/main,cache/computecache,cache/kit,config,data,logs,pkg} $H/.cache/ov/hub $H/work
chown -R 1234:1234 $H/docker/isaac-sim $H/.cache/ov/hub
chmod 777 $H/work

# isaac-run NAME ENTRYPOINT ARGS...: container with the documented cache mounts, repo copy at /work
cat > /usr/local/bin/isaac-run <<EOS
#!/bin/bash
name=\$1 entry=\$2; shift 2
exec docker run --rm --name "\$name" --gpus all --network=host -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=N -u 1234:1234 \\
  -v $H/docker/isaac-sim/cache/main:/isaac-sim/.cache:rw \\
  -v $H/docker/isaac-sim/cache/computecache:/isaac-sim/.nv/ComputeCache:rw \\
  -v $H/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \\
  -v $H/docker/isaac-sim/logs:/isaac-sim/.nvidia-omniverse/logs:rw \\
  -v $H/docker/isaac-sim/config:/isaac-sim/.nvidia-omniverse/config:rw \\
  -v $H/docker/isaac-sim/data:/isaac-sim/.local/share/ov/data:rw \\
  -v $H/docker/isaac-sim/pkg:/isaac-sim/.local/share/ov/pkg:rw \\
  -v $H/.cache/ov/hub:/var/cache/hub:rw \\
  -v $H/work:/work:rw \\
  --entrypoint "\$entry" $IMAGE "\$@"
EOS

# public IP changes on every start, so it is read at service start
cat > /usr/local/bin/isaac-livestream <<'EOS'
#!/bin/bash
t=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/public-ipv4)
exec /usr/local/bin/isaac-run isaac-sim /isaac-sim/runheadless.sh \
  --/exts/omni.kit.livestream.app/primaryStream/publicIp="$ip" \
  --/exts/omni.kit.livestream.app/primaryStream/signalPort=49100 \
  --/exts/omni.kit.livestream.app/primaryStream/streamPort=47998
EOS

# idle = no SSH or WebRTC signaling connection and no isaac-render container
cat > /usr/local/bin/idle-stop <<EOS
#!/bin/bash
f=/run/idle-since
if ss -Htn state established '( sport = :22 or sport = :49100 )' | grep -q . || docker ps -q -f name=^isaac-render\$ | grep -q .; then rm -f \$f; exit 0; fi
[ -f \$f ] || date +%s > \$f
[ \$(( \$(date +%s) - \$(cat \$f) )) -ge $((IDLE_MIN * 60)) ] && shutdown -h now
EOS
chmod +x /usr/local/bin/isaac-run /usr/local/bin/isaac-livestream /usr/local/bin/idle-stop
echo '*/5 * * * * root /usr/local/bin/idle-stop' > /etc/cron.d/idle-stop

cat > /etc/systemd/system/max-runtime.service <<EOS
[Unit]
Description=Hard stop after $MAX_HOURS h uptime
[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h +$((MAX_HOURS * 60))
[Install]
WantedBy=multi-user.target
EOS

cat > /etc/systemd/system/isaac-sim.service <<'EOS'
[Unit]
Description=Isaac Sim WebRTC livestream
After=docker.service network-online.target
Requires=docker.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f isaac-sim
ExecStart=/usr/local/bin/isaac-livestream
Restart=on-failure
TimeoutStartSec=0
[Install]
WantedBy=multi-user.target
EOS

systemctl daemon-reload
systemctl enable --now max-runtime.service
docker pull "$IMAGE"
systemctl enable --now isaac-sim.service
EOF
)

id=$(aws ec2 run-instances --image-id "$ami" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$sg" ${SUBNET_ID:+--subnet-id "$SUBNET_ID"} --instance-initiated-shutdown-behavior stop \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings "DeviceName=$root_dev,Ebs={VolumeSize=$DISK_GB,VolumeType=gp3,DeleteOnTermination=true}" \
  --tag-specifications "ResourceType=instance,Tags=[$TAGS]" "ResourceType=volume,Tags=[$TAGS]" \
  --user-data "$user_data" --query 'Instances[0].InstanceId' --output text)
echo "Launched $id, waiting for it to run..."
aws ec2 wait instance-running --instance-ids "$id"
ip=$(aws ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "Public IP $ip. The container pull takes ~10 min; then connect the Isaac Sim WebRTC Streaming Client to $ip."
echo "SSH: ssh -i <your-key>.pem ubuntu@$ip   Logs: journalctl -fu isaac-sim"
