# Running the Bot

## Docker Commands

| Action | Command |
|---|---|
| Start (first time or after code changes) | `docker compose up --build -d` |
| Start (restart with existing build) | `docker compose up -d` |
| Stop | `docker compose down` |
| View recent logs | `docker compose logs --tail 50` |
| Follow logs live | `docker compose logs -f` |
| Rebuild after pip package changes | `docker compose build --no-cache && docker compose up -d` |

## Rebuilding After Changes

- **Strategy code changes**: `docker compose up --build -d` (rebuilds and restarts)
- **New pip packages added to Dockerfile**: `docker compose build --no-cache` (cache bust required)
- **Config changes only**: `docker compose down && docker compose up -d` (restart picks up config)

## Dockerfile Structure

- **Base image**: `freqtradeorg/freqtrade:stable`
- **Added packages**: xgboost, lightgbm, torch, transformers, httpx, datasieve
- **Note**: `datasieve` is required by FreqAI but not in the base image — see [Docker Issues](../debugging/docker-issues.md) if you hit a `ModuleNotFoundError`

## docker-compose.yml Structure

- **Volume mounts**:
  - `./user_data:/freqtrade/user_data` — live sync of strategy, config, models
  - `./.env:/freqtrade/.env` — environment variables
  - `./logs:/freqtrade/user_data/logs` — log files for rotation and reports
- **Port**: `8080:8080` for web UI
- **Log file**: `--logfile user_data/logs/freqtrade.log` — writes to both stdout AND a file for rotation
- **Command**: `trade --config ... --strategy ... --freqaimodel XGBoostRegressor --dry-run`

**IMPORTANT**: The command does NOT include the `freqtrade` prefix because the Docker entrypoint already includes it. Adding it causes a `freqtrade freqtrade trade` double-command error. See [Docker Issues](../debugging/docker-issues.md).

## docker-compose.live.yml

Same structure but uses `config.live.json` and no `--dry-run` flag.

**Note**: This file still has the old `freqtrade trade` prefix in the command — it needs updating before live use. See [Going Live](going-live.md).
