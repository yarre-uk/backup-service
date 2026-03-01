import os
import sys
import time
import yaml
import argparse
import tarfile
import zipfile
import schedule
from datetime import datetime
from pathlib import Path
import glob
import fnmatch


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
        
        # Include patterns (like .gitignore but for what TO include)
        self.include_file = config.get('include_file', None)
        self.include_patterns = []
        
        if self.include_file and os.path.exists(self.include_file):
            self._load_include_patterns()
        
        # Create output directory
        os.makedirs(self.output_path, exist_ok=True)
        
        print(f"[Archiver] Initialized")
        print(f"[Archiver] Container: {self.container_name}")
        print(f"[Archiver] Source: {self.source_path}")
        print(f"[Archiver] Output: {self.output_path}")
        print(f"[Archiver] Format: {self.archive_format}")
        print(f"[Archiver] Compression: {self.compression_level}")
        print(f"[Archiver] Interval: {self.interval_hours} hours")
        if self.include_patterns:
            print(f"[Archiver] Include patterns: {len(self.include_patterns)} rules loaded")
    
    def _load_include_patterns(self):
        print(f"[Archiver] Loading include patterns from: {self.include_file}")
        
        with open(self.include_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    self.include_patterns.append(line)
        
        print(f"[Archiver] Loaded {len(self.include_patterns)} include patterns")
    
    def _should_include(self, path):
        if not self.include_patterns:
            # No patterns = include everything
            return True
        
        # Get relative path from source
        try:
            rel_path = os.path.relpath(path, self.source_path)
        except ValueError:
            return False
        
        # Check against all patterns
        for pattern in self.include_patterns:
            # Directory pattern (ends with /)
            if pattern.endswith('/'):
                pattern_dir = pattern.rstrip('/')
                # Match if path is inside this directory
                if rel_path.startswith(pattern_dir + os.sep) or rel_path == pattern_dir:
                    return True
            else:
                # File pattern - use fnmatch for wildcards
                if fnmatch.fnmatch(rel_path, pattern):
                    return True
                # Also check if this is a parent directory of the pattern
                if pattern.startswith(rel_path + os.sep):
                    return True
        
        return False
    
    def _get_files_to_archive(self):
        if not self.include_patterns:
            # No patterns = include everything
            return [self.source_path]

        print(f"[Archiver] Scanning for files matching include patterns...")

        found = set()
        for pattern in self.include_patterns:
            if pattern.endswith('/'):
                # Directory pattern - include all files inside recursively
                full_pattern = os.path.join(self.source_path, pattern.rstrip('/'), '**')
                for f in glob.glob(full_pattern, recursive=True):
                    if os.path.isfile(f):
                        found.add(f)
            else:
                # File/glob pattern - supports *, **, ?
                for f in glob.glob(os.path.join(self.source_path, pattern), recursive=True):
                    if os.path.isfile(f):
                        found.add(f)

        files_to_archive = sorted(found)
        print(f"[Archiver] Found {len(files_to_archive)} files to archive")
        return files_to_archive
    
    def generate_filename(self):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = self.naming_pattern.format(
            container=self.container_name,
            timestamp=timestamp
        )
        return filename
    
    def create_tar_archive(self, output_file):
        compression_mode = 'w:gz' if self.archive_format == 'tar.gz' else 'w'
        
        print(f"[Archiver] Creating {self.archive_format} archive...")
        
        files_to_archive = self._get_files_to_archive()

        if not files_to_archive:
            print(f"[Archiver] ✗ No files match include patterns")
            return False
        
        with tarfile.open(output_file, compression_mode, compresslevel=self.compression_level) as tar:
            for file_path in files_to_archive:
                # Get relative path for archive
                arcname = os.path.relpath(file_path, self.source_path)
                tar.add(file_path, arcname=arcname)
        
        return True
    
    def create_zip_archive(self, output_file):
        print(f"[Archiver] Creating zip archive...")
        
        files_to_archive = self._get_files_to_archive()
        
        if not files_to_archive:
            print(f"[Archiver] ✗ No files match include patterns")
            return False
        
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=self.compression_level) as zipf:
            for file_path in files_to_archive:
                # Get relative path for archive
                arcname = os.path.relpath(file_path, self.source_path)
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
        
        # Create archive
        try:
            start_time = time.time()
            
            if self.archive_format in ['tar.gz', 'tar']:
                success = self.create_tar_archive(output_file)
            elif self.archive_format == 'zip':
                success = self.create_zip_archive(output_file)
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
