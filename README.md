# Planner Digitization Automation

A complete automation system for digitizing handwritten daily planner pages using OCR and AI-powered parsing. Automatically monitors a folder for new planner images, processes them using Apple's Vision OCR framework, and uploads structured data to Notion.

## Features

- **📁 Folder Monitoring**: Watches a designated folder for new planner images with 2-minute pause trigger
- **🔍 OCR Processing**: Uses Apple's Vision framework for local text extraction (no external APIs)
- **🤖 AI Parsing**: Leverages GPT-4o-mini for intelligent text parsing and structuring
- **📊 Notion Integration**: Automatically uploads parsed data to Notion databases
- **📅 Date Validation**: Extracts and validates dates, detects gaps in sequences
- **🔄 Retry Logic**: Robust error handling with configurable retry attempts
- **📋 Enhanced Logging**: Detailed notifications and status updates via structured logging
- **⏰ Scheduled Reminders**: Weekly reminders to maintain consistent planner scanning
- **🔍 Gap Detection**: Identifies missing dates in your planner sequence

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Folder Watcher │───▶│ Date Validator   │───▶│ Digitizer       │
│                 │    │                  │    │ Integration     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐             │
│ Notification    │◀───│ Automation       │◀────────────┘
│ Manager         │    │ Orchestrator     │
└─────────────────┘    └──────────────────┘
```

## Components

### Core Components

- **`automation_orchestrator.py`**: Main coordinator that manages all components
- **`folder_watcher.py`**: Monitors drop folder with pause-based triggering
- **`date_validator.py`**: Extracts dates from images and detects gaps
- **`digitizer_integration.py`**: CLI integration with existing digitizer system
- **`notification_manager.py`**: Handles Slack and Notion notifications

### Configuration

- **`.env`**: Environment variables for API keys and paths
- **`requirements.txt`**: Python dependencies
- **`.env.example`**: Template for environment configuration

## Setup

### 1. Prerequisites

- Python 3.8+
- macOS (for Apple Vision OCR framework)
- OpenAI API key
- Notion integration token and database ID
- Slack webhook URL (optional)

### 2. Installation

```bash
# Clone or download the automation system
cd planner-digitization-automation

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 3. Configuration

Edit the `.env` file with your settings:

```bash
# Slack Configuration (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_CHANNEL_NAME=personal-automation

# Notion Configuration (required)
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_database_id

# OpenAI Configuration (required)
OPENAI_API_KEY=your_openai_api_key

# Paths (required)
WATCH_FOLDER=/path/to/your/planner/images
DIGITIZER_PATH=/path/to/existing/digitizer

# Processing Configuration
PAUSE_MINUTES=2
RETRY_ATTEMPTS=3
BATCH_SIZE=5

# Reminder Schedule (Sunday 8 PM)
REMINDER_DAY=6
REMINDER_HOUR=20
REMINDER_MINUTE=0

# Logging
LOG_LEVEL=INFO
LOG_FILE=automation.log
```

### 4. Notion Database Setup

Create a Notion database with these properties:
- **Title** (title): Page title
- **Date** (date): Planner date
- **Schedule** (rich_text): Daily schedule entries
- **Notes** (rich_text): Additional notes

### 5. Enhanced Logging Configuration

The system uses structured logging for all notifications:

```bash
# In your .env file
LOG_LEVEL=INFO
LOG_FILE=automation.log
ENHANCED_LOGGING=true
```

Enhanced logging provides detailed status updates in the console and log files.

## Usage

### Running the Automation

```bash
# Start the automation system
python automation_orchestrator.py
```

The system will:
1. Monitor your watch folder for new images
2. Wait 2 minutes after file activity stops
3. Process images using OCR and AI parsing
4. Upload structured data to Notion
5. Log detailed processing results and status
6. Detect and report date gaps

### Manual Processing

You can also run components individually:

```bash
# Test folder watching
python folder_watcher.py

# Test date validation
python date_validator.py

# Test digitizer integration
python digitizer_integration.py

# Test notifications
python notification_manager.py
```

### Monitoring

The automation provides several monitoring features:

