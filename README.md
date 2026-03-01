# Backup Service

HTTP-based backup system with automatic archiving and file transfer from remote servers to a local backup receiver.

## Used By

- [minecraft-server](https://github.com/yarre-uk/minecraft-server) — Paper Minecraft server with sender integration
- [terraria-server](https://github.com/yarre-uk/terraria-server) — Terraria server with archiver + sender integration

## Architecture

```
[ Game Server VPS ]                        [ Local Server ]
  Archiver  →  /backups  →  Sender  ───►  Receiver
```

- **Archiver**: Creates compressed archives from game server data on a schedule, with selective file inclusion
- **Sender**: Monitors the archive output directory and uploads new files via HTTP
- **Receiver**: HTTP server that receives and stores backups with size-based retention

## Features

- Scheduled archiving (configurable interval in hours)
- Selective file inclusion via glob patterns (supports `**`, `*`, `?`)
- Cron-based sending (runs every 15 minutes)
- File stability checking before transfer
- CSV-based tracking to prevent duplicate sends
- Automatic retry on failure
- Size-based archive cleanup (FIFO)
- Multiple game/service support
- Docker deployment

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/yarre-uk/backup-service.git
cd backup-service
```

### 2. Configure Services

**Archiver Configuration** (`archiver/config.yml`):

```yaml
container_name: "terraria"
interval_hours: 6
source_path: "/server"
output_path: "/backups"
archive_format: "tar.gz"
compression_level: 6
naming_pattern: "{container}-{timestamp}.tar.gz"
include_file: "/include-patterns"
```

**Receiver Configuration** (`receiver/config.yml`):

```yaml
games:
  minecraft:
    archive_path: "/archive/minecraft"
    max_size_gb: 30
  
  vintage-story:
    archive_path: "/archive/vintage-story"
    max_size_gb: 30
```

**Sender Configuration** (`sender/config.yml`):

```yaml
game_name: "minecraft"
receiver_url: "http://10.66.66.2:8080/backup"
backup_extensions:
  - ".tar.gz"
  - ".zip"
  - ".tar"
  - ".7z"
```

### 3. Deploy with Docker

**Production (using Docker Hub images):**

```bash
docker compose up -d
```

**Local development (build from source):**

```bash
docker compose -f docker-compose-local.yml up -d
```

### 4. Verify Setup

Check receiver is running:
```bash
curl http://localhost:8080/health
```

Check sender logs:
```bash
docker logs -f backup-sender-minecraft
```

## Configuration Details

### Archiver

- **container_name**: Used in the output archive filename
- **interval_hours**: How often to create an archive
- **source_path**: Root directory to archive (mount your game server data here)
- **output_path**: Where archives are written (mount the sender's watch directory here)
- **archive_format**: `tar.gz`, `tar`, or `zip`
- **compression_level**: 1 (fastest) – 9 (smallest), default 6
- **naming_pattern**: Supports `{container}` and `{timestamp}` placeholders
- **include_file**: Path to an include patterns file (optional — omit to archive everything)

### Include Patterns

The include patterns file controls which files get archived. If omitted, the entire `source_path` is archived. The format is one pattern per line; lines starting with `#` are comments.

Supported pattern syntax:

| Pattern | Matches |
|---|---|
| `Saves/` | Everything inside the `Saves/` directory |
| `*.cfg` | All `.cfg` files at the root only |
| `**/*.sav` | All `.sav` files in any subdirectory recursively |
| `world/level.dat` | A specific file at a specific path |
| `data/**/*.json` | All `.json` files under `data/` recursively |

**Example — Terraria:**
```
# World and player saves
Saves/

# Server config
serverconfig.txt
```

**Example — Minecraft:**
```
# World folders
world/
world_nether/
world_the_end/

# Server config files
server.properties
whitelist.json
ops.json
banned-players.json
```

**Example — Vintage Story:**
```
# Save files only (skip mods, logs, etc.)
**/*.vcdbs
**/*.vcdbs-journal
ModConfig/
serverconfig.json
```

### Receiver

- **archive_path**: Where backups are stored
- **max_size_gb**: Maximum total size before old backups are deleted

### Sender

- **game_name**: Identifier matching receiver's game configuration
- **receiver_url**: Full URL to receiver's `/backup` endpoint
- **backup_extensions**: File extensions to monitor and send

## Usage

### Adding New Game/Service

1. Add game to receiver config:
```yaml
games:
  new-game:
    archive_path: "/archive/new-game"
    max_size_gb: 50
```

2. Create new sender instance in `docker-compose.yml`:
```yaml
  backup-sender-new-game:
    image: yarreuk/backup-sender:latest
    container_name: backup-sender-new-game
    volumes:
      - ./sender/new-game-config.yml:/config.yml:ro
      - /path/to/backups:/watch:ro
    network_mode: host
    restart: unless-stopped
```

3. Create sender config file `sender/new-game-config.yml`

4. Restart services:
```bash
docker compose up -d
```

### Monitoring

**Check receiver statistics:**
```bash
curl http://localhost:8080/stats
curl http://localhost:8080/stats?game_name=minecraft
```

## API Endpoints

### Receiver

- `POST /backup` - Receive backup file
  - Form data: `game_name`, `file`
  
- `GET /stats` - View backup statistics
  - Query param: `game_name` (optional)
  
- `GET /health` - Health check

## How It Works

### Sender Process (Every 15 Minutes)

1. **Reconcile Directory**: Compare watch directory with CSV tracker
2. **Add New Files**: Track newly detected backup files
3. **Remove Deleted**: Clean up tracker for deleted files
4. **Stability Check**: Wait for files to finish writing (6 seconds stable)
5. **Send Backups**: Upload unsent files to receiver
6. **Mark Sent**: Update tracker on success

### Receiver Process

1. **Receive Upload**: Accept backup file via HTTP POST
2. **Save File**: Store in game's archive directory
3. **Enforce Limits**: Delete oldest backups if size exceeded
4. **Return Status**: Confirm success/failure to sender

## Troubleshooting

### Sender not sending files

Check:
- Receiver is accessible: `curl http://<receiver-url>/health`
- File extensions match config
- Files are stable (not still being written)
- Check sender logs for errors

### Receiver not receiving

Check:
- Port 8080 is accessible
- `game_name` in sender config matches receiver config
- Receiver logs for errors

### Permission errors

Ensure volumes have correct ownership:
```bash
chown -R 1000:1000 archive/ test/
```

## Development

### Build Images Locally

```bash
# Receiver
cd receiver
docker build -f receiver.Dockerfile -t backup-receiver:dev .

# Sender
cd sender
docker build -f sender.Dockerfile -t backup-sender:dev .
```

### Run Tests

Place test file:
```bash
echo "test" > test/test-backup.tar.gz
```

Monitor:
```bash
docker logs -f backup-sender-minecraft
```

## Network Requirements

- **Receiver**: Port 8080 exposed
- **Sender**: `network_mode: host` for VPN/WireGuard access
- If using WireGuard, ensure receiver URL uses VPN IP (e.g., `10.66.66.2`)
