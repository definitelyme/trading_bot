# VPS Setup Guide

Complete setup for a fresh Hetzner CAX11 (Ubuntu 24.04 LTS) running the AI Crypto Trader.

**Estimated time**: 30-45 minutes for first setup.

---

## Prerequisites

- Hetzner Cloud account + CAX11 server created (Ubuntu 24.04)
- SSH access as root to the new server
- GitHub repo SSH deploy key generated (see "CI/CD Setup" below)
- Cloudflare R2 bucket created for model backups
- Bybit live API keys (read + trade permissions)

---

## 1. System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Set timezone to UTC (Freqtrade uses UTC internally)
sudo timedatectl set-timezone UTC
```

---

## 2. Create Deploy User

```bash
# Create non-root user for CI/CD and bot operations
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy

# Add CI/CD SSH public key (paste your GitHub Actions public key)
sudo mkdir -p /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys <<< "<PASTE_GITHUB_ACTIONS_PUBLIC_KEY_HERE>"
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

---

## 3. Add Swap Space (Persistent)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

---

## 4. Firewall + fail2ban

```bash
sudo apt install ufw fail2ban -y

# Allow SSH; block direct 8080 access (use SSH tunnel instead)
sudo ufw allow 22
sudo ufw deny 8080
sudo ufw enable

# Verify: sudo ufw status
```

**Web UI access via SSH tunnel** (on your Mac):
```bash
ssh -L 8080:localhost:8080 deploy@<VPS_IP>
# Then open: http://localhost:8080
```

---

## 5. Install rclone + Configure Cloudflare R2

```bash
# Install rclone as the deploy user
sudo -u deploy bash -c 'curl https://rclone.org/install.sh | sudo bash'

# Configure R2 remote (run as deploy user — saves config to ~deploy/.config/rclone/)
sudo -u deploy rclone config
# Follow prompts: new remote → name: r2 → type: s3 → provider: Cloudflare → add keys
```

**Verify R2 connection:**
```bash
sudo -u deploy rclone ls r2:crypto-bot-backup
```

---

## 6. Clone Repo + Configure Bot

```bash
sudo git clone <REPO_SSH_URL> /opt/crypto
sudo chown -R deploy:deploy /opt/crypto
cd /opt/crypto

# Create .env from template — NEVER commit this file
cp .env.example .env
nano .env  # Fill in ALL values:
```

**Required `.env` values for live trading:**

```bash
# Bybit live credentials
FREQTRADE__EXCHANGE__KEY=<your_bybit_api_key>
FREQTRADE__EXCHANGE__SECRET=<your_bybit_api_secret>

# Web UI credentials (replace placeholders from config.live.json)
FREQTRADE__API_SERVER__JWT_SECRET_KEY=<32+ char random string>
FREQTRADE__API_SERVER__PASSWORD=<strong password>

# Telegram
FREQTRADE__TELEGRAM__TOKEN=<telegram_bot_token>
FREQTRADE__TELEGRAM__CHAT_ID=<your_chat_id>
```

---

## 7. Create Python venv for Reporting Scripts

The 2h log rotation and daily report scripts run on the VPS host (not inside Docker) and need Python:

```bash
cd /opt/crypto
python3 -m venv .venv
.venv/bin/pip install requests
```

---

## 8. Run Setup Script (Installs Cron Jobs + Starts Docker)

```bash
cd /opt/crypto
./scripts/setup.sh
```

This will:
- Build and start the Docker container
- Install 3 cron jobs: 2h log rotation, 23:59 daily report, 03:00 model backup

---

## 9. Verify Everything is Running

```bash
# Check Docker container
docker compose ps
docker compose logs --tail 30

# Check cron jobs
crontab -l | grep -E "(two-hour-report|daily-report|backup-models)"

# Check log file exists
ls -lh /opt/crypto/logs/freqtrade.log

# Check R2 backup (first backup runs at 03:00 AM UTC)
# Manual test: ./scripts/backup-models.sh
```

---

## 10. Sync Logs to Mac (One-Time Mac Setup)

On your Mac, add to crontab (`crontab -e`):

```bash
# Sync VPS logs to local Mac every hour (no --delete preserves local history)
0 * * * * rsync -avz deploy@<VPS_IP>:/opt/crypto/logs/ /Users/brendan/Sites/crypto/logs/ >> /tmp/vps-log-sync.log 2>&1
```

---

## CI/CD Setup (GitHub Secrets)

Generate a dedicated SSH key for GitHub Actions (on your Mac):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/vps_deploy_key -C "github-actions-deploy" -N ""
cat ~/.ssh/vps_deploy_key      # → paste as GitHub Secret: VPS_SSH_KEY
cat ~/.ssh/vps_deploy_key.pub  # → paste into /home/deploy/.ssh/authorized_keys on VPS
```

**Add these 5 secrets to GitHub** (repo → Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `VPS_HOST` | VPS IP address |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Contents of `~/.ssh/vps_deploy_key` |
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your chat ID |

**Enable branch protection on `main`** (repo → Settings → Branches):
- Require a pull request before merging
- Require status checks to pass: `CI / test`

---

## Going Live Checklist

Before switching from dry_run to live trading:

- [ ] Bot ran stable on VPS for ≥48h in dry_run mode (via `docker-compose.yml`)
- [ ] All pairs trained successfully — check logs for `Done training <PAIR>` for all 16 pairs (BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET, HYPE, ZRO, MORPHO, XMR, KITE)
- [ ] 2h report received via log sync — confirms cron + reporting pipeline works
- [ ] Web UI accessible via SSH tunnel
- [ ] Telegram trade notifications working
- [ ] Live `.env` values confirmed (Bybit live keys, JWT secret, strong password)
- [ ] `backup-models.sh` tested — confirmed R2 backup appears
- [ ] Set `COMPOSE_FILE=docker-compose.live.yml` permanently on VPS so all `docker compose` commands (including CI/CD `restart.sh`) use the live file:
  ```bash
  echo 'COMPOSE_FILE=docker-compose.live.yml' | sudo tee -a /etc/environment
  # Log out and back in, then verify: echo $COMPOSE_FILE
  ```
- [ ] Switch: `docker compose down && docker compose up -d` (will now use live compose file)

---

## Upgrade Path (When NLP Features Go Live)

When LunarCrush/NewsNLP signals are enabled, RAM usage will exceed CAX11's 4GB. Upgrade to CAX21:

1. Hetzner Cloud Console → server → "Rescale"
2. Power off server
3. Select **"CPU and RAM only"** (keeps 40GB disk → can downgrade later if needed)
4. Choose CAX21 → Rescale → server auto-restarts in ~2-3 minutes
5. IP, data, `.env`, models: all preserved. No config changes needed.