- **Enhanced Logging**: Structured console and file logging with detailed formatting
- **Processing Statistics**: Tracks success rates and performance metrics
- **Date Gap Detection**: Identifies missing planner pages with detailed reports
- **Error Tracking**: Comprehensive error logging with context and recommendations

## Configuration Options

### Processing Configuration

- **`PAUSE_MINUTES`**: Time to wait after file activity stops (default: 2)
- **`RETRY_ATTEMPTS`**: Number of retry attempts for failed processing (default: 3)
- **`BATCH_SIZE`**: Number of images to process in each batch (default: 5)

### Logging Configuration

- **`LOG_LEVEL`**: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- **`LOG_FILE`**: Optional log file path for persistent logging
- **`ENHANCED_LOGGING`**: Enable structured notification formatting (default: true)

### Reminder Configuration

- **`REMINDER_DAY`**: Day of week for reminders (0=Monday, 6=Sunday)
- **`REMINDER_HOUR`**: Hour for reminder (24-hour format)
- **`REMINDER_MINUTE`**: Minute for reminder

## File Processing Workflow

1. **File Detection**: New images detected in watch folder
2. **Pause Trigger**: 2-minute countdown starts after file activity stops
3. **Date Extraction**: OCR extracts dates from images for validation
4. **Duplicate Check**: Compares with existing Notion entries
5. **Processing Decision**: Determines whether to create new, update, or skip
6. **OCR & Parsing**: Processes images using Apple Vision + GPT-4o-mini
7. **Notion Upload**: Uploads structured data to database
8. **Notification**: Sends results via Slack
9. **Gap Detection**: Identifies missing dates in sequence

## Supported File Types

- JPG/JPEG images
- PNG images
- PDF files (first page)

## Error Handling

The system includes comprehensive error handling:

- **Retry Logic**: Automatic retries with exponential backoff
- **Timeout Protection**: Prevents hanging on problematic files
- **Graceful Degradation**: Continues processing other files if one fails
- **Error Notifications**: Immediate alerts for critical issues
- **Logging**: Detailed logs for troubleshooting

## Troubleshooting

### Common Issues

1. **Environment Variables**
   ```bash
   # Check if variables are loaded
   python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('API Key set:', bool(os.getenv('OPENAI_API_KEY')))"
   ```

2. **Folder Permissions**
   ```bash
   # Check folder access
   ls -la /path/to/watch/folder
   ```

3. **Notion Connection**
   ```bash
   # Test Notion API
   python -c "from notion_client import Client; Client(auth='your_token').users.me()"
   ```

4. **OCR Dependencies**
   ```bash
   # Verify PyObjC installation
   python -c "import Vision; print('Vision framework available')"
   ```

### Debug Mode

Enable debug logging:
```bash
LOG_LEVEL=DEBUG python automation_orchestrator.py
```

### Log Analysis

Check the automation log:
```bash
tail -f automation.log
```

## Performance

- **Processing Speed**: ~30-60 seconds per image (includes OCR + AI parsing)
- **Batch Processing**: Processes 5 images at a time by default
- **Memory Usage**: Low memory footprint with streaming processing
- **Rate Limiting**: Respects Notion API limits (3 requests/second)

## Security

- **Local OCR**: Uses Apple's Vision framework (no external API calls for OCR)
- **API Key Protection**: Environment variables for sensitive data
- **No Data Storage**: Processed data goes directly to your Notion workspace

## Customization

### Adding New File Types

Edit `folder_watcher.py`:
```python
self.supported_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.tiff'}
```

### Custom Parsing Rules

Modify the digitizer integration or create custom parsers in the existing digitizer system.

### Notification Templates

Customize message formats in `notification_manager.py`:
```python
def _format_processing_message(self, result, batch_files, success_rate):
    # Customize message format here
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs
3. Test individual components
4. Open an issue with detailed error information

## Changelog

### v1.0.0
- Initial release with complete automation system
- Folder monitoring with pause trigger
- OCR date extraction and validation
- Notion integration with duplicate detection
- Slack notifications and error handling
- Weekly reminder scheduling
- Comprehensive logging and error handling