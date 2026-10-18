# CDML-X — VPS Deployment

> A Telegram mirror/leech bot intended for a Linux VPS. The one-click installer configures system packages, a Python virtual environment, the bot service, and its local helper services.

## One-click deployment (VPS only)

> **Supported:** Ubuntu/Debian-based Linux VPS. A root shell works directly. A non-root login is supported when `sudo` is installed and the account is allowed to use it. A non-root account without root/sudo access cannot install system packages or create system services.

### 1. Get the project

```bash
cd /bot1
git clone https://github.com/hemanthbreaker3-hash/CDML-X.git CDML-X
cd CDML-X
```

If you already uploaded/extracted the ZIP, `cd` into the extracted `CDML-X` directory instead.

### 2. Configure credentials

Set these in your shell before running the installer, or put the values in the project's `config.py`. Replace every placeholder with your own values.

```bash
export BOT_TOKEN='REPLACE_WITH_BOT_TOKEN'
export TELEGRAM_API='REPLACE_WITH_TELEGRAM_API_ID'
export TELEGRAM_HASH='REPLACE_WITH_TELEGRAM_API_HASH'
export OWNER_ID='YOUR_TELEGRAM_USER_ID'
export DATABASE_URL='REPLACE_WITH_MONGODB_URI'
export CMD_SUFFIX='a'
```

Optional start-menu buttons can be set too:

```bash
export START_REPO_URL='https://t.me/your_repository_channel'
export START_REPO_BUTTON='Repository'
export START_UPDATE_URL='https://t.me/your_updates_channel'
export START_UPDATE_BUTTON='Updates'
export START_DEV_URL='https://t.me/your_developer_channel'
export START_DEV_BUTTON='Developer'
```

> Keep credentials private. Never commit `config.py` containing real secrets or paste tokens into public chats. If a token has been exposed, revoke and regenerate it.

### 3. Run the installer

**Root VPS:**

```bash
chmod +x one-click-deploy.sh deploy.vps start.sh
./one-click-deploy.sh
```

**Non-root VPS login with sudo permission:** use the same command. The script requests sudo and transfers only the documented deployment variables through a private temporary file; it does not use `sudo -E` or preserve your entire environment.

```bash
chmod +x one-click-deploy.sh deploy.vps start.sh
./one-click-deploy.sh
```

**If sudo says your user is not allowed** (for example, `I'm sorry ... I can't do that`), stop here: this is a VPS sudoers/provider permission rule, not a script bug. Log in as root, or ask the VPS administrator/provider to grant your account the required sudo permission. No deployment script can safely override that restriction. A non-root account without root/sudo cannot install `apt` packages or create system services.

## Check service and logs

```bash
systemctl status cantarellabots_bot --no-pager -l
journalctl -u cantarellabots_bot -f
```

The YouTube token helper service is managed separately:

```bash
systemctl status bgutil-ytdlp-pot-provider --no-pager -l
journalctl -u bgutil-ytdlp-pot-provider -f
```

## Upload speed notes

> Telegram upload speed depends on VPS network throughput, route/peering, CPU, storage read speed, Telegram limits, and account/session restrictions. A 100 Mbps VPS link has a theoretical ceiling of about **12.5 MB/s** before overhead; this installer cannot guarantee that sustained rate. The client enables concurrent transmissions, and the uploader avoids an unnecessary fixed delay before flushing grouped media. Do not raise concurrency blindly: it can increase RAM usage and trigger Telegram flood limits.

## Troubleshooting

- Check `journalctl -u cantarellabots_bot -n 200 --no-pager` for startup errors.
- Confirm the VPS can resolve and reach GitHub, Telegram, and your database host.
- Ensure `BOT_TOKEN`, `TELEGRAM_API`, `TELEGRAM_HASH`, `OWNER_ID`, and `DATABASE_URL` are valid.
- If a port is already in use, identify the process before stopping anything.
- Re-run `./one-click-deploy.sh` from the project directory after correcting configuration.
