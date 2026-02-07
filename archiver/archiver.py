import os
import sys
import time
import yaml
import argparse
import tarfile
import zipfile
import docker
import schedule
from datetime import datetime
from pathlib import Path


class Archiver:
    def __init__(self, config):
        self.config = config
        self.container_name = config['container_name']
        self.interval_hours = config['interval_hours']
        self.source_path = config['source_path']
        self.output_path = config['output_path']
        self.compression_level = config.get('compression_level', 6)
        self.archive_format = config.get('archive_format', 'tar.gz')
        self.naming_pattern = config.get('naming_pattern', '{container}-{timestamp}.tar.gz')
        
        # Pre-archive command settings
        self.pre_archive_command = config.get('pre_archive_command')
        self.command_timeout = config.get('command_timeout', 30)
        
        # Docker client
        try:
            self.docker_client = docker.from_env()
            print(f"[Archiver] Docker client initialized")
        except Exception as e:
            print(f"[Archiver] Failed to initialize Docker client: {e}")
            print(f"[Archiver] Pre-archive commands will be skipped")
            self.docker_client = None
        
        # Create output directory
        os.makedirs(self.output_path, exist_ok=True)
        
        print(f"[Archiver] Initialized")
        print(f"[Archiver] Container: {self.container_name}")
        print(f"[Archiver] Source: {self.source_path}")
        print(f"[Archiver] Output: {self.output_path}")
        print(f"[Archiver] Format: {self.archive_format}")
        print(f"[Archiver] Compression: {self.compression_level}")
        print(f"[Archiver] Interval: {self.interval_hours} hours")
        if self.pre_archive_command:
            print(f"[Archiver] Pre-command: {self.pre_archive_command}")
    
    def run_pre_archive_command(self):
        if not self.pre_archive_command:
            return True
        
        if not self.docker_client:
            print(f"[Archiver] Skipping pre-archive command (no Docker client)")
            return True
        
        try:
            print(f"[Archiver] Running pre-archive command in {self.container_name}...")
            container = self.docker_client.containers.get(self.container_name)
            
            result = container.exec_run(
                self.pre_archive_command,
                timeout=self.command_timeout
            )
            
            if result.exit_code == 0:
                print(f"[Archiver] ✓ Pre-archive command completed successfully")
                if result.output:
                    output = result.output.decode('utf-8').strip()
                    if output:
                        print(f"[Archiver] Command output: {output}")
                return True
            else:
                print(f"[Archiver] ✗ Pre-archive command failed with exit code {result.exit_code}")
                if result.output:
                    print(f"[Archiver] Error: {result.output.decode('utf-8')}")
                return False
                
        except docker.errors.NotFound:
            print(f"[Archiver] ✗ Container '{self.container_name}' not found")
            return False
        except docker.errors.APIError as e:
            print(f"[Archiver] ✗ Docker API error: {e}")
            return False
        except Exception as e:
            print(f"[Archiver] ✗ Error executing pre-archive command: {e}")
            return False
    
    def generate_filename(self):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = self.naming_pattern.format(
            container=self.container_name,
            timestamp=timestamp
        )
        return filename
    
    def create_tar_archive(self, source, output_file):
        compression_mode = 'w:gz' if self.archive_format == 'tar.gz' else 'w'
        
        print(f"[Archiver] Creating {self.archive_format} archive...")
        
        with tarfile.open(output_file, compression_mode, compresslevel=self.compression_level) as tar:
            tar.add(source, arcname=os.path.basename(source))
        
        return True
    
    def create_zip_archive(self, source, output_file):
        print(f"[Archiver] Creating zip archive...")
        
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=self.compression_level) as zipf:
            source_path = Path(source)
            
            if source_path.is_file():
                zipf.write(source, arcname=source_path.name)
            else:
                for file_path in source_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(source_path.parent)
                        zipf.write(file_path, arcname=arcname)
        
        return True
    
    def create_archive(self):
        if not os.path.exists(self.source_path):
            print(f"[Archiver] ✗ Source path does not exist: {self.source_path}")
            return False
        
        # Generate filename
        filename = self.generate_filename()
        output_file = os.path.join(self.output_path, filename)
        
        print(f"\n[Archiver] === Archive Creation Started at {datetime.now().isoformat()} ===")
        print(f"[Archiver] Output: {filename}")
        
        # Run pre-archive command
        if not self.run_pre_archive_command():
            print(f"[Archiver] ✗ Pre-archive command failed, skipping archive creation")
            return False
        
        # Wait a bit for command effects to settle
        if self.pre_archive_command:
            print(f"[Archiver] Waiting 60 seconds for state to stabilize...")
            time.sleep(60)
        
        # Create archive
        try:
            start_time = time.time()
            
            if self.archive_format in ['tar.gz', 'tar']:
                success = self.create_tar_archive(self.source_path, output_file)
            elif self.archive_format == 'zip':
                success = self.create_zip_archive(self.source_path, output_file)
            else:
                print(f"[Archiver] ✗ Unknown archive format: {self.archive_format}")
                return False
            
            if success:
                elapsed = time.time() - start_time
                file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                print(f"[Archiver] ✓ Archive created: {file_size_mb:.2f} MB in {elapsed:.1f}s")
                print(f"[Archiver] === Archive Creation Complete ===\n")
                return True
            else:
                print(f"[Archiver] ✗ Archive creation failed")
                return False
                
        except Exception as e:
            print(f"[Archiver] ✗ Error creating archive: {e}")
            return False
    
    def run(self):
        self.create_archive()


def load_config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description='Archiver - Automated backup archiving service')
    parser.add_argument('--config', '-c', required=True, help='Path to config file')
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Validate config
    required_fields = ['container_name', 'interval_hours', 'source_path', 'output_path']
    for field in required_fields:
        if field not in config:
            print(f"Error: Missing required field '{field}' in config")
            sys.exit(1)
    
    # Initialize archiver
    archiver = Archiver(config)
    
    # Run immediately on start
    archiver.run()
    
    # Schedule recurring runs
    schedule.every(archiver.interval_hours).hours.do(archiver.run)
    
    print(f"\n[Archiver] Scheduler started, running every {archiver.interval_hours} hours")
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == '__main__':
    main()
