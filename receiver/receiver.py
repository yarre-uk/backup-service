import os
import sys
import yaml
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn


class BackupManager:
    def __init__(self, config):
        self.config = config
        self.games = config['games']
        
        # Create archive directories
        for game_name, game_config in self.games.items():
            os.makedirs(game_config['archive_path'], exist_ok=True)
            print(f"[{game_name}] Archive: {game_config['archive_path']}")
            print(f"[{game_name}] Max size: {game_config['max_size_gb']} GB")
    
    def save_backup(self, game_name: str, file: UploadFile):
        if game_name not in self.games:
            raise ValueError(f"Unknown game: {game_name}")
        
        game_config = self.games[game_name]
        archive_path = game_config['archive_path']
        
        # Save file
        file_path = os.path.join(archive_path, file.filename)
        
        print(f"[{game_name}] Receiving: {file.filename}")
        
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"[{game_name}] ✓ Saved: {file.filename} ({file_size_mb:.2f} MB)")
        
        # Check and enforce size limit
        self.enforce_size_limit(game_name)
        
        # Show current stats
        self.show_stats(game_name)
        
        return file_path
    
    def enforce_size_limit(self, game_name: str):
        game_config = self.games[game_name]
        archive_path = game_config['archive_path']
        max_size_gb = game_config['max_size_gb']
        
        if max_size_gb <= 0:
            return
        
        max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        
        # Get all backups sorted by modification time (oldest first)
        backups = sorted(
            Path(archive_path).iterdir(),
            key=lambda x: x.stat().st_mtime
        )
        
        # Calculate total size
        total_size = sum(b.stat().st_size for b in backups if b.is_file())
        
        # Remove oldest until under limit
        removed = 0
        while total_size > max_size_bytes and backups:
            oldest = backups.pop(0)
            if oldest.is_file():
                file_size = oldest.stat().st_size
                oldest.unlink()
                total_size -= file_size
                removed += 1
                print(f"[{game_name}] Removed old backup: {oldest.name} (size limit)")
        
        if removed > 0:
            total_gb = total_size / (1024**3)
            print(f"[{game_name}] Cleanup: removed {removed} backups, now {total_gb:.2f}/{max_size_gb} GB")
    
    def show_stats(self, game_name: str):
        game_config = self.games[game_name]
        archive_path = game_config['archive_path']
        
        backups = list(Path(archive_path).iterdir())
        backup_files = [b for b in backups if b.is_file()]
        total_size = sum(b.stat().st_size for b in backup_files)
        total_size_gb = total_size / (1024**3)
        
        print(f"[{game_name}] Archive: {len(backup_files)} backups, {total_size_gb:.2f} GB\n")
    
    def get_stats(self, game_name: str = None):
        if game_name:
            games = {game_name: self.games[game_name]}
        else:
            games = self.games
        
        stats = {}
        for gname, game_config in games.items():
            archive_path = game_config['archive_path']
            backups = list(Path(archive_path).iterdir())
            backup_files = [b for b in backups if b.is_file()]
            total_size = sum(b.stat().st_size for b in backup_files)
            
            stats[gname] = {
                'backup_count': len(backup_files),
                'total_size_gb': round(total_size / (1024**3), 2),
                'max_size_gb': game_config['max_size_gb'],
                'backups': [
                    {
                        'filename': b.name,
                        'size_mb': round(b.stat().st_size / (1024**2), 2),
                        'modified': datetime.fromtimestamp(b.stat().st_mtime).isoformat()
                    }
                    for b in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]
                ]
            }
        
        return stats


# Initialize FastAPI
app = FastAPI(title="Backup Receiver", version="1.0")
manager = None


@app.post("/backup")
async def receive_backup(
    game_name: str = Form(...),
    file: UploadFile = File(...)
):
    print(f"asd")

    try:
        file_path = manager.save_backup(game_name, file)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Backup received: {file.filename}",
                "game_name": game_name,
                "filename": file.filename
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save backup: {str(e)}")


@app.get("/stats")
async def get_stats(game_name: str = None):
    try:
        stats = manager.get_stats(game_name)
        return JSONResponse(status_code=200, content=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    global manager
    
    parser = argparse.ArgumentParser(description='Backup Receiver - HTTP server')
    parser.add_argument('--config', '-c', required=True, help='Path to config file')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    if 'games' not in config:
        print("Error: 'games' section missing in config")
        sys.exit(1)
    
    # Initialize manager
    manager = BackupManager(config)
    
    print("\n=== Backup Receiver Started ===")
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  POST /backup - Receive backup")
    print(f"  GET  /stats  - View statistics")
    print(f"  GET  /health - Health check\n")
    
    # Start server
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == '__main__':
    main()
