#!/usr/bin/env python3
"""
Notification Manager - Slack and Notion notifications
Handles all notification logic for the planner digitization automation
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
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
    slack_webhook_url: Optional[str] = None
    slack_channel: str = "personal-automation"
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None
    enable_slack: bool = True
    enable_notion_comments: bool = True

class NotificationManager:
    """Manages notifications for planner digitization automation"""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.slack_client = None
        self.notion_client = None
        
        # Initialize Slack client
        if config.enable_slack and config.slack_webhook_url:
            self.slack_webhook_url = config.slack_webhook_url
            logger.info("Slack notifications enabled")
        else:
            logger.warning("Slack notifications disabled - no webhook URL")
        
        # Initialize Notion client
        if config.enable_notion_comments and config.notion_token:
            try:
                self.notion_client = Client(auth=config.notion_token)
                logger.info("Notion client initialized for comments")
            except Exception as e:
                logger.error(f"Failed to initialize Notion client: {e}")
        else:
            logger.warning("Notion comments disabled")
    
    def send_processing_notification(self, result: ProcessingResult, 
                                   batch_files: List[str]) -> bool:
        """Send notification about processing results"""
        try:
            # Generate summary message
            total_files = len(batch_files)
            success_rate = (result.success_count / total_files * 100) if total_files > 0 else 0
            
            # Create message
            message = self._format_processing_message(result, batch_files, success_rate)
            
            # Send to Slack
            slack_sent = False
            if self.config.enable_slack:
                slack_sent = self._send_slack_message(message)
            
            # Add Notion comments for errors if any
            notion_updated = False
            if self.config.enable_notion_comments and result.errors:
                notion_updated = self._add_notion_error_comments(result.errors)
            
            logger.info(f"Notifications sent - Slack: {slack_sent}, Notion: {notion_updated}")
            return slack_sent or notion_updated
            
        except Exception as e:
            logger.error(f"Error sending processing notification: {e}")
            return False
    
    def send_gap_detection_notification(self, gaps: List[Dict], 
                                      detected_dates: List[datetime]) -> bool:
        """Send notification about detected date gaps"""
        try:
            if not gaps:
                return True  # No gaps is good news, no notification needed
            
            message = self._format_gap_message(gaps, detected_dates)
            
            if self.config.enable_slack:
                return self._send_slack_message(message)
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending gap notification: {e}")
            return False
    
    def send_reminder_notification(self, stats: Dict) -> bool:
        """Send weekly reminder notification with stats"""
        try:
            message = self._format_reminder_message(stats)
            
            if self.config.enable_slack:
                return self._send_slack_message(message)
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")
            return False
    
    def send_error_notification(self, error_type: str, error_message: str, 
                              context: Optional[Dict] = None) -> bool:
        """Send notification about critical errors"""
        try:
            message = self._format_error_message(error_type, error_message, context)
            
            if self.config.enable_slack:
                return self._send_slack_message(message, urgent=True)
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")
            return False
    
    def _format_processing_message(self, result: ProcessingResult, 
                                 batch_files: List[str], success_rate: float) -> str:
        """Format processing result message"""
        total_files = len(batch_files)
        
        # Status emoji based on success rate
        if success_rate >= 90:
            status_emoji = "✅"
        elif success_rate >= 70:
            status_emoji = "⚠️"
        else:
            status_emoji = "❌"
        
        message = f"{status_emoji} **Planner Processing Complete**\n\n"
        message += f"📊 **Summary:**\n"
        message += f"• Total files: {total_files}\n"
        message += f"• Success: {result.success_count} ({success_rate:.1f}%)\n"
        message += f"• Errors: {result.error_count}\n"
        message += f"• New entries: {result.new_entries}\n"
        message += f"• Updated entries: {result.updated_entries}\n"
        message += f"• Skipped: {result.skipped_count}\n"
        message += f"• Processing time: {result.processing_time:.1f}s\n\n"
        
        if result.errors:
            message += f"🚨 **Errors:**\n"
            for error in result.errors[:3]:  # Show max 3 errors
                message += f"• {error}\n"
            if len(result.errors) > 3:
                message += f"• ... and {len(result.errors) - 3} more errors\n"
            message += "\n"
        
        message += f"📅 **Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    def _format_gap_message(self, gaps: List[Dict], detected_dates: List[datetime]) -> str:
        """Format date gap detection message"""
        total_gaps = len(gaps)
        total_missing = sum(len(gap.get('missing_dates', [])) for gap in gaps)
        
        message = f"📅 **Date Gap Detection Results**\n\n"
        message += f"• Found {total_gaps} gaps\n"
        message += f"• Total missing days: {total_missing}\n"
        message += f"• Analyzed {len(detected_dates)} dates\n\n"
        
        if gaps:
            message += f"🔍 **Detected Gaps:**\n"
            for i, gap in enumerate(gaps[:5], 1):  # Show max 5 gaps
                start = gap.get('start_date', 'Unknown')
                end = gap.get('end_date', 'Unknown')
                missing_count = len(gap.get('missing_dates', []))
                message += f"{i}. {start} → {end} ({missing_count} days)\n"
            
            if len(gaps) > 5:
                message += f"• ... and {len(gaps) - 5} more gaps\n"
        
        return message
    
    def _format_reminder_message(self, stats: Dict) -> str:
        """Format weekly reminder message"""
        message = f"📱 **Weekly Planner Reminder**\n\n"
        message += f"📊 **Current Stats:**\n"
        
        if 'total_entries' in stats:
            message += f"• Total entries: {stats['total_entries']}\n"
        if 'last_processed' in stats:
            message += f"• Last processed: {stats['last_processed']}\n"
        if 'pending_count' in stats:
            message += f"• Pending files: {stats['pending_count']}\n"
        if 'completion_rate' in stats:
            message += f"• Completion rate: {stats['completion_rate']:.1f}%\n"
        
        message += f"\n💡 **Reminder:** Don't forget to scan your daily planner pages!"
        message += f"\n📸 Drop new images in your watch folder for automatic processing."
        
        return message
    
    def _format_error_message(self, error_type: str, error_message: str, 
                            context: Optional[Dict] = None) -> str:
        """Format error notification message"""
        message = f"🚨 **Planner Automation Error**\n\n"
        message += f"**Type:** {error_type}\n"
        message += f"**Message:** {error_message}\n"
        message += f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if context:
            message += f"\n**Context:**\n"
            for key, value in context.items():
                message += f"• {key}: {value}\n"
        
        message += f"\n⚠️ **Action Required:** Please check the automation logs."
        
        return message
    
    def _send_slack_message(self, message: str, urgent: bool = False) -> bool:
        """Send message to Slack via webhook"""
        try:
            if not self.slack_webhook_url:
                logger.warning("No Slack webhook URL configured")
                return False
            
            # Format message for Slack
            slack_message = {
                "channel": self.config.slack_channel,
                "text": message,
                "username": "Planner Automation",
                "icon_emoji": ":robot_face:" if not urgent else ":warning:"
            }
            
            # Send to webhook
            response = requests.post(
                self.slack_webhook_url,
                json=slack_message,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Slack message sent successfully")
                return True
            else:
                logger.error(f"Slack webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return False
    
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
    
    # Test configuration
    config = NotificationConfig(
        slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
        slack_channel="test-automation",
        notion_token=os.getenv('NOTION_TOKEN'),
        notion_database_id=os.getenv('NOTION_DATABASE_ID'),
        enable_slack=True,
        enable_notion_comments=False  # Disable for testing
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
    print(f"Processing notification sent: {success}")
    
    # Test error notification
    success = manager.send_error_notification(
        "Folder Watch Error",
        "Failed to access watch folder",
        {"folder": "/path/to/watch", "error_code": "EACCES"}
    )
    print(f"Error notification sent: {success}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_notification_manager()