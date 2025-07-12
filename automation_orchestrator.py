#!/usr/bin/env python3
"""
Automation Orchestrator - Main coordinator script
Coordinates all automation components for planner digitization
"""

import os
import sys
import signal
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# Import our custom modules
from folder_watcher import FolderWatcher
from date_validator import DateValidator, ProcessingDecision
from digitizer_integration import DigitizerIntegration, ProcessingConfig, DigitizerResult
from notification_manager import NotificationManager, NotificationConfig, ProcessingResult

logger = logging.getLogger(__name__)

@dataclass
class AutomationConfig:
    """Complete automation configuration"""
    # Paths
    watch_folder: str
    digitizer_path: str
    
    # Processing
    pause_minutes: int = 2
    retry_attempts: int = 3
    batch_size: int = 5
    
    # Notion
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None
    
    # Scheduling
    reminder_day: int = 6  # Sunday
    reminder_hour: int = 20  # 8 PM
    reminder_minute: int = 0
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    enhanced_logging: bool = True

class AutomationOrchestrator:
    """Main orchestrator for planner digitization automation"""
    
    def __init__(self, config: AutomationConfig):
        self.config = config
        self.running = False
        self.scheduler = None
        self.folder_watcher = None
        self.date_validator = None
        self.digitizer = None
        self.notifier = None
        self.lock = threading.Lock()
        
        # Setup logging
        self._setup_logging()
        
        # Initialize components
        self._initialize_components()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Automation orchestrator initialized")
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler if specified
        if self.config.log_file:
            try:
                file_handler = logging.FileHandler(self.config.log_file)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                logger.info(f"Logging to file: {self.config.log_file}")
            except Exception as e:
                logger.error(f"Failed to setup file logging: {e}")
    
    def _initialize_components(self):
        """Initialize all automation components"""
        try:
            # Date validator
            if self.config.notion_token and self.config.notion_database_id:
                self.date_validator = DateValidator(
                    self.config.digitizer_path,
                    self.config.notion_token,
                    self.config.notion_database_id
                )
                logger.info("Date validator initialized")
            else:
                logger.warning("Date validator disabled - missing Notion configuration")
            
            # Digitizer integration
            digitizer_config = ProcessingConfig(
                digitizer_path=self.config.digitizer_path,
                retry_attempts=self.config.retry_attempts,
                batch_size=self.config.batch_size
            )
            self.digitizer = DigitizerIntegration(digitizer_config)
            logger.info("Digitizer integration initialized")
            
            # Notification manager
            notification_config = NotificationConfig(
                notion_token=self.config.notion_token,
                notion_database_id=self.config.notion_database_id,
                enable_notion_comments=False,  # Disabled by default
                enhanced_logging=self.config.enhanced_logging
            )
            self.notifier = NotificationManager(notification_config)
            logger.info("Notification manager initialized")
            
            # Folder watcher (initialized but not started)
            self.folder_watcher = FolderWatcher(
                self.config.watch_folder,
                self._handle_new_files,
                self.config.pause_minutes
            )
            logger.info("Folder watcher initialized")
            
            # Validate environment
            is_valid, issues = self.digitizer.validate_environment()
            if not is_valid:
                logger.warning("Environment validation issues detected:")
                for issue in issues:
                    logger.warning(f"  - {issue}")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def start(self):
        """Start the automation system"""
        if self.running:
            logger.warning("Automation already running")
            return
        
        logger.info("Starting planner digitization automation...")
        
        try:
            # Start scheduler for reminders
            self._start_scheduler()
            
            # Start folder watcher
            self.folder_watcher.start()
            
            # Process any existing files in watch folder
            self._process_existing_files()
            
            self.running = True
            logger.info("✅ Automation system started successfully")
            
            # Log startup status
            startup_stats = self._get_current_stats()
            logger.info("📢 Automation system started successfully")
            logger.info(f"📁 Watching: {self.config.watch_folder}")
            logger.info(f"🔧 Digitizer: {self.config.digitizer_path}")
            logger.info(f"⏱️  Pause trigger: {self.config.pause_minutes} minutes")
            logger.info(f"🔄 Retry attempts: {self.config.retry_attempts}")
            if startup_stats.get('total_processed'):
                logger.info(f"📊 Found {startup_stats['total_processed']} existing processed files")
            
        except Exception as e:
            logger.error(f"Failed to start automation: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop the automation system"""
        if not self.running:
            return
        
        logger.info("Stopping automation system...")
        
        try:
            # Stop folder watcher
            if self.folder_watcher:
                self.folder_watcher.stop()
            
            # Stop scheduler
            if self.scheduler:
                self.scheduler.shutdown(wait=False)
                self.scheduler = None
            
            self.running = False
            logger.info("✅ Automation system stopped")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def _start_scheduler(self):
        """Start the background scheduler for reminders"""
        try:
            self.scheduler = BackgroundScheduler()
            
            # Weekly reminder
            trigger = CronTrigger(
                day_of_week=self.config.reminder_day,
                hour=self.config.reminder_hour,
                minute=self.config.reminder_minute
            )
            
            self.scheduler.add_job(
                self._send_weekly_reminder,
                trigger=trigger,
                id='weekly_reminder',
                name='Weekly Planner Reminder'
            )
            
            self.scheduler.start()
            logger.info(f"Scheduler started - weekly reminders on day {self.config.reminder_day} at {self.config.reminder_hour}:{self.config.reminder_minute:02d}")
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def _handle_new_files(self, file_paths: List[str]):
        """Handle new files detected by folder watcher"""
        with self.lock:
            try:
                logger.info(f"Processing {len(file_paths)} new files")
                
                # Validate files with date extraction
                decisions = []
                if self.date_validator:
                    decisions = self.date_validator.validate_batch(file_paths)
                else:
                    # Create default decisions if no validator
                    decisions = [
                        ProcessingDecision(
                            action='new',
                            date=None,
                            reason='No date validation available'
                        ) for _ in file_paths
                    ]
                
                # Filter files to process
                files_to_process = []
                for file_path, decision in zip(file_paths, decisions):
                    if decision.action in ['new', 'update']:
                        files_to_process.append(file_path)
                    else:
                        logger.info(f"Skipping {Path(file_path).name}: {decision.reason}")
                
                if not files_to_process:
                    logger.info("No files to process after validation")
                    return
                
                # Process files
                results = self.digitizer.process_batch(files_to_process, upload_to_notion=True)
                
                # Create processing result summary
                processing_result = self._create_processing_result(results, decisions)
                
                # Send notification
                if self.notifier:
                    self.notifier.send_processing_notification(processing_result, file_paths)
                
                # Detect date gaps if validator is available
                if self.date_validator and any(d.date for d in decisions):
                    detected_dates = [d.date for d in decisions if d.date]
                    gaps = self.date_validator.detect_date_gaps(detected_dates)
                    
                    if gaps:
                        gap_data = [
                            {
                                'start_date': gap.start_date.strftime('%Y-%m-%d'),
                                'end_date': gap.end_date.strftime('%Y-%m-%d'),
                                'missing_dates': [d.strftime('%Y-%m-%d') for d in gap.missing_dates]
                            }
                            for gap in gaps
                        ]
                        
                        if self.notifier:
                            self.notifier.send_gap_detection_notification(gap_data, detected_dates)
                
                logger.info(f"Completed processing {len(file_paths)} files")
                
            except Exception as e:
                logger.error(f"Error handling new files: {e}")
                
                # Send error notification
                if self.notifier:
                    self.notifier.send_error_notification(
                        "File Processing Error",
                        str(e),
                        {"file_count": len(file_paths), "files": [Path(f).name for f in file_paths]}
                    )
    
    def _process_existing_files(self):
        """Process any existing files in the watch folder on startup"""
        try:
            existing_files = self.folder_watcher.get_existing_files()
            
            if existing_files:
                logger.info(f"Found {len(existing_files)} existing files in watch folder")
                
                # Only process a subset to avoid overwhelming on startup
                max_startup_files = 10
                if len(existing_files) > max_startup_files:
                    logger.info(f"Limiting startup processing to {max_startup_files} most recent files")
                    existing_files = sorted(existing_files, 
                                          key=lambda f: Path(f).stat().st_mtime, 
                                          reverse=True)[:max_startup_files]
                
                # Process existing files
                self._handle_new_files(existing_files)
            else:
                logger.info("No existing files found in watch folder")
                
        except Exception as e:
            logger.error(f"Error processing existing files: {e}")
    
    def _create_processing_result(self, results: List[DigitizerResult], 
                                decisions: List[ProcessingDecision]) -> ProcessingResult:
        """Create processing result summary from digitizer results"""
        success_count = sum(1 for r in results if r.success)
        error_count = len(results) - success_count
        
        # Count actions from decisions
        new_entries = sum(1 for d in decisions if d.action == 'new')
        updated_entries = sum(1 for d in decisions if d.action == 'update')
        skipped_count = sum(1 for d in decisions if d.action == 'skip')
        
        # Collect errors
        errors = [r.error_message for r in results if r.error_message]
        
        # Calculate total processing time
        total_time = sum(r.processing_time for r in results)
        
        return ProcessingResult(
            success_count=success_count,
            error_count=error_count,
            new_entries=new_entries,
            updated_entries=updated_entries,
            skipped_count=skipped_count,
            processing_time=total_time,
            errors=errors
        )
    
    def _send_weekly_reminder(self):
        """Send weekly reminder notification"""
        try:
            logger.info("Sending weekly reminder")
            
            stats = self._get_current_stats()
            
            if self.notifier:
                self.notifier.send_reminder_notification(stats)
            
        except Exception as e:
            logger.error(f"Error sending weekly reminder: {e}")
    
    def _get_current_stats(self) -> Dict:
        """Get current system statistics"""
        stats = {}
        
        try:
            # Get digitizer stats
            if self.digitizer:
                digitizer_stats = self.digitizer.get_processing_stats()
                stats.update(digitizer_stats)
            
            # Get notification stats
            if self.notifier:
                notion_stats = self.notifier.get_processing_stats()
                stats.update(notion_stats)
            
            # Add system stats
            stats.update({
                'automation_uptime': self._get_uptime(),
                'watch_folder': self.config.watch_folder,
                'last_check': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error getting current stats: {e}")
        
        return stats
    
    def _get_uptime(self) -> str:
        """Get automation uptime"""
        if not hasattr(self, '_start_time'):
            self._start_time = datetime.now()
        
        uptime = datetime.now() - self._start_time
        return str(uptime).split('.')[0]  # Remove microseconds
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def run_forever(self):
        """Run the automation system until stopped"""
        try:
            self.start()
            
            logger.info("🤖 Automation system running - watching for planner images...")
            logger.info(f"📁 Watch folder: {self.config.watch_folder}")
            logger.info("Press Ctrl+C to stop")
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            self.stop()

def load_config_from_env() -> AutomationConfig:
    """Load configuration from environment variables"""
    load_dotenv()
    
    return AutomationConfig(
        # Paths
        watch_folder=os.getenv('WATCH_FOLDER', ''),
        digitizer_path=os.getenv('DIGITIZER_PATH', ''),
        
        # Processing
        pause_minutes=int(os.getenv('PAUSE_MINUTES', '2')),
        retry_attempts=int(os.getenv('RETRY_ATTEMPTS', '3')),
        batch_size=int(os.getenv('BATCH_SIZE', '5')),
        
        # Notion
        notion_token=os.getenv('NOTION_TOKEN'),
        notion_database_id=os.getenv('NOTION_DATABASE_ID'),
        
        # Scheduling
        reminder_day=int(os.getenv('REMINDER_DAY', '6')),
        reminder_hour=int(os.getenv('REMINDER_HOUR', '20')),
        reminder_minute=int(os.getenv('REMINDER_MINUTE', '0')),
        
        # Logging
        log_level=os.getenv('LOG_LEVEL', 'INFO'),
        log_file=os.getenv('LOG_FILE'),
        enhanced_logging=os.getenv('ENHANCED_LOGGING', 'true').lower() == 'true'
    )

def main():
    """Main entry point"""
    try:
        # Load configuration
        config = load_config_from_env()
        
        # Validate required configuration
        if not config.watch_folder or not Path(config.watch_folder).exists():
            print(f"Error: Watch folder not found: {config.watch_folder}")
            print("Please set WATCH_FOLDER in your .env file")
            sys.exit(1)
        
        if not config.digitizer_path or not Path(config.digitizer_path).exists():
            print(f"Error: Digitizer path not found: {config.digitizer_path}")
            print("Please set DIGITIZER_PATH in your .env file")
            sys.exit(1)
        
        # Create and run orchestrator
        orchestrator = AutomationOrchestrator(config)
        orchestrator.run_forever()
        
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()