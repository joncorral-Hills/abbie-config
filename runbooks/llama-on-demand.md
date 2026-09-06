# Llama-Server On-Demand Protocol

> Manages Gemma 4 E4B (4.0 GB) lifecycle to free ~4 GB RAM when not in use.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│                  Normal State                        │
│         llama-server OFF (~4 GB RAM free)            │
└──────────────────────┬──────────────────────────────┘
                       │
              Cron needs llama-local
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  1. Cron message includes:                           │
│     "First run: bash ~/abbie-config/scripts/         │
│      llama-on-demand.sh start"                       │
│  2. Script starts llama-server, waits for healthy    │
│  3. Cron executes with llama-local                   │
│  4. Cron completes, touches timestamp                │
└──────────────────────┬──────────────────────────────┘
                       │
              30 min idle timeout
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Idle monitor (q15m cron) detects timeout            │
│  → Stops llama-server → Back to OFF state            │
└─────────────────────────────────────────────────────┘
```

## Affected Crons (llama-local model)

| ID | Name | Schedule | Deployed |
|:---|:---|:---|:---|
| 7 | Monthly Financial Update | 1st @ 9 AM | ✅ |
| 3 | Monthly Subscription Audit | 1st @ 10 AM | ✅ |
| 6 | Statement Processor | Daily @ 10 PM | ✅ |
| TX1 | Quarterly Tax Deadline | Quarterly | ✅ |
| TX2 | Monthly Deduction Scan | 5th @ 10 AM | ✅ |
| TX3 | Quarterly Tax Dashboard | Quarterly | ✅ |
| CAL2 | Conflict Detection | Daily @ 8 AM | ✅ (migrate to gemini-local) |

## Deployment Steps

### 1. Disable llama-server auto-start

```bash
# If managed by supervisord:
supervisorctl stop llama-server
# Remove from supervisord autostart or set autostart=false

# If managed by systemd:
sudo systemctl stop llama-server
sudo systemctl disable llama-server
```

### 2. Install the on-demand script

```bash
chmod +x ~/abbie-config/scripts/llama-on-demand.sh
bash ~/abbie-config/scripts/llama-on-demand.sh status
```

### 3. Add idle monitor cron

```bash
# Check every 15 min if llama-server should be stopped
# Add to system crontab:
*/15 * * * * bash ~/abbie-config/scripts/llama-on-demand.sh idle-check >> /tmp/llama-idle.log 2>&1
```

### 4. Update cron messages

For each llama-local cron in `~/.hermes/config.yaml`, prepend to the message:

```
First, ensure llama-server is running by executing:
bash ~/abbie-config/scripts/llama-on-demand.sh start

Then proceed with the task. After completing, run:
bash ~/abbie-config/scripts/llama-on-demand.sh touch
```

### 5. Migrate CAL2 to gemini-local

CAL2 (daily calendar conflict detection) does NOT handle PII and runs daily.
Keeping llama-server alive just for CAL2 defeats the purpose.

```yaml
# In config.yaml, change CAL2:
model: gemini-local  # was llama-local
```

## RAM Impact

| State | llama-server | RAM Freed |
|:---|:---|:---|
| Before (always on) | ~4.0 GB resident | 0 |
| After (on-demand) | 0 GB ~90% of time | **~4.0 GB** |
| During cron execution | ~4.0 GB for 5-15 min | 0 (temporary) |
