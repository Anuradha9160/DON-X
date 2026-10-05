# HTR-X — Ultra-Speed Telegram Mirror & Leech Bot


## What changed in this release

### Telegram UI
- Completely removed native Telegram **Rich Message** / Rich TL message generation.
- Removed the Rich Message fallback/conversion path.
- All bot messages now use reliable normal Telegram HTML formatting.
- UI uses clean **bold**, *italic*, `<code>monospace`, blockquotes, compact sections, and consistent buttons.
- Removed Rich-specific dependencies from help, status, settings, and IMDb output.
- Status/help/settings no longer attempt a second Rich-message request when Telegram rejects a payload.

- Detects Cloud Resume, Instant DL, Cloud/R2 and Direct Server variants.
- Detects newer `data-href`, `data-url`, `data-download`, worker, R2 and JavaScript-generated URLs.
- Avoids falsely failing when a CDN does not support HEAD requests.
- Pack links resolve each contained file independently.

### Speed
HTR-X now defaults to a more aggressive transfer profile:
- Hyper Telegram pipeline: **64**
- Hyper Telegram chunk: **8 MiB**
- Stream pipeline: **32**
- Stream clients per client: **12**
- Status refresh: **5 seconds**
- Hyper download remains enabled by default.

Actual speed still depends on Telegram/DC limits, source server/CDN, VPS network, CPU/RAM, disk I/O, and provider rate limits. These settings maximize concurrency without pretending that an unlimited network speed is possible.

## Quick start

### Docker

```bash
git clone <your-repository-url> HTR-X
cd HTR-X
docker compose up -d --build
```

### Existing installation

```bash
cd HTR-X-Main
python3 -m compileall bot plugins tests
bash start.sh
```

If the project is managed by systemd, make sure `ExecStart` points to the actual checkout directory.

## Required configuration

Configure the values required by your deployment in `config.py` or through the project's supported database/config workflow:

- `BOT_TOKEN`
- `TELEGRAM_API`
- `TELEGRAM_HASH`
- `OWNER_ID`
- `DATABASE_URL` when database storage is enabled

Do not publish bot tokens, API hashes, session strings, cookies, passwords, or database credentials.

## Speed tuning

Recommended starting values:

```python
USE_HYPER = True
HYPER_THREADS = 0
HYPER_PIPELINE = 64
HYPER_CHUNK = 8 * 1024 * 1024

STREAM_PIPELINE = 32
STREAM_CHUNK = 2097152
STREAM_PER_CLIENT = 12
STATUS_UPDATE_INTERVAL = 5
```

For a small VPS, reduce pipeline/client counts if memory usage becomes high. For a high-bandwidth VPS, these values can be increased carefully after measuring CPU, RAM, network and Telegram flood waits.



1. Confirm the URL opens normally in a browser.
2. Retry the bot after a short delay if the provider/CDN has expired the generated link.
3. Check the bot log for the resolver's candidate/fallback error.
5. Test with a normal `/file/` URL before testing a large pack.

The resolver intentionally tries multiple download variants instead of assuming one permanent endpoint.

## YouTube

HTR-X can use yt-dlp and configured cookies/JS runtimes where required by the target platform. Keep cookies private and use a valid Netscape cookie file when a site requires authenticated access.

## FFmpeg

FFmpeg-based operations can be CPU intensive. The bot supports configurable processing options and limits. Keep enough CPU/RAM available when running downloads and encoding simultaneously.

## Security

- Never commit `cookies.txt`, `.netrc`, session strings, API credentials, or database URLs.
- Restrict owner/sudo settings carefully.
- Use private dumps/auth chats only where the bot account has permission.
- Keep the VPS operating system and Python dependencies updated.
- Do not expose internal service ports unnecessarily.

## Diagnostics

Compile all Python modules:

```bash
python3 -m compileall bot plugins tests
```

Run the regression tests:

```bash
pytest -q
```

Check service status:

```bash
systemctl status wzml_bot --no-pager
```

Follow logs:

```bash
journalctl -u wzml_bot -f
```

## Project structure

- `bot/` — Telegram bot and core task logic
- `bot/helper/mirror_leech_utils/` — download/upload engines and resolvers
- `bot/helper/telegram_helper/` — Telegram messaging, buttons and transfers
- `plugins/` — optional plugin modules
- `tests/` — regression and feature tests
- `web/` — web/stream components
- `deploy.vps` — VPS deployment helper
- `docker-compose.yml` — container deployment

## License

Use the license and upstream notices included with the project. HTR-X modifications should preserve applicable upstream attribution and licenses.


## Uphoster destinations

Uphoster destination selection supports the existing DDL uploaders plus configurable
API destinations for **GDFlix, HubCloud, FilePress, LuluStream, StreamTape, FileMoon,
UploadHub, and FileStreams**. Configure each host's current official upload endpoint
and API key (when required) before selecting it. The bot intentionally does **not**
guess undocumented upload endpoints.

**GDFlix link resolving/downloading has been removed.** GDFlix remains available only
as an upload-destination slot when a valid upload API endpoint is configured.

## Cookie / Login method

`/cookiesettings` now lets each supported platform choose:

- **Cookie Method** — upload a Netscape `cookies.txt`.
- **Login Method** — store username/email + password for yt-dlp extractors that
  natively support credentials.

Credentials are stored per user and should only be used for accounts the user is
authorized to access. Unsupported sites still require their normal supported
authentication mechanism.
