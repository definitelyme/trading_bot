# VPS Setup Guide

Complete setup for a fresh Hetzner CAX11 (Ubuntu 24.04 LTS) running the AI Crypto Trader in **dry-run mode** — the same paper-trading mode you run on your Mac, but on a 24/7 server.

> **This guide is NOT for going live.** Moving to a VPS just means your bot runs continuously without your Mac. Live trading is a separate decision — you can flip it on (or back off) any time after the VPS is stable. See [Going Live](#going-live) at the bottom of this guide.

**Estimated time**: 60–90 minutes for first setup (most time is waiting for apt/Docker/pip).

---

## Before You Begin — Accounts and Credentials You Need

You need to set up the following accounts and keys **before** you provision the VPS. Each section below walks you through exactly how.

| Account / Key | Purpose | Need before step |
|---|---|---|
| [Hetzner Cloud account](#hetzner-account-setup) | The VPS itself | Step 1 |
| [Bybit API key (read-only)](#bybit-api-key) | Market data for dry-run | Step 6 |
| [Cloudflare R2 bucket + credentials](#cloudflare-r2-setup) | Model backups | Step 5 |
| [Telegram bot token + chat ID](#telegram-setup) | Trade notifications + deploy alerts | Step 6 |
| [GitHub SSH deploy key](#cicd-setup-github-secrets) | CI/CD auto-deploy | CI/CD section |

---

## Hetzner Account Setup

### 1. Create a Hetzner Cloud Account

1. Go to [cloud.hetzner.com](https://console.hetzner.cloud/) and click **Sign Up**
2. Fill in name, email, password. You'll get a verification email — confirm it.
3. Add payment method (credit card or PayPal). Hetzner charges monthly in arrears (~€3.79/mo for CAX11).
4. If it asks for ID verification, upload a government ID photo. This is standard for Hetzner new accounts — usually approved within minutes.

### 2. Create the CAX11 Server

1. In the Hetzner Cloud Console, click **"New Project"** → name it `crypto-bot`
2. Inside the project, click **"Add Server"**
3. Configure:
   - **Location**: Nuremberg (NBG1) or any EU region close to Bybit servers
   - **Image**: Ubuntu 24.04 (not 22.04)
   - **Type**: Click **"Shared CPU - ARM64"** tab → select **CAX11** (€3.79/mo, 2 vCPU ARM, 4 GB RAM)
   - **Networking**: IPv4 enabled (you'll need the IP address)
   - **SSH Keys**: Click **"Add SSH Key"** → paste your Mac's public key:
     ```bash
     cat ~/.ssh/id_ed25519.pub  # or ~/.ssh/id_rsa.pub if you use RSA
     ```
     If you don't have an SSH key, generate one first:
     ```bash
     ssh-keygen -t ed25519 -C "your-email@example.com"
     cat ~/.ssh/id_ed25519.pub  # paste this into Hetzner
     ```
   - **Name**: `crypto-bot-1`
4. Click **"Create & Buy Now"**
5. Wait ~30 seconds. Note the **public IPv4 address** shown in the console — you'll use it everywhere as `<VPS_IP>`.

### 3. First SSH Login

```bash
ssh root@<VPS_IP>
# You should see an Ubuntu 24.04 login banner
```

> **Note**: Always work as `root` for initial setup. You'll create a `deploy` user for the bot and CI/CD. Never run the bot as root.

---

## Bybit API Key

You need a Bybit API key even in dry-run mode because Freqtrade uses it to fetch live market prices (OHLCV candles) from the exchange. For dry-run, **read-only permission is enough** — no trading permissions needed.

### Create a Read-Only Bybit API Key

1. Log into [bybit.com](https://www.bybit.com) → top-right avatar → **"API"** (or go to **Account & Security → API Management**)
2. Click **"Create New Key"**
3. Fill in:
   - **Key Name**: `freqtrade-dryrun`
   - **API Key Type**: **System-generated** (not self-generated)
   - **Permission**: Check **"Read-Only"** ONLY — do NOT enable trade permissions for dry-run
   - **IP Restriction**: Enter your **VPS IP address** (the one you noted from Hetzner). This limits the key to only work from the VPS, preventing misuse if the key leaks.
4. Complete identity verification if prompted (standard security check)
5. **Save** the API key and secret immediately — Bybit only shows the secret once
6. You now have: `BYBIT_API_KEY` and `BYBIT_API_SECRET`

> **When you go live later**: Create a second API key with **"Unified Trading"** → Spot + Derivatives permissions, with the VPS IP whitelist. Keep the read-only key separate.

---

## Cloudflare R2 Setup

R2 is Cloudflare's object storage (like S3 but cheaper — no egress fees). Used to back up your trained FreqAI models so you never lose them.

### 1. Create a Cloudflare Account

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → **"Sign Up"**
2. Free account is fine — R2 has a generous free tier (10 GB storage, 1M requests/month — well within your needs)

### 2. Enable R2

1. In Cloudflare dashboard sidebar → **"R2 Object Storage"**
2. If not enabled, click **"Purchase R2"** (it's free — the "purchase" just means you agree to terms and optionally add a card for overages you won't hit)

### 3. Create the Bucket

1. Click **"Create bucket"**
2. **Name**: `crypto-bot-backup` (must match exactly what's in `scripts/backup-models.sh`)
3. **Location**: Automatic (or choose Europe if you prefer)
4. Click **"Create bucket"**

### 4. Create R2 API Credentials (for rclone)

1. In R2 dashboard → **"Manage R2 API Tokens"** (top-right of R2 page)
2. Click **"Create API Token"**
3. Configure:
   - **Token name**: `rclone-vps`
   - **Permissions**: **"Object Read & Write"**
   - **Specify bucket**: `crypto-bot-backup`
4. Click **"Create API Token"**
5. **Save immediately**:
   - `Access Key ID` → this is `R2_ACCESS_KEY_ID`
   - `Secret Access Key` → this is `R2_SECRET_ACCESS_KEY`
   - `Endpoint URL` → looks like `https://<account_id>.r2.cloudflarestorage.com` → this is `R2_ENDPOINT`

> You'll enter these into rclone during VPS setup (Step 5 below).

---

## Telegram Setup

Freqtrade already sends trade notifications to your Telegram. The same bot and chat ID are used for CI/CD deploy alerts.

If you already have a Telegram bot token and chat ID configured (they're in your `.env`), you can skip this section — just make sure you have them on hand.

### If You Need to Create a Bot

1. Open Telegram → search for **@BotFather** → tap **Start**
2. Send: `/newbot`
3. Choose a name: `AI Crypto Trader` (display name, shown to users)
4. Choose a username: `your_crypto_bot` (must end in `bot`, used in URLs)
5. BotFather replies with your **bot token**: looks like `7123456789:AAF...` → this is `TELEGRAM_BOT_TOKEN`

### Get Your Chat ID

1. Send any message to your new bot (e.g. "hello")
2. Open this URL in a browser (replace `<TOKEN>` with your bot token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. In the JSON response, find `"chat":{"id":` — the number after it (may be negative for groups) is your `TELEGRAM_CHAT_ID`

> Alternatively: search for **@userinfobot** on Telegram → send it a message → it replies with your chat ID.

---

## VPS Provisioning

Now you have all credentials. Proceed with the VPS setup.

### Step 1: System Setup

SSH into the VPS as root:

```bash
ssh root@<VPS_IP>

# Update system packages
apt update && apt upgrade -y

# Install essentials
apt install -y git curl nano ufw fail2ban logrotate

# Install Docker (official install script — installs latest stable)
curl -fsSL https://get.docker.com | sh

# Set timezone to UTC (Freqtrade internals use UTC)
timedatectl set-timezone UTC

# Verify Docker works
docker run --rm hello-world
```

---

### Step 2: Create Deploy User

The `deploy` user runs the bot and receives CI/CD connections. Never run as root in production.

```bash
# Create user
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Let deploy read logs written by other processes
usermod -aG adm deploy

# Set a password for deploy (optional — you'll use SSH keys)
passwd deploy
```

**Add your SSH public key for the deploy user** (so you can `ssh deploy@<VPS_IP>`):
```bash
mkdir -p /home/deploy/.ssh
# Paste your Mac's public key (same one you used for root login):
echo "ssh-ed25519 AAAA... your-email@example.com" > /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Test: from your Mac, open a new terminal:
# ssh deploy@<VPS_IP>   ← should log in without password
```

---

### Step 3: Add Swap Space (Persistent)

XGBoost training peaks at ~1.5–2 GB RAM. The 2 GB swap provides a safety buffer on CAX11's 4 GB RAM.

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Make persistent across reboots
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Reduce swap aggressiveness (only use swap when RAM is >90% full)
echo 'vm.swappiness=10' >> /etc/sysctl.conf
sysctl -p

# Verify
free -h  # Should show 2G Swap
```

---

### Step 4: Firewall + fail2ban

```bash
# Allow SSH (critical — do this BEFORE enabling ufw or you'll lock yourself out)
ufw allow 22/tcp

# Block port 8080 from public internet — access via SSH tunnel only
ufw deny 8080

# Enable firewall
ufw --force enable

# Verify
ufw status

# fail2ban protects SSH from brute-force attacks (auto-bans IPs after 5 failed attempts)
systemctl enable fail2ban
systemctl start fail2ban
```

**Accessing the Freqtrade Web UI from your Mac (SSH tunnel):**
```bash
# Run on your Mac (not on VPS):
ssh -L 8080:localhost:8080 deploy@<VPS_IP>
# Then open: http://localhost:8080 in your browser
# The tunnel stays open as long as this terminal window is open
```

---

### Step 5: Install rclone + Configure Cloudflare R2

rclone is the tool that syncs models to Cloudflare R2. Install it **as the deploy user** so the config is owned by that user (cron jobs run as deploy).

```bash
# Switch to deploy user
su - deploy

# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure the R2 remote
rclone config
```

When `rclone config` runs, follow these exact steps:
```
> n                           # New remote
name> r2                      # MUST be exactly "r2"
Storage> s3                   # Type: Amazon S3 Compliant
provider> Cloudflare          # Choose "Cloudflare R2 Storage"
env_auth> false               # No — we'll enter keys manually
access_key_id> <R2_ACCESS_KEY_ID>
secret_access_key> <R2_SECRET_ACCESS_KEY>
region>                       # Leave blank (press Enter)
endpoint> <R2_ENDPOINT>       # e.g. https://abc123.r2.cloudflarestorage.com
location_constraint>          # Leave blank (press Enter)
acl>                          # Leave blank (press Enter)
> n                           # No advanced config
> y                           # Confirm
> q                           # Quit
```

**Verify R2 connection:**
```bash
# Still as deploy user:
rclone ls r2:crypto-bot-backup
# Should return empty (no files yet) — if it errors, re-run rclone config

# Exit back to root
exit
```

---

### Step 6: Clone Repo + Configure .env

```bash
# Clone repo (as root, then give ownership to deploy)
git clone git@github.com:<YOUR_GITHUB_USERNAME>/<REPO_NAME>.git /opt/crypto
chown -R deploy:deploy /opt/crypto

# Switch to deploy user for all remaining steps
su - deploy
cd /opt/crypto

# Create .env from the example template
cp .env.example .env
nano .env
```

**Fill in `.env` for dry-run mode.** You need all of these:

```bash
# ── Bybit market data access (READ ONLY — needed even for dry-run) ──────────
FREQTRADE__EXCHANGE__KEY=<your_bybit_api_key>
FREQTRADE__EXCHANGE__SECRET=<your_bybit_api_secret>

# ── Web UI credentials ────────────────────────────────────────────────────────
# Generate a secure JWT secret:
#   openssl rand -hex 32
# Example output: a3f1d8c2... (paste the full 64-char hex string)
FREQTRADE__API_SERVER__JWT_SECRET_KEY=<run: openssl rand -hex 32>

# Choose any strong password for the web UI login
FREQTRADE__API_SERVER__USERNAME=freqtrader
FREQTRADE__API_SERVER__PASSWORD=<choose-a-strong-password>

# ── Telegram notifications ────────────────────────────────────────────────────
FREQTRADE__TELEGRAM__TOKEN=<your_telegram_bot_token>
FREQTRADE__TELEGRAM__CHAT_ID=<your_telegram_chat_id>
```

**Generate the JWT secret right now:**
```bash
openssl rand -hex 32
# Copy the output and paste it as FREQTRADE__API_SERVER__JWT_SECRET_KEY
```

Verify .env is complete:
```bash
grep -E "^FREQTRADE" .env
# Should show 6 non-empty lines
```

---

### Step 7: Create Python venv for Reporting Scripts

The 2h log rotation and daily report scripts run directly on the VPS host (not inside Docker). They need Python with `requests`:

```bash
# Still as deploy user in /opt/crypto:
python3 -m venv .venv
.venv/bin/pip install requests

# Verify
.venv/bin/python3 -c "import requests; print('OK')"
```

---

### Step 8: Transfer Models from Mac (Avoid Retraining)

If your Mac has already trained FreqAI models, copy them to the VPS to avoid 5–6 hours of retraining on first start. Skip this if you want a clean start.

**Run this on your Mac** (not the VPS):
```bash
# Sync trained models from Mac to VPS
rsync -avz --progress \
  /Users/brendan/Sites/crypto/user_data/models/ \
  deploy@<VPS_IP>:/opt/crypto/user_data/models/

# Optional: also sync the dry-run trade history database
rsync -avz \
  /Users/brendan/Sites/crypto/user_data/tradesv3.dryrun.sqlite \
  deploy@<VPS_IP>:/opt/crypto/user_data/
```

---

### Step 9: Set Up VPS Log Rotation

Logs accumulate over time. This keeps 90 days on the VPS (giving your Mac rsync plenty of time to pick them up) and compresses old files to save disk space.

**Run as root:**
```bash
cat > /etc/logrotate.d/crypto-bot << 'EOF'
/opt/crypto/logs/*.log {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d
}
EOF

# Test the config is valid
logrotate --debug /etc/logrotate.d/crypto-bot
```

This means:
- Logs rotate daily, keeping 90 days of history (compressed)
- If your Mac is offline for up to 90 days, no logs are lost when it reconnects
- Old logs are compressed (.gz) — rsync will sync those too

---

### Step 10: Run Setup Script (Installs Cron Jobs + Starts Docker)

```bash
# As deploy user:
su - deploy
cd /opt/crypto
./scripts/setup.sh
```

This will:
- Build the Docker image (~3–5 minutes first time)
- Start the container in **dry-run mode** (`docker-compose.yml`)
- Install 3 cron jobs:
  - Every 2h: log rotation + Telegram report
  - Daily at 23:59: daily performance report
  - Daily at 03:00 UTC: model backup to Cloudflare R2

---

### Step 11: Verify Everything is Running

```bash
# Container status
docker compose ps
# Expected: freqtrade running, Up X minutes

# Live log tail (watch for "Starting dry run trading" and pair training messages)
docker compose logs --tail 50 -f
# Ctrl+C to stop tailing

# Check cron jobs installed
crontab -l | grep -E "(two-hour-report|daily-report|backup-models)"
# Should show 3 cron entries

# Check log file is being written
ls -lh /opt/crypto/logs/freqtrade.log
# Should show a non-zero file size

# Manual model backup test (optional — runs immediately, requires R2 configured)
./scripts/backup-models.sh
```

**Expected first-boot behavior:**
- FreqAI will start downloading historical data for all pairs (~10–15 minutes)
- Then training begins for each pair (~20–30 minutes each if starting fresh)
- Trades will start appearing in Telegram once training completes
- If you transferred models from Mac (Step 8), training is skipped and trading starts immediately

---

## Mac Log Sync Setup

Set up your Mac to automatically pull logs from the VPS. This gives you local access to all logs for debugging and analysis.

**On your Mac**, open Terminal and run:
```bash
crontab -e
```

Add these two lines (replace `<VPS_IP>`):
```bash
# Pull VPS logs to Mac every hour — no --delete means local logs are never removed
# If Mac is offline, rsync just fails silently and catches up next time it runs
0 * * * * rsync -az deploy@<VPS_IP>:/opt/crypto/logs/ /Users/brendan/Sites/crypto/logs/ >> /tmp/vps-log-sync.log 2>&1

# Also sync the dry-run trade database every hour (for local analysis)
5 * * * * rsync -az deploy@<VPS_IP>:/opt/crypto/user_data/tradesv3.dryrun.sqlite /Users/brendan/Sites/crypto/user_data/ >> /tmp/vps-log-sync.log 2>&1
```

**What happens when your Mac is offline?**
- rsync fails silently — no data is lost on the VPS (logs stay there for 90 days)
- When your Mac reconnects, the next hourly cron run picks up everything that was missed
- rsync is incremental: it only copies files that are new or changed since the last sync
- You'll never lose logs as long as you reconnect within 90 days (the VPS retention window)

**Check the sync log:**
```bash
tail -20 /tmp/vps-log-sync.log
# Shows the last sync result
```

---

## CI/CD Setup (GitHub Secrets)

The GitHub Actions deploy pipeline (`deploy.yml`) automatically deploys to the VPS when you merge a PR to `main`. It needs SSH access to the VPS.

### 1. Generate a Dedicated Deploy SSH Key (on your Mac)

This key is separate from your personal SSH key — it's only used by GitHub Actions.

```bash
# Generate (no passphrase — GitHub Actions can't enter one interactively)
ssh-keygen -t ed25519 -f ~/.ssh/vps_deploy_key -C "github-actions-deploy" -N ""

# View the private key (paste into GitHub secret VPS_SSH_KEY):
cat ~/.ssh/vps_deploy_key

# View the public key (add to VPS authorized_keys):
cat ~/.ssh/vps_deploy_key.pub
```

### 2. Add the Public Key to the VPS

```bash
# On the VPS, as root:
echo "<paste the .pub key content here>" >> /home/deploy/.ssh/authorized_keys

# Test from your Mac:
ssh -i ~/.ssh/vps_deploy_key deploy@<VPS_IP> echo "CI/CD key works"
```

### 3. Add Secrets to GitHub

Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add each of these 5 secrets:

| Secret name | Where to get it | Example value |
|---|---|---|
| `VPS_HOST` | Your Hetzner IPv4 address | `65.21.xxx.xxx` |
| `VPS_USER` | Always `deploy` | `deploy` |
| `VPS_SSH_KEY` | Contents of `~/.ssh/vps_deploy_key` (the private key, starts with `-----BEGIN OPENSSH PRIVATE KEY-----`) | multiline |
| `TELEGRAM_BOT_TOKEN` | From BotFather when you created the bot | `7123456789:AAF...` |
| `TELEGRAM_CHAT_ID` | Your Telegram user/chat ID | `123456789` |

> **IMPORTANT for `VPS_SSH_KEY`**: Copy the ENTIRE private key file content including the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines.

### 4. Enable Branch Protection on `main`

Go to your repo → **Settings** → **Branches** → **Add branch protection rule**:
- Branch name pattern: `main`
- Check: **"Require a pull request before merging"**
- Check: **"Require status checks to pass before merging"**
  - Search for and add: `CI / test` (this is the job name in `ci.yml`)
- Click **"Create"**

---

## VPS Reliability Notes

**Hetzner Cloud (CAX11) uptime in practice:**
- Independent monitoring records **99.96–99.99% uptime** for running instances
- In the 6 months to March 2026: zero incidents causing running servers to go offline
  - February 2026 "limited availability" — only affects *new* server creation, not running servers
  - March 2026 rescale delay — only affects disk-resize operations, not running servers
- The `restart: unless-stopped` Docker policy automatically recovers from:
  - Container crashes (OOM, segfaults)
  - VPS reboots (after maintenance)
  - Docker daemon restarts
- **Assessment**: For a dry-run crypto bot, occasional brief maintenance windows have zero financial impact. No additional countermeasures needed beyond the restart policy already in place.

**Sources**: [Hetzner status page](https://status.hetzner.com/) · [Better Stack review](https://betterstack.com/community/guides/web-servers/hetzner-cloud-review/) · [StatusGator history](https://statusgator.com/services/hetzner/cloud-server)

---

## Verify Bot is Working

After setup, confirm these within the first 24 hours:

```bash
# 1. Container healthy
docker compose ps

# 2. No error-level log entries (should see training/trading messages)
docker compose logs --tail 100 | grep -i "error\|exception\|critical" || echo "No errors"

# 3. Telegram: you should have received a "Freqtrade started" message
# 4. Web UI (via SSH tunnel): http://localhost:8080
# 5. Check model training progress
docker compose logs --tail 100 | grep -i "training\|done training"
```

---

## Going Live

This section is for when you've run the bot in dry-run on the VPS for ≥48 hours and are ready to use real money. **Skip this until you're ready.**

### Prerequisites
- [ ] Bot ran stable on VPS for ≥48h in dry_run (using `docker-compose.yml`)
- [ ] All 11 pairs trained — check logs for `Done training <PAIR>` for: BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET
- [ ] Telegram notifications confirmed working
- [ ] Web UI accessible via SSH tunnel
- [ ] `backup-models.sh` tested — R2 backup confirmed

### Switch Steps

**1. Create live Bybit API keys** (separate from read-only dry-run keys):
- Bybit → API Management → New Key → **"Unified Trading"** permissions → Spot + Derivatives (not Perpetual if you're not using leverage)
- Set IP whitelist to VPS IP
- Save the new `KEY` and `SECRET`

**2. Update `.env` on VPS with live keys:**
```bash
ssh deploy@<VPS_IP>
cd /opt/crypto
nano .env  # Update FREQTRADE__EXCHANGE__KEY and FREQTRADE__EXCHANGE__SECRET
```

**3. Set COMPOSE_FILE permanently so all docker compose commands use live config:**
```bash
# As root:
echo 'COMPOSE_FILE=docker-compose.live.yml' >> /etc/environment
# Log out and back in, verify:
echo $COMPOSE_FILE  # should show: docker-compose.live.yml
```

**4. Backup current models, then switch:**
```bash
cd /opt/crypto
./scripts/backup-models.sh          # Backup dry-run models to R2
docker compose down                  # Stop dry-run container
docker compose up -d                 # Now uses docker-compose.live.yml
docker compose logs --tail 30        # Verify it starts with live config
```

**5. To revert to dry-run at any time:**
```bash
docker compose down
unset COMPOSE_FILE  # Or remove from /etc/environment and relogin
docker compose up -d                 # Back to docker-compose.yml (dry-run)
```

---

## Upgrade Path (When NLP Features Go Live)

When LunarCrush/NewsNLP signals are enabled, RAM usage will exceed CAX11's 4 GB. Upgrade to CAX21 (€5.77/mo, 8 GB RAM):

1. Hetzner Cloud Console → your server → **"Rescale"**
2. Power off server (button in UI — Docker will restart via `restart: unless-stopped` after)
3. Select **"CPU and RAM only"** ← important: keeps 40 GB disk, preserves downgrade option
4. Choose **CAX21** → click **Rescale** → server restarts in ~2–3 minutes
5. Everything preserved: IP, `.env`, models, trade history, cron jobs. No config changes needed.
