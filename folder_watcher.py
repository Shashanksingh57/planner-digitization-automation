#!/usr/bin/env python3
"""
Folder Watcher with 2-minute pause trigger
Monitors drop folder and triggers processing after file activity stops
"""

import os
import time
import threading
import logging
from pathlib import Path
from typing import List, Callable, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class PauseTriggeredHandler(FileSystemEventHandler):
    """File system event handler with pause-based triggering"""
    
    def __init__(self, callback: Callable[[List[str]], None], pause_seconds: int = 120):
        super().__init__()
        self.callback = callback
        self.pause_seconds = pause_seconds
        self.timer = None
        self.new_files: Set[str] = set()
        self.lock = threading.Lock()
        self.supported_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
        
    def _is_supported_file(self, file_path: str) -> bool:
        """Check if file has supported extension"""
        return Path(file_path).suffix.lower() in self.supported_extensions
    
    def _reset_timer(self):
        """Reset the pause timer"""
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.pause_seconds, self._trigger_callback)
            self.timer.start()
            logger.debug(f"Timer reset for {self.pause_seconds} seconds")
    
    def _trigger_callback(self):
        """Called when timer expires - triggers processing"""
        with self.lock:
            if self.new_files:
                files_to_process = list(self.new_files)
                self.new_files.clear()
                logger.info(f"Pause trigger activated. Processing {len(files_to_process)} files")
                
                try:
                    self.callback(files_to_process)
                except Exception as e:
                    logger.error(f"Error in callback execution: {e}")
            else:
                logger.debug("Timer expired but no new files to process")
    
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory and self._is_supported_file(event.src_path):
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            
            # Check if file is accessible (fully written)
            try:
                if os.path.getsize(event.src_path) > 0:
                    with self.lock:
                        self.new_files.add(event.src_path)
                        logger.info(f"New file detected: {Path(event.src_path).name}")
                        self._reset_timer()
            except (OSError, FileNotFoundError):
                logger.warning(f"File not accessible yet: {event.src_path}")
    
    def on_moved(self, event):
        """Handle file move events (e.g., from download completion)"""
        if not event.is_directory and self._is_supported_file(event.dest_path):
            with self.lock:
                self.new_files.add(event.dest_path)
                logger.info(f"File moved to watch folder: {Path(event.dest_path).name}")
                self._reset_timer()
    
    def stop(self):
        """Stop the timer and cleanup"""
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
                logger.info("Folder watcher timer stopped")

class FolderWatcher:
    """Main folder watching class with pause-based triggering"""
    
    def __init__(self, watch_folder: str, callback: Callable[[List[str]], None], 
                 pause_minutes: int = 2):
        self.watch_folder = Path(watch_folder)
        self.callback = callback
        self.pause_seconds = pause_minutes * 60
        self.observer = None
        self.handler = None
        
        # Validate watch folder
        if not self.watch_folder.exists():
            logger.error(f"Watch folder does not exist: {self.watch_folder}")
            raise FileNotFoundError(f"Watch folder not found: {self.watch_folder}")
        
        if not self.watch_folder.is_dir():
            logger.error(f"Watch path is not a directory: {self.watch_folder}")
            raise NotADirectoryError(f"Watch path is not a directory: {self.watch_folder}")
        
        logger.info(f"Folder watcher initialized for: {self.watch_folder}")
        logger.info(f"Pause trigger set to: {pause_minutes} minutes")
    
    def start(self):
        """Start watching the folder"""
        if self.observer:
            logger.warning("Folder watcher is already running")
            return
        
        try:
            self.handler = PauseTriggeredHandler(self.callback, self.pause_seconds)
            self.observer = Observer()
            self.observer.schedule(self.handler, str(self.watch_folder), recursive=True)
            self.observer.start()
            
            logger.info(f"Started watching folder: {self.watch_folder}")
            logger.info(f"Monitoring for files: {', '.join(self.handler.supported_extensions)}")
            
        except Exception as e:
            logger.error(f"Failed to start folder watcher: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop watching the folder"""
        if self.handler:
            self.handler.stop()
            self.handler = None
        
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            if self.observer.is_alive():
                logger.warning("Observer thread did not stop gracefully")
            self.observer = None
            
        logger.info("Folder watcher stopped")
    
    def is_running(self) -> bool:
        """Check if watcher is currently running"""
        return self.observer is not None and self.observer.is_alive()
    
    def get_existing_files(self) -> List[str]:
        """Get list of existing supported files in watch folder"""
        existing_files = []
        
        try:
            for file_path in self.watch_folder.rglob("*"):
                if file_path.is_file():
                    suffix = file_path.suffix.lower()
                    if suffix in {'.jpg', '.jpeg', '.png', '.pdf'}:
                        existing_files.append(str(file_path))
            
            logger.info(f"Found {len(existing_files)} existing files in watch folder")
            
        except Exception as e:
            logger.error(f"Error scanning existing files: {e}")
        
        return existing_files

def test_folder_watcher():
    """Test function for folder watcher"""
    def test_callback(files):
        print(f"TEST: Processing triggered for {len(files)} files:")
        for file in files:
            print(f"  - {Path(file).name}")
    
    # Test with a temporary directory
    test_dir = Path("/tmp/test_watch")
    test_dir.mkdir(exist_ok=True)
    
    watcher = FolderWatcher(str(test_dir), test_callback, pause_minutes=0.1)  # 6 seconds for testing
    
    try:
        watcher.start()
        print(f"Watching {test_dir} - add some files to test...")
        
        # Keep running for test
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping watcher...")
    finally:
        watcher.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_folder_watcher()