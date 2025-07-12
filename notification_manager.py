#!/usr/bin/env python3
"""
Notification Manager - Enhanced logging and optional Notion notifications
Handles all notification logic for the planner digitization automation
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import requests
from notion_client import Client

logger = logging.getLogger(__name__)

@dataclass
class ProcessingResult:
    """Result of processing batch"""
    success_count: int
    error_count: int
    new_entries: int
    updated_entries: int
    skipped_count: int
    processing_time: float
    errors: List[str]

@dataclass
class NotificationConfig:
    """Configuration for notifications"""
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None
    enable_notion_comments: bool = False  # Disabled by default
    enhanced_logging: bool = True

class NotificationManager:
    """Manages enhanced logging and optional Notion notifications for planner digitization automation"""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.notion_client = None
        
        # Setup enhanced logging
        if config.enhanced_logging:
            self._setup_enhanced_logging()
            logger.info("Enhanced logging enabled for notifications")
        
        # Initialize Notion client (optional)
        if config.enable_notion_comments and config.notion_token:
            try:
                self.notion_client = Client(auth=config.notion_token)
                logger.info("Notion client initialized for comments")
            except Exception as e:
                logger.error(f"Failed to initialize Notion client: {e}")
        else:
            logger.info("Notion comments disabled")
    
    def _setup_enhanced_logging(self):
        """Setup enhanced logging for detailed notification output"""
        # Create a notification-specific logger
        self.notification_logger = logging.getLogger('automation.notifications')
        
        # Add console handler with special formatting for notifications
        if not any(isinstance(h, logging.StreamHandler) for h in self.notification_logger.handlers):
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '\n%(asctime)s - 📢 NOTIFICATION - %(levelname)s\n%(message)s\n' + '='*80
            )
            console_handler.setFormatter(formatter)
            self.notification_logger.addHandler(console_handler)
            self.notification_logger.setLevel(logging.INFO)
    
    def send_processing_notification(self, result: ProcessingResult, 
                                   batch_files: List[str]) -> bool:
        """Send enhanced logging notification about processing results"""
        try:
            # Generate summary message
            total_files = len(batch_files)
            success_rate = (result.success_count / total_files * 100) if total_files > 0 else 0
            
            # Create detailed log message
            message = self._format_processing_message(result, batch_files, success_rate)
            
            # Log with enhanced formatting
            if self.config.enhanced_logging:
                self.notification_logger.info(message)
            else:
                logger.info(f"Processing complete - {result.success_count}/{total_files} successful")
            
            # Add Notion comments for errors if enabled
            notion_updated = False
            if self.config.enable_notion_comments and result.errors:
                notion_updated = self._add_notion_error_comments(result.errors)
            
            logger.debug(f"Notifications processed - Enhanced logging: {self.config.enhanced_logging}, Notion: {notion_updated}")
            return True  # Always successful since we're just logging
            
        except Exception as e:
            logger.error(f"Error sending processing notification: {e}")
            return False
    
    def send_gap_detection_notification(self, gaps: List[Dict], 
                                      detected_dates: List[datetime]) -> bool:
        """Send enhanced logging notification about detected date gaps"""
        try:
            if not gaps:
                logger.info("Date gap detection: No gaps found - all dates are continuous")
                return True
            
            message = self._format_gap_message(gaps, detected_dates)
            
            if self.config.enhanced_logging:
                self.notification_logger.warning(message)
            else:
                logger.warning(f"Date gaps detected: {len(gaps)} gaps found in sequence")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending gap notification: {e}")
            return False
    
    def send_reminder_notification(self, stats: Dict) -> bool:
        """Send weekly reminder as enhanced log message"""
        try:
            message = self._format_reminder_message(stats)
            
            if self.config.enhanced_logging:
                self.notification_logger.info(message)
            else:
                logger.info("Weekly reminder: Don't forget to scan your daily planner pages!")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")
            return False
    
    def send_error_notification(self, error_type: str, error_message: str, 
                              context: Optional[Dict] = None) -> bool:
        """Send critical error notification via enhanced logging"""
        try:
            message = self._format_error_message(error_type, error_message, context)
            
            if self.config.enhanced_logging:
                self.notification_logger.error(message)
            else:
                logger.error(f"Critical error - {error_type}: {error_message}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")
            return False
    
    def _format_processing_message(self, result: ProcessingResult, 
                                 batch_files: List[str], success_rate: float) -> str:
        """Format processing result message for enhanced logging"""
        total_files = len(batch_files)
        
        # Status indicator based on success rate
        if success_rate >= 90:
            status = "SUCCESS"
        elif success_rate >= 70:
            status = "PARTIAL SUCCESS"
        else:
            status = "FAILED"
        
        message = f"PLANNER PROCESSING {status}\n"
        message += f"{'='*50}\n"
        message += f"📊 PROCESSING SUMMARY:\n"
        message += f"   • Total files processed: {total_files}\n"
        message += f"   • Successful: {result.success_count} ({success_rate:.1f}%)\n"
        message += f"   • Failed: {result.error_count}\n"
        message += f"   • New entries created: {result.new_entries}\n"
        message += f"   • Existing entries updated: {result.updated_entries}\n"
        message += f"   • Files skipped: {result.skipped_count}\n"
        message += f"   • Total processing time: {result.processing_time:.1f} seconds\n"
        
        if batch_files:
            message += f"\n📁 PROCESSED FILES:\n"
            for i, file_path in enumerate(batch_files[:10], 1):  # Show max 10 files
                from pathlib import Path
                filename = Path(file_path).name
                message += f"   {i}. {filename}\n"
            if len(batch_files) > 10:
                message += f"   ... and {len(batch_files) - 10} more files\n"
        
        if result.errors:
            message += f"\n🚨 ERRORS ENCOUNTERED:\n"
            for i, error in enumerate(result.errors[:5], 1):  # Show max 5 errors
                message += f"   {i}. {error}\n"
            if len(result.errors) > 5:
                message += f"   ... and {len(result.errors) - 5} more errors\n"
        
        message += f"\n⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    def _format_gap_message(self, gaps: List[Dict], detected_dates: List[datetime]) -> str:
        """Format date gap detection message for enhanced logging"""
        total_gaps = len(gaps)
        total_missing = sum(len(gap.get('missing_dates', [])) for gap in gaps)
        
        message = f"DATE GAP DETECTION RESULTS\n"
        message += f"{'='*50}\n"
        message += f"🔍 ANALYSIS SUMMARY:\n"
        message += f"   • Gaps found: {total_gaps}\n"
        message += f"   • Total missing days: {total_missing}\n"
        message += f"   • Dates analyzed: {len(detected_dates)}\n"
        
        if gaps:
            message += f"\n📅 DETECTED GAPS:\n"
            for i, gap in enumerate(gaps[:10], 1):  # Show max 10 gaps
                start = gap.get('start_date', 'Unknown')
                end = gap.get('end_date', 'Unknown')
                missing_dates = gap.get('missing_dates', [])
                missing_count = len(missing_dates)
                
                message += f"   {i}. Gap: {start} → {end} ({missing_count} missing days)\n"
                
                # Show missing dates for smaller gaps
                if missing_count <= 5 and missing_dates:
                    missing_str = ", ".join(missing_dates[:5])
                    message += f"      Missing: {missing_str}\n"
                elif missing_count > 5:
                    missing_str = ", ".join(missing_dates[:3])
                    message += f"      Missing: {missing_str}... and {missing_count - 3} more\n"
            
            if len(gaps) > 10:
                message += f"   ... and {len(gaps) - 10} more gaps\n"
            
            message += f"\n⚠️  ACTION REQUIRED: Please scan missing planner pages to maintain complete records"
        
        return message
    
    def _format_reminder_message(self, stats: Dict) -> str:
        """Format weekly reminder message for enhanced logging"""
        message = f"WEEKLY PLANNER REMINDER\n"
        message += f"{'='*50}\n"
        message += f"📊 AUTOMATION STATUS:\n"
        
        if 'total_entries' in stats:
            message += f"   • Total entries processed: {stats['total_entries']}\n"
        if 'last_processed' in stats:
            message += f"   • Last processing date: {stats['last_processed']}\n"
        if 'pending_count' in stats:
            message += f"   • Pending files in queue: {stats['pending_count']}\n"
        if 'completion_rate' in stats:
            message += f"   • Overall success rate: {stats['completion_rate']:.1f}%\n"
        if 'automation_uptime' in stats:
            message += f"   • System uptime: {stats['automation_uptime']}\n"
        
        message += f"\n💡 MAINTENANCE REMINDER:\n"
        message += f"   • Scan daily planner pages regularly\n"
        message += f"   • Drop new images in watch folder for automatic processing\n"
        message += f"   • Check automation logs for any issues\n"
        message += f"   • Review processed entries in Notion database\n"
        
        message += f"\n📁 Watch folder: {stats.get('watch_folder', 'Not configured')}"
        
        return message
    
    def _format_error_message(self, error_type: str, error_message: str, 
                            context: Optional[Dict] = None) -> str:
        """Format error notification message for enhanced logging"""
        message = f"CRITICAL AUTOMATION ERROR\n"
        message += f"{'='*50}\n"
        message += f"🚨 ERROR DETAILS:\n"
        message += f"   • Type: {error_type}\n"
        message += f"   • Message: {error_message}\n"
        message += f"   • Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if context:
            message += f"\n📋 CONTEXT INFORMATION:\n"
            for key, value in context.items():
                message += f"   • {key}: {value}\n"
        
        message += f"\n🔧 RECOMMENDED ACTIONS:\n"
        message += f"   • Check automation logs for detailed error traces\n"
        message += f"   • Verify system configuration and dependencies\n"
        message += f"   • Test individual components if error persists\n"
        message += f"   • Review environment variables and API keys\n"
        
        return message
    
    
    def _add_notion_error_comments(self, errors: List[str]) -> bool:
        """Add error comments to Notion pages"""
        try:
            if not self.notion_client or not self.config.notion_database_id:
                return False
            
            # Query recent pages to add comments
            response = self.notion_client.databases.query(
                database_id=self.config.notion_database_id,
                sorts=[{"timestamp": "created_time", "direction": "descending"}],
                page_size=10
            )
            
            comment_added = False
            for page in response.get('results', [])[:3]:  # Comment on last 3 pages
                page_id = page['id']
                
                # Create comment text
                comment_text = f"⚠️ Processing errors detected:\n"
                for i, error in enumerate(errors[:3], 1):
                    comment_text += f"{i}. {error}\n"
                
                # Add comment
                try:
                    self.notion_client.comments.create(
                        parent={"page_id": page_id},
                        rich_text=[{
                            "type": "text",
                            "text": {"content": comment_text}
                        }]
                    )
                    comment_added = True
                    logger.info(f"Added error comment to Notion page: {page_id}")
                except Exception as e:
                    logger.error(f"Failed to add comment to page {page_id}: {e}")
            
            return comment_added
            
        except Exception as e:
            logger.error(f"Error adding Notion comments: {e}")
            return False
    
    def get_processing_stats(self) -> Dict:
        """Get current processing statistics from Notion"""
        try:
            if not self.notion_client or not self.config.notion_database_id:
                return {}
            
            # Query database for stats
            response = self.notion_client.databases.query(
                database_id=self.config.notion_database_id,
                sorts=[{"timestamp": "created_time", "direction": "descending"}],
                page_size=100
            )
            
            pages = response.get('results', [])
            
            stats = {
                'total_entries': len(pages),
                'last_processed': None,
                'completion_rate': 0
            }
            
            if pages:
                # Get last processed date
                last_page = pages[0]
                created_time = last_page.get('created_time')
                if created_time:
                    stats['last_processed'] = created_time.split('T')[0]
                
                # Calculate completion rate (placeholder)
                # This would need to check actual completion status from properties
                completed = sum(1 for page in pages if self._is_page_completed(page))
                if len(pages) > 0:
                    stats['completion_rate'] = (completed / len(pages)) * 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting processing stats: {e}")
            return {}
    
    def _is_page_completed(self, page: Dict) -> bool:
        """Check if a Notion page is marked as completed"""
        try:
            # This would check the completion status property
            # Implementation depends on your database schema
            properties = page.get('properties', {})
            
            # Example: Check if there's a completion checkbox
            completion_prop = properties.get('Completed', {})
            if completion_prop.get('type') == 'checkbox':
                return completion_prop.get('checkbox', False)
            
            return False
            
        except Exception:
            return False

def test_notification_manager():
    """Test function for notification manager"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test configuration - enhanced logging only
    config = NotificationConfig(
        notion_token=os.getenv('NOTION_TOKEN'),
        notion_database_id=os.getenv('NOTION_DATABASE_ID'),
        enable_notion_comments=False,  # Disable for testing
        enhanced_logging=True
    )
    
    # Test notification manager
    manager = NotificationManager(config)
    
    # Test processing notification
    test_result = ProcessingResult(
        success_count=8,
        error_count=2,
        new_entries=5,
        updated_entries=3,
        skipped_count=2,
        processing_time=45.7,
        errors=["OCR failed on image_001.jpg", "Date extraction failed on image_005.jpg"]
    )
    
    test_files = ["image_001.jpg", "image_002.jpg", "image_003.jpg"]
    
    success = manager.send_processing_notification(test_result, test_files)
    print(f"Processing notification logged: {success}")
    
    # Test gap detection notification
    test_gaps = [
        {
            'start_date': '2025-01-15',
            'end_date': '2025-01-18',
            'missing_dates': ['2025-01-16', '2025-01-17']
        }
    ]
    
    success = manager.send_gap_detection_notification(test_gaps, [])
    print(f"Gap detection notification logged: {success}")
    
    # Test error notification
    success = manager.send_error_notification(
        "Folder Watch Error",
        "Failed to access watch folder",
        {"folder": "/path/to/watch", "error_code": "EACCES"}
    )
    print(f"Error notification logged: {success}")
    
    # Test reminder notification
    test_stats = {
        'total_entries': 189,
        'last_processed': '2025-01-15',
        'automation_uptime': '2 days, 3:45:22'
    }
    
    success = manager.send_reminder_notification(test_stats)
    print(f"Reminder notification logged: {success}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_notification_manager()