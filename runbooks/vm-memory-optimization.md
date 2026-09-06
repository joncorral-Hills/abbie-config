# VM Deployment Guide — Memory Optimization

> Instructions for Allie to execute on the Abacus AI SuperComputer VM.
> Send this via bridge or Telegram.

---

## 1. Create Swap File (2 GB Safety Net)

Prevents OOM kills when RAM spikes during concurrent cron + inference.

```bash
# Check if swap already exists
sudo swapon --show

# Create 2 GB swap file
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Set swappiness low (prefer RAM, swap is emergency only)
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Verify
free -h
```

## 2. Deploy Heartbeat Bash Script

```bash
# Copy script to VM
cp ~/abbie-config/scripts/heartbeat.sh ~/heartbeat.sh
chmod +x ~/heartbeat.sh

# Test it
bash ~/heartbeat.sh

# Update Hermes cron SH1:
# - Change schedule from "0 */2 * * *" to "0 */4 * * *"
# - Change execution to run bash script instead of LLM inference
# In ~/.hermes/config.yaml, update the SH1 cron message to:
#   "Run bash ~/abbie-config/scripts/heartbeat.sh and report the output"
```

## 3. Deploy Log Rotation Script

```bash
# Copy script
cp ~/abbie-config/scripts/rotate_logs.sh ~/rotate_logs.sh
chmod +x ~/rotate_logs.sh

# Test it
bash ~/rotate_logs.sh

# Add weekly cron (Sunday 4 AM, before SH4 storage audit at 5 AM)
# Either via system crontab or as a Hermes cron with bash execution
```

## 4. Update SH1 Cron in Hermes Config

In `~/.hermes/config.yaml`, find the SH1 cron definition and update:

```yaml
# Before:
- id: SH1
  schedule: "0 */2 * * *"
  model: gemini-local
  message: "Run heartbeat monitor..."

# After:
- id: SH1
  schedule: "0 */4 * * *"
  model: gemini-local  # Still needs a model to execute the bash command
  message: "Execute: bash ~/abbie-config/scripts/heartbeat.sh — Report the stdout output. No additional analysis needed."
```

## 5. Verify

After deploying, confirm:
- [ ] `free -h` shows 2 GB swap active
- [ ] `bash ~/heartbeat.sh` runs and produces JSON state file
- [ ] `bash ~/rotate_logs.sh` runs without errors
- [ ] SH1 fires at the next 4h mark and sends results
