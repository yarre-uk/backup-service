import os
import sys
import time
import yaml
import csv
import argparse
import requests
from pathlib import Path
from datetime import datetime

class ProgressFileWrapper:
    def __init__(self, file_obj, total_size, game_name):
        self.file = file_obj
        self.total_size = total_size
        self.uploaded = 0
        self.last_print = 0
        self.game_name = game_name

    def read(self, size=-1):
        data = self.file.read(size)
        self.uploaded += len(data)
    
        # Print progress every 10%
        progress = (self.uploaded / self.total_size) * 100
        if progress - self.last_print >= 10:
            print(f"[{self.game_name}] Progress: {progress:.0f}%")
            self.last_print = progress
        return data
    
    def __len__(self):
        return self.total_size


class BackupTracker:
    def __init__(self, tracker_file):
        self.tracker_file = tracker_file
        self.records = {}  # {filename: is_sent}
        self._load()
    
    def _load(self):
        if not os.path.exists(self.tracker_file):
            return
        
        with open(self.tracker_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.records[row['filename']] = row['is_sent'] == 'True'
    
    def _save(self):
        with open(self.tracker_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['filename', 'is_sent'])
            writer.writeheader()
            for filename, is_sent in self.records.items():
                writer.writerow({'filename': filename, 'is_sent': str(is_sent)})
    
    def add_file(self, filename):
        if filename not in self.records:
            self.records[filename] = False
            self._save()
    
    def mark_sent(self, filename):
        self.records[filename] = True
        self._save()
    
    def remove_file(self, filename):
        if filename in self.records:
            del self.records[filename]
            self._save()
    
    def get_unsent(self):
        return [f for f, sent in self.records.items() if not sent]


class BackupSender:
    def __init__(self, config):
        self.config = config
        self.game_name = config['game_name']
        self.watch_dir = config['watch_directory']
        self.receiver_url = config['receiver_url']
        self.backup_extensions = config.get('backup_extensions', ['.tar.gz', '.zip', '.tar'])
        
        tracker_file = os.path.join(self.watch_dir, '.backup_tracker.csv')
        self.tracker = BackupTracker(tracker_file)
        
        print(f"[{self.game_name}] Initialized backup sender")
        print(f"[{self.game_name}] Watching: {self.watch_dir}")
        print(f"[{self.game_name}] Receiver: {self.receiver_url}")
    
    def _is_backup_file(self, filepath):
        return any(filepath.endswith(ext) for ext in self.backup_extensions)
    
    def reconcile_directory(self):
        print(f"\n[{self.game_name}] Reconciling directory...")
        
        # Get current files in directory
        current_files = set()
        for file in os.listdir(self.watch_dir):
            filepath = os.path.join(self.watch_dir, file)
            if os.path.isfile(filepath) and self._is_backup_file(filepath):
                current_files.add(file)
        
        # Remove deleted files from tracker
        tracked_files = set(self.tracker.records.keys())
        deleted_files = tracked_files - current_files
        for filename in deleted_files:
            print(f"[{self.game_name}] Removing deleted file from tracker: {filename}")
            self.tracker.remove_file(filename)
        
        # Add new files to tracker
        new_files = current_files - tracked_files
        for filename in new_files:
            print(f"[{self.game_name}] New file detected: {filename}")
            self.tracker.add_file(filename)
        
        print(f"[{self.game_name}] Reconciliation complete. New: {len(new_files)}, Deleted: {len(deleted_files)}")
    
    def _wait_for_file_stable(self, filepath, timeout=60):
        print(f"[{self.game_name}] Checking file stability: {os.path.basename(filepath)}")
        previous_size = -1
        stable_count = 0
        start_time = time.time()

        while True:
            if not os.path.exists(filepath):
                print(f"[{self.game_name}] ✗ File disappeared during stability check")
                return False

            try:
                current_size = os.path.getsize(filepath)
            except OSError as e:
                print(f"[{self.game_name}] Error reading file size: {e}")
                time.sleep(2)
                continue
            
            if current_size == previous_size:
                stable_count += 1
                if stable_count >= 3:  # 3 consecutive checks with same size (6 seconds)
                    print(f"[{self.game_name}] ✓ File stable ({current_size / (1024*1024):.2f} MB)")
                return True
            else:
                stable_count = 0

            previous_size = current_size
            time.sleep(2)
        
            if time.time() - start_time > timeout:
                print(f"[{self.game_name}] ✗ Timeout waiting for file stability")
                return False

    def send_backup(self, filename):
        filepath = os.path.join(self.watch_dir, filename)

        # Check if file is still being written
        if not self._wait_for_file_stable(filepath):
            print(f"[{self.game_name}] ✗ Skipping {filename} - file not stable")
            return False

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)

        print(f"[{self.game_name}] Sending {filename} ({file_size_mb:.2f} MB)...")

        try:
            with open(filepath, 'rb') as f:
                # Wrap file object to track progress
                total_size = os.path.getsize(filepath)


                wrapped_file = ProgressFileWrapper(f, total_size, self.game_name)
                files = {'file': (filename, wrapped_file, 'application/octet-stream')}
                data = {'game_name': self.game_name}

                response = requests.post(
                    self.receiver_url,
                    files=files,
                    data=data,
                    timeout=600
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"[{self.game_name}] ✓ {result.get('message', 'OK')}")
                    return True
                else:
                    print(f"[{self.game_name}] ✗ Server error: {response.status_code} - {response.text}")
                    return False

        except requests.exceptions.Timeout:
            print(f"[{self.game_name}] ✗ Upload timeout")
            return False
        except requests.exceptions.ConnectionError:
            print(f"[{self.game_name}] ✗ Connection error - is receiver running?")
            return False
        except Exception as e:
            print(f"[{self.game_name}] ✗ Error: {e}")
            return False

    def process_unsent(self):
        unsent = self.tracker.get_unsent()
        
        if not unsent:
            print(f"[{self.game_name}] No unsent backups")
            return
        
        print(f"[{self.game_name}] Found {len(unsent)} unsent backup(s)")
        
        for filename in unsent:
            if self.send_backup(filename):
                self.tracker.mark_sent(filename)
            else:
                print(f"[{self.game_name}] Failed to send {filename}, will retry next run")
    

    def run(self):
        print(f"\n[{self.game_name}] === Backup Run Started at {datetime.now().isoformat()} ===")
        self.reconcile_directory()
        self.process_unsent()
        print(f"[{self.game_name}] === Run Complete ===\n")


def load_config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description='Backup Sender - Cron-based backup uploader')
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
    
    # Run sender
    sender = BackupSender(config)
    sender.run()


if __name__ == '__main__':
    main()
