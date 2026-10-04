# HTR-X

**HTR-X** is a fast, configurable Telegram mirror/leech bot for VPS deployments. It combines Telegram MTProto transfers with Aria2, qBittorrent, Mega, NZB, Rclone, Google Drive, JDownloader, direct downloads, and yt-dlp.

## Highlights

- ⚡ Fast mirror/leech pipeline with queue and task controls
- 🎬 YouTube/yt-dlp downloads with per-user cookies and Telegram session-aware workflows
- 🔐 Per-user Telegram session strings for private/restricted Telegram links
- 🧩 yt-dlp JavaScript challenge support through Deno or supported Node.js
- ☁️ Mega downloads/uploads, including folder and nested-content workflows
- 🎛️ Advanced merge, FFmpeg, metadata, thumbnail, track and media-processing tools
- 🧭 Inline menus, pagination, progress/status messages and lightweight UI
- 🐳 Docker and direct VPS/systemd deployment

## Requirements

- Linux VPS (recommended)
- Python 3.10+ for direct deployment
- Telegram bot token, API ID and API hash
- MongoDB
- FFmpeg
- Optional: Aria2, qBittorrent, rclone, SABnzbd, JDownloader, Google Drive, Mega and other integrations

## VPS deployment

```bash
git clone <your-htr-x-repository> HTR-X
cd HTR-X
chmod +x deploy.vps
./deploy.vps
```

The deployment script creates the `htr_bot` systemd service. Check it with:

```bash
systemctl status htr_bot
journalctl -u htr_bot -f
```

## Configuration

Configure the required values through the project's supported environment/configuration system. At minimum you normally need:

- `BOT_TOKEN`
- `TELEGRAM_API`
- `TELEGRAM_HASH`
- `OWNER_ID`
- `DATABASE_URL`

Only enable integrations for which you have valid credentials.

## YouTube / yt-dlp

HTR-X supports per-user yt-dlp cookie files through the user settings. Keep exported cookies private and replace them when they expire.

For YouTube JavaScript challenges, the runtime must be available **on the actual VPS/container running the bot**. HTR-X detects Deno first and only accepts Node.js versions supported by the installed yt-dlp release. The Dockerfile includes Deno and Node.js 20.

Useful checks:

```bash
deno --version 2>/dev/null || true
node --version
yt-dlp --version
```

If the bot reports `The page needs to be reloaded`, `Requested format is not available`, or an authentication/challenge error, check the runtime, yt-dlp/yt-dlp-ejs compatibility and the user's cookie file.

## Telegram private-link sessions

Users can configure their own Telegram session string from the bot's Telegram Session settings. When a user has configured one, HTR-X uses that **user's session** when resolving private Telegram links instead of relying only on the global owner/helper session.

A configured session must belong to an account that can actually access the target private chat/message. Never share a session string with another person.

## Mega

HTR-X targets **MegaSDK v10.20.20** in its engine/version metadata and deployment configuration. The project supports both the native `megasdk` import path and the compatible `mega` Python wrapper as fallback paths.

> Note: the public PyPI `mega.py` package is a separate Python wrapper and its published release number is not the native Mega SDK version. HTR-X therefore does not pretend that `pip install mega.py` itself installs native MegaSDK 10.20.20.

Mega workflows include account login, public links, folder links, nested folders and multi-file downloads where supported by the active SDK/API implementation.

## UI

The bot uses compact status messages and inline controls with suitable emojis for common states:

- ⬇️ Downloading
- ⬆️ Uploading
- ⚙️ Processing
- ⏳ Queued
- ✅ Completed
- ❌ Failed
- 🔐 Authentication/session
- ☁️ Cloud/Mega
- 🎬 YouTube/media

## Troubleshooting

### `Private: Please report!`

Update HTR-X and ensure the user has configured a valid Telegram session string with access to the private chat. The resolver now attempts the requesting user's configured session.

### YouTube has no downloadable formats

Check:

```bash
which deno
deno --version
node --version
yt-dlp --version
python -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

Then refresh the user's cookie export if the video requires authentication.

### Mega SDK unavailable

Check the installed Python environment and import path:

```bash
python -c "from mega import MegaApi; print(MegaApi)"
```

If your deployment uses a native `megasdk` build, verify that its native library and Python bindings are installed together.

## Project layout

```text
HTR-X/
├── bot/                 # Telegram bot and transfer engines
├── configs/             # Service configuration
├── docs/                # Documentation/assets
├── plugins/             # Optional plugins
├── web/                 # Web/selector UI
├── Dockerfile
├── docker-compose.yml
├── deploy.vps
├── requirements.txt
└── README.md
```

## Security

- Never commit `BOT_TOKEN`, API credentials, cookies, or Telegram session strings.
- Treat user session strings as full account credentials.
- Restrict VPS access and protect MongoDB/Redis endpoints.
- Use fresh cookie exports when required and remove old credentials from logs.

## Credits

HTR-X is based on the upstream WZML-X project and retains required upstream technical compatibility where necessary. Upstream references are kept for compatibility and attribution; the user-facing project branding is **HTR-X**.

## License

See [LICENSE](LICENSE).


## 🎬 HTR-X Track Merge

- `/merge` (`/tmerge`) supports a replied video plus external **audio tracks and subtitles**.
- Add tracks from Telegram files or direct download URLs.
- For extensionless URLs use `audio|URL` or `sub|URL`.
- Interactive planner supports track reorder, remove, output rename, and **audio/subtitle language + title editing**.
- `🚀 Done & Start` starts FFmpeg muxing immediately.
- `/merge` and all plugin aliases automatically honor `CMD_SUFFIX`.

## 📊 MediaInfo

- `/mediainfo` and `/mi` honor `CMD_SUFFIX`.
- Reply to a video/audio/document or pass a direct download URL.
- MediaInfo links are published through **PastyX** when available, with Telegraph fallback.
- URL inputs are downloaded completely before MediaInfo analysis (not just the first chunk).
