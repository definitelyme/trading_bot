# Web UI Issues

## Web UI Not Loading

**Symptom**: `ERR_CONNECTION_REFUSED` in browser.

**Cause**: Bot not running, or `api_server.enabled: false`, or wrong port.

**Fix**:
1. Check the container is running: `docker compose ps`
2. Verify config has `api_server.enabled: true`
3. Check port mapping in `docker-compose.yml` (should be `8080:8080`)

---

## "400 Bad Request" in Logs

**Symptom**: Repeated `connection rejected (400 Bad Request)` in logs, web UI not working.

**Cause**: JWT secret key too short. Must be 32+ bytes for SHA256.

**Log indicator**: `InsecureKeyLengthWarning: The HMAC key is 30 bytes long, which is below the minimum recommended length of 32 bytes`

**Fix**: Generate a proper key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Set the output as `jwt_secret_key` in config.

---

## "Login failed, Username or Password wrong"

**Symptom**: Web UI login page rejects credentials.

**Cause**: Wrong password. Default is `change-this-password` (not `password`).

**Fix**: Check `api_server.username` and `api_server.password` in `config.json`. Use those exact values.

---

## listen_ip_address Inside Docker

**Symptom**: Web UI at `localhost:8080` shows nothing or refuses connection.

**Cause**: Config has `listen_ip_address: "127.0.0.1"` — inside Docker, this means the container's own loopback only. The host machine can't reach it.

**Fix**: Change to `"0.0.0.0"` to accept connections from outside the container.

**Note**: For live trading, use `127.0.0.1` for security (restrict to local access only).
