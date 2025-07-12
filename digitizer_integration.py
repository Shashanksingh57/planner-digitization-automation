#!/usr/bin/env python3
"""
Digitizer Integration - CLI integration with retry logic
Handles interaction with the existing planner digitizer system
"""

import os
import json
import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ProcessingConfig:
    """Configuration for digitizer processing"""
    digitizer_path: str
    retry_attempts: int = 3
    retry_delay: int = 5  # seconds
    timeout: int = 120  # seconds per image
    batch_size: int = 5
    parser_type: str = "simple"

@dataclass
class DigitizerResult:
    """Result from digitizer processing"""
    success: bool
    image_path: str
    output_data: Optional[Dict] = None
    error_message: Optional[str] = None
    processing_time: float = 0.0
    retry_count: int = 0

class DigitizerIntegration:
    """Integrates with existing planner digitizer CLI"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.digitizer_path = Path(config.digitizer_path)
        
        # Validate digitizer path
        if not self.digitizer_path.exists():
            raise FileNotFoundError(f"Digitizer path not found: {self.digitizer_path}")
        
        # Find the main digitizer script
        self.digitizer_script = self.digitizer_path / "planner_digitizer.py"
        if not self.digitizer_script.exists():
            raise FileNotFoundError(f"Digitizer script not found: {self.digitizer_script}")
        
        # Check for notion uploader
        self.notion_uploader = self.digitizer_path / "notion_uploader.py"
        self.has_notion_uploader = self.notion_uploader.exists()
        
        logger.info(f"Digitizer integration initialized: {self.digitizer_path}")
        logger.info(f"Notion uploader available: {self.has_notion_uploader}")
    
    def process_single_image(self, image_path: str, 
                           upload_to_notion: bool = True) -> DigitizerResult:
        """Process a single image with retry logic"""
        start_time = time.time()
        image_path = str(Path(image_path).resolve())
        
        for attempt in range(self.config.retry_attempts):
            try:
                logger.info(f"Processing {Path(image_path).name} (attempt {attempt + 1})")
                
                # Run digitizer
                result = self._run_digitizer(image_path, upload_to_notion)
                
                if result.success:
                    result.processing_time = time.time() - start_time
                    result.retry_count = attempt
                    logger.info(f"Successfully processed {Path(image_path).name}")
                    return result
                else:
                    logger.warning(f"Attempt {attempt + 1} failed for {Path(image_path).name}: {result.error_message}")
                    
                    # Wait before retry (except on last attempt)
                    if attempt < self.config.retry_attempts - 1:
                        time.sleep(self.config.retry_delay)
                        
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} exception for {Path(image_path).name}: {e}")
                
                if attempt < self.config.retry_attempts - 1:
                    time.sleep(self.config.retry_delay)
        
        # All attempts failed
        processing_time = time.time() - start_time
        return DigitizerResult(
            success=False,
            image_path=image_path,
            error_message=f"Failed after {self.config.retry_attempts} attempts",
            processing_time=processing_time,
            retry_count=self.config.retry_attempts
        )
    
    def process_batch(self, image_paths: List[str], 
                     upload_to_notion: bool = True) -> List[DigitizerResult]:
        """Process multiple images in batches"""
        results = []
        total_images = len(image_paths)
        
        logger.info(f"Processing batch of {total_images} images")
        
        # Process in smaller batches to avoid timeouts
        for i in range(0, total_images, self.config.batch_size):
            batch = image_paths[i:i + self.config.batch_size]
            batch_num = i // self.config.batch_size + 1
            total_batches = (total_images + self.config.batch_size - 1) // self.config.batch_size
            
            logger.info(f"Processing sub-batch {batch_num}/{total_batches} ({len(batch)} images)")
            
            # Process each image in the batch
            for image_path in batch:
                result = self.process_single_image(image_path, upload_to_notion)
                results.append(result)
                
                # Small delay between images to avoid overwhelming the system
                time.sleep(0.5)
        
        # Log summary
        success_count = sum(1 for r in results if r.success)
        error_count = total_images - success_count
        total_time = sum(r.processing_time for r in results)
        
        logger.info(f"Batch complete: {success_count} success, {error_count} errors, {total_time:.1f}s total")
        
        return results
    
    def _run_digitizer(self, image_path: str, upload_to_notion: bool) -> DigitizerResult:
        """Run the digitizer CLI for a single image"""
        try:
            # Build command
            cmd = [
                "python", str(self.digitizer_script),
                "--parser", self.config.parser_type,
                image_path
            ]
            
            # Add notion upload flag if available and requested
            if upload_to_notion and self.has_notion_uploader:
                cmd.append("--upload-notion")
            
            # Set up environment
            env = os.environ.copy()
            # Ensure API keys are available
            if not env.get('OPENAI_API_KEY'):
                logger.warning("OPENAI_API_KEY not found in environment")
            if upload_to_notion and not env.get('NOTION_TOKEN'):
                logger.warning("NOTION_TOKEN not found in environment")
            
            # Run digitizer with timeout
            start_time = time.time()
            result = subprocess.run(
                cmd,
                cwd=str(self.digitizer_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout
            )
            
            processing_time = time.time() - start_time
            
            if result.returncode == 0:
                # Parse output for structured data
                output_data = self._parse_digitizer_output(result.stdout)
                
                return DigitizerResult(
                    success=True,
                    image_path=image_path,
                    output_data=output_data,
                    processing_time=processing_time
                )
            else:
                return DigitizerResult(
                    success=False,
                    image_path=image_path,
                    error_message=result.stderr or "Unknown error",
                    processing_time=processing_time
                )
                
        except subprocess.TimeoutExpired:
            return DigitizerResult(
                success=False,
                image_path=image_path,
                error_message=f"Timeout after {self.config.timeout} seconds"
            )
        except Exception as e:
            return DigitizerResult(
                success=False,
                image_path=image_path,
                error_message=str(e)
            )
    
    def _parse_digitizer_output(self, output: str) -> Optional[Dict]:
        """Parse structured data from digitizer output"""
        try:
            # Look for JSON output in the stdout
            lines = output.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            
            # If no JSON found, create basic structure from text
            return {
                "raw_output": output,
                "processed_at": datetime.now().isoformat(),
                "parser_type": self.config.parser_type
            }
            
        except Exception as e:
            logger.error(f"Error parsing digitizer output: {e}")
            return None
    
    def validate_environment(self) -> Tuple[bool, List[str]]:
        """Validate environment and dependencies"""
        issues = []
        
        # Check Python environment
        try:
            result = subprocess.run(
                ["python", "--version"],
                cwd=str(self.digitizer_path),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                issues.append("Python not available in digitizer path")
        except Exception:
            issues.append("Failed to check Python version")
        
        # Check required environment variables
        required_vars = ['OPENAI_API_KEY']
        for var in required_vars:
            if not os.getenv(var):
                issues.append(f"Missing environment variable: {var}")
        
        # Check optional environment variables for Notion
        if self.has_notion_uploader:
            notion_vars = ['NOTION_TOKEN', 'NOTION_DATABASE_ID']
            for var in notion_vars:
                if not os.getenv(var):
                    issues.append(f"Missing Notion variable: {var} (Notion upload will fail)")
        
        # Test digitizer script
        try:
            result = subprocess.run(
                ["python", str(self.digitizer_script), "--help"],
                cwd=str(self.digitizer_path),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                issues.append("Digitizer script failed help test")
        except Exception as e:
            issues.append(f"Failed to test digitizer script: {e}")
        
        is_valid = len(issues) == 0
        if is_valid:
            logger.info("Environment validation passed")
        else:
            logger.warning(f"Environment validation found {len(issues)} issues")
            for issue in issues:
                logger.warning(f"  - {issue}")
        
        return is_valid, issues
    
    def get_processing_stats(self) -> Dict:
        """Get processing statistics from output directory"""
        try:
            # Look for output files in the digitizer directory
            output_patterns = [
                self.digitizer_path / "*.json",
                self.digitizer_path / "*_processed.json",
                self.digitizer_path / "output" / "*.json"
            ]
            
            processed_files = []
            for pattern in output_patterns:
                processed_files.extend(list(pattern.parent.glob(pattern.name)))
            
            stats = {
                "total_processed": len(processed_files),
                "last_processed": None,
                "output_directory": str(self.digitizer_path),
                "has_notion_uploader": self.has_notion_uploader
            }
            
            # Get last processed time
            if processed_files:
                latest_file = max(processed_files, key=lambda f: f.stat().st_mtime)
                stats["last_processed"] = datetime.fromtimestamp(
                    latest_file.stat().st_mtime
                ).isoformat()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting processing stats: {e}")
            return {}
    
    def cleanup_old_outputs(self, days_old: int = 30) -> int:
        """Clean up old output files"""
        try:
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)
            cleaned_count = 0
            
            # Look for old JSON files
            output_files = list(self.digitizer_path.glob("*_processed.json"))
            output_files.extend(list(self.digitizer_path.glob("output/*.json")))
            
            for file_path in output_files:
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned old output: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Failed to clean {file_path}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned {cleaned_count} old output files")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0

def test_digitizer_integration():
    """Test function for digitizer integration"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test configuration
    config = ProcessingConfig(
        digitizer_path="/Users/shashanksingh/Desktop/AI Projects/Planner Digitizer",
        retry_attempts=2,
        retry_delay=2,
        timeout=60,
        batch_size=2
    )
    
    try:
        # Test initialization
        integration = DigitizerIntegration(config)
        
        # Test environment validation
        is_valid, issues = integration.validate_environment()
        print(f"Environment valid: {is_valid}")
        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  - {issue}")
        
        # Test stats
        stats = integration.get_processing_stats()
        print(f"Processing stats: {stats}")
        
        # Test cleanup (dry run)
        cleaned = integration.cleanup_old_outputs(days_old=365)  # Very old files only
        print(f"Cleaned {cleaned} old files")
        
    except Exception as e:
        print(f"Test error: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_digitizer_integration()