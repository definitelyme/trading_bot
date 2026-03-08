# Docker Issues

## "freqtrade freqtrade trade" Double Command

**Symptom**: `Error: No such command 'freqtrade'` or unexpected behavior on startup.

**Cause**: The Docker image entrypoint already includes `freqtrade`. Adding it to the docker-compose command causes doubling: `freqtrade freqtrade trade`.

**Fix**: Remove `freqtrade` from the command in `docker-compose.yml`. Keep only `trade --config ...`.

**Prevention**: Remember the Docker entrypoint handles the `freqtrade` binary name.

---

## "ModuleNotFoundError: No module named 'datasieve'"

**Symptom**: Strategy fails to load, bot crashes on startup.

**Cause**: `datasieve` is required by FreqAI but not in the base Docker image.

**Fix**: Add `datasieve` to the `pip install` line in the Dockerfile. Rebuild with cache bust:

```bash
docker compose build --no-cache
```

**Prevention**: Always rebuild with `--no-cache` when adding new pip packages.

---

## "attempted relative import with no known parent package"

**Symptom**: Strategy import error for `risk_manager` or `signal_aggregator`.

**Cause**: Freqtrade loads strategies as standalone files, not Python packages. Relative imports (`from .risk import ...`) don't work.

**Fix**: Use the `sys.path` hack at the top of the strategy file — see [Architecture](../reference/architecture.md).

**Prevention**: Always use absolute imports with `sys.path` insertion for strategy sub-modules.

---

## Docker Not in PATH (macOS)

**Symptom**: `command not found: docker`

**Cause**: Docker Desktop binary at `/usr/local/bin/docker` may not be in the current shell PATH.

**Fix**: Ensure Docker Desktop app is running. Run commands directly in a terminal, not through automated tools.
