# Prerequisites

## Required

- **Docker Desktop** — the bot runs entirely inside Docker. Tested on macOS. Download from [docker.com](https://www.docker.com/products/docker-desktop/).
- **Bybit account** with API access enabled — see [Exchange Setup](exchange-setup.md)
- **Telegram app + account** — for trade notifications and bot control
- **Git** — for cloning the repo

## Optional

- **Python 3.11+** — only needed for local development/testing, NOT for Docker deployment

## Important Note

The bot runs entirely inside Docker. You do not need to install Python packages, Freqtrade, or XGBoost on your host machine. Docker handles all dependencies.
