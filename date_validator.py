#!/usr/bin/env python3
"""
Date Validator - OCR date extraction and gap detection
Extracts dates from planner images and identifies missing sequences
"""

import os
import re
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ProcessingDecision:
    """Decision for how to handle an image file"""
    action: str  # 'new', 'update', 'skip'
    date: Optional[datetime]
    reason: str
    existing_id: Optional[str] = None

@dataclass
class DateGap:
    """Represents a gap in date sequence"""
    start_date: datetime
    end_date: datetime
    missing_dates: List[datetime]

class DateValidator:
    """Validates dates and detects gaps in planner sequences"""
    
    def __init__(self, digitizer_path: str, notion_token: str, database_id: str):
        self.digitizer_path = Path(digitizer_path)
        self.notion_token = notion_token
        self.database_id = database_id
        self.existing_dates: Dict[str, str] = {}  # date_str -> page_id
        self.date_pattern = re.compile(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})')
        
        # Validate digitizer path
        if not self.digitizer_path.exists():
            raise FileNotFoundError(f"Digitizer path not found: {self.digitizer_path}")
        
        # Initialize by loading existing dates from Notion
        self._load_existing_dates()
        
    def _load_existing_dates(self):
        """Load existing dates from Notion database"""
        try:
            # Use existing notion query setup
            query_script = self.digitizer_path / "notion_query.py"
            if not query_script.exists():
                logger.warning(f"Notion query script not found: {query_script}")
                return
            
            # Set up environment for the query
            env = os.environ.copy()
            env['NOTION_TOKEN'] = self.notion_token
            env['NOTION_DATABASE_ID'] = self.database_id
            
            # Run query to get existing dates
            result = subprocess.run(
                ['python', str(query_script)],
                cwd=str(self.digitizer_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self._parse_existing_dates()
                logger.info(f"Loaded {len(self.existing_dates)} existing dates from Notion")
            else:
                logger.error(f"Failed to query Notion: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error loading existing dates: {e}")
    
    def _parse_existing_dates(self):
        """Parse existing dates from Notion query results"""
        try:
            # Look for notion query output files
            summary_file = self.digitizer_path / "notion_pages_summary.json"
            if summary_file.exists():
                with open(summary_file, 'r') as f:
                    data = json.load(f)
                
                for entry in data.get('pages', []):
                    date_str = entry.get('date')
                    page_id = entry.get('id')
                    if date_str and page_id:
                        self.existing_dates[date_str] = page_id
                        
        except Exception as e:
            logger.error(f"Error parsing existing dates: {e}")
    
    def extract_date_from_image(self, image_path: str) -> Optional[datetime]:
        """Extract date from image using existing digitizer OCR"""
        try:
            # Use existing planner_digitizer.py for OCR
            digitizer_script = self.digitizer_path / "planner_digitizer.py"
            if not digitizer_script.exists():
                logger.error(f"Digitizer script not found: {digitizer_script}")
                return None
            
            # Set up environment
            env = os.environ.copy()
            env['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')
            
            # Run digitizer to extract content
            result = subprocess.run(
                ['python', str(digitizer_script), image_path, '--test'],
                cwd=str(self.digitizer_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Parse the output for date information
                return self._extract_date_from_output(result.stdout)
            else:
                logger.error(f"Digitizer failed for {image_path}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Digitizer timeout for {image_path}")
            return None
        except Exception as e:
            logger.error(f"Error extracting date from {image_path}: {e}")
            return None
    
    def _extract_date_from_output(self, output: str) -> Optional[datetime]:
        """Extract date from digitizer output"""
        try:
            # Look for date in JSON output or text
            if '"date":' in output:
                # Try to parse JSON output
                for line in output.split('\n'):
                    if '"date":' in line:
                        date_match = re.search(r'"date":\s*"([^"]+)"', line)
                        if date_match:
                            date_str = date_match.group(1)
                            return self._parse_date_string(date_str)
            
            # Look for date patterns in text output
            matches = self.date_pattern.findall(output)
            if matches:
                month_str, day_str, year_str = matches[0]
                return self._parse_date_components(month_str, day_str, year_str)
            
            # Alternative patterns
            for pattern in [
                r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "May 28, 2025"
                r'(\d{4})-(\d{2})-(\d{2})',        # "2025-05-28"
                r'(\d{1,2})/(\d{1,2})/(\d{4})'     # "5/28/2025"
            ]:
                matches = re.findall(pattern, output)
                if matches:
                    if pattern.startswith(r'(\d{4})'):  # ISO format
                        year, month, day = matches[0]
                        return datetime(int(year), int(month), int(day))
                    elif '/' in pattern:  # MM/DD/YYYY
                        month, day, year = matches[0]
                        return datetime(int(year), int(month), int(day))
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date from output: {e}")
            return None
    
    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various formats"""
        try:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%b %d, %Y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            # Try parsing components
            matches = self.date_pattern.findall(date_str)
            if matches:
                month_str, day_str, year_str = matches[0]
                return self._parse_date_components(month_str, day_str, year_str)
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date string '{date_str}': {e}")
            return None
    
    def _parse_date_components(self, month_str: str, day_str: str, year_str: str) -> Optional[datetime]:
        """Parse date from month name, day, year components"""
        try:
            # Convert month name to number
            month_names = {
                'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
                'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
                'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
                'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
            }
            
            month_num = month_names.get(month_str.lower())
            if month_num:
                day_num = int(day_str)
                year_num = int(year_str)
                return datetime(year_num, month_num, day_num)
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date components: {e}")
            return None
    
    def validate_batch(self, image_paths: List[str]) -> List[ProcessingDecision]:
        """Validate a batch of images and return processing decisions"""
        decisions = []
        
        for image_path in image_paths:
            try:
                # Extract date from image
                extracted_date = self.extract_date_from_image(image_path)
                
                if not extracted_date:
                    decision = ProcessingDecision(
                        action='skip',
                        date=None,
                        reason='Could not extract date from image'
                    )
                else:
                    # Check if date already exists in Notion
                    date_str = extracted_date.strftime('%Y-%m-%d')
                    existing_id = self.existing_dates.get(date_str)
                    
                    if existing_id:
                        decision = ProcessingDecision(
                            action='update',
                            date=extracted_date,
                            reason=f'Date {date_str} already exists in Notion',
                            existing_id=existing_id
                        )
                    else:
                        decision = ProcessingDecision(
                            action='new',
                            date=extracted_date,
                            reason=f'New date {date_str} to be processed'
                        )
                
                decisions.append(decision)
                logger.info(f"{Path(image_path).name}: {decision.action} - {decision.reason}")
                
            except Exception as e:
                logger.error(f"Error validating {image_path}: {e}")
                decisions.append(ProcessingDecision(
                    action='skip',
                    date=None,
                    reason=f'Validation error: {e}'
                ))
        
        return decisions
    
    def detect_date_gaps(self, processed_dates: List[datetime], 
                        look_back_days: int = 30) -> List[DateGap]:
        """Detect gaps in date sequences"""
        gaps = []
        
        try:
            if not processed_dates:
                return gaps
            
            # Sort dates
            sorted_dates = sorted(processed_dates)
            
            # Add existing dates for context
            all_dates = set(sorted_dates)
            for date_str in self.existing_dates.keys():
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    all_dates.add(date_obj)
                except ValueError:
                    continue
            
            all_dates_sorted = sorted(all_dates)
            
            # Look for gaps
            for i in range(len(all_dates_sorted) - 1):
                current_date = all_dates_sorted[i]
                next_date = all_dates_sorted[i + 1]
                
                # Check for gaps > 1 day
                diff = (next_date - current_date).days
                if diff > 1:
                    missing_dates = []
                    for day_offset in range(1, diff):
                        missing_date = current_date + timedelta(days=day_offset)
                        missing_dates.append(missing_date)
                    
                    gap = DateGap(
                        start_date=current_date,
                        end_date=next_date,
                        missing_dates=missing_dates
                    )
                    gaps.append(gap)
            
            logger.info(f"Detected {len(gaps)} date gaps")
            for gap in gaps:
                missing_str = [d.strftime('%Y-%m-%d') for d in gap.missing_dates]
                logger.info(f"Gap: {gap.start_date.strftime('%Y-%m-%d')} to {gap.end_date.strftime('%Y-%m-%d')} - Missing: {missing_str}")
            
        except Exception as e:
            logger.error(f"Error detecting date gaps: {e}")
        
        return gaps
    
    def refresh_existing_dates(self):
        """Refresh the cache of existing dates from Notion"""
        try:
            self._load_existing_dates()
            logger.info("Refreshed existing dates cache")
        except Exception as e:
            logger.error(f"Error refreshing existing dates: {e}")

def test_date_validator():
    """Test function for date validator"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test configuration
    digitizer_path = "/Users/shashanksingh/Desktop/AI Projects/Planner Digitizer"
    notion_token = os.getenv('NOTION_TOKEN', '')
    database_id = os.getenv('NOTION_DATABASE_ID', '')
    
    if not notion_token or not database_id:
        print("Please set NOTION_TOKEN and NOTION_DATABASE_ID in environment")
        return
    
    try:
        validator = DateValidator(digitizer_path, notion_token, database_id)
        print(f"Loaded {len(validator.existing_dates)} existing dates")
        
        # Test date gap detection
        test_dates = [
            datetime(2025, 5, 25),
            datetime(2025, 5, 26),
            datetime(2025, 5, 30),  # Gap: 27, 28, 29 missing
            datetime(2025, 5, 31)
        ]
        
        gaps = validator.detect_date_gaps(test_dates)
        print(f"Found {len(gaps)} gaps in test dates")
        
    except Exception as e:
        print(f"Test error: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_date_validator()