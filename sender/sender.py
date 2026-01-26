import os
import sys
import time
import yaml
import argparse
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class BackupSender(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.game_name = config['game_name']
        self.watch_dir = config['watch_directory']
        self.receiver_url = config['receiver_url']
        self.max_local_backups = config.get('max_local_backups', 5)
        self.backup_extensions = config.get('backup_extensions', ['.tar.gz', '.zip', '.tar'])
        
        print(f"[{self.game_name}] Initialized backup sender")
        print(f"[{self.game_name}] Watching: {self.watch_dir}")
        print(f"[{self.game_name}] Receiver: {self.receiver_url}")
        print(f"[{self.game_name}] Max local backups: {self.max_local_backups}")
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if not self._is_backup_file(event.src_path):
            return
        
        print(f"\n[{self.game_name}] New backup detected: {os.path.basename(event.src_path)}")
        
        # Wait for file to finish writing
        if self._wait_for_file_stable(event.src_path):
            if self.send_backup(event.src_path):
                print(f"[{self.game_name}] ✓ Successfully sent backup")
            else:
                print(f"[{self.game_name}] ✗ Failed to send backup")
    
    def _is_backup_file(self, filepath):
        return any(filepath.endswith(ext) for ext in self.backup_extensions)
    
    def _wait_for_file_stable(self, filepath, timeout=60):
        print(f"[{self.game_name}] Waiting for file to finish writing...")
        previous_size = -1
        stable_count = 0
        start_time = time.time()
        
        while True:
            if not os.path.exists(filepath):
                return False
            
            try:
                current_size = os.path.getsize(filepath)
            except OSError:
                time.sleep(2)
                continue
            
            if current_size == previous_size:
                stable_count += 1
                if stable_count >= 3:
                    return True
            else:
                stable_count = 0
            
            previous_size = current_size
            time.sleep(2)
            
            if time.time() - start_time > timeout:
                print(f"[{self.game_name}] Timeout waiting for file stability")
                return False
    
    def send_backup(self, filepath):
        filename = os.path.basename(filepath)
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        
        print(f"[{self.game_name}] Sending {filename} ({file_size_mb:.2f} MB)...")
        
        try:
            with open(filepath, 'rb') as f:
                files = {'file': (filename, f, 'application/octet-stream')}
                data = {'game_name': self.game_name}

                print(f"sending to", self.receiver_url)
                
                
                response = requests.post(
                    self.receiver_url,
                    files=files,
                    data=data,
                    timeout=600  # 10 minute timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"[{self.game_name}] Server response: {result.get('message', 'OK')}")
                    return True
                else:
                    print(f"[{self.game_name}] Server error: {response.status_code} - {response.text}")
                    return False
                    
        except requests.exceptions.Timeout:
            print(f"[{self.game_name}] Upload timeout")
            return False
        except requests.exceptions.ConnectionError:
            print(f"[{self.game_name}] Connection error - is receiver running?")
            return False
        except Exception as e:
            print(f"[{self.game_name}] Error: {e}")
            return False


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description='Backup Sender - Watch and send backups via HTTP')
    parser.add_argument('--config', '-c', required=True, help='Path to config file')
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Validate config
    required_fields = ['game_name', 'watch_directory', 'receiver_url']
    for field in required_fields:
        if field not in config:
            print(f"Error: Missing required field '{field}' in config")
            sys.exit(1)
    
    # Create watch directory if it doesn't exist
    os.makedirs(config['watch_directory'], exist_ok=True)
    
    # Set up file watcher
    event_handler = BackupSender(config)
    observer = Observer()
    observer.schedule(event_handler, config['watch_directory'], recursive=False)
    
    print(f"\n[{config['game_name']}] === Backup Sender Started ===\n")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[{config['game_name']}] === Stopping Backup Sender ===")
        observer.stop()
    
    observer.join()


if __name__ == '__main__':
    main()
