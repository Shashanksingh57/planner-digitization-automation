# Integration Guide - Planner Automation with Existing Digitizer

This document explains how the automation system integrates with your existing planner digitizer.

## Overview

The automation system acts as a wrapper around your existing digitizer, providing automated folder monitoring, batch processing, and notifications while preserving all existing functionality.

## Architecture

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│ Automation System   │───▶│ Existing Digitizer  │───▶│ Notion Database     │
│ (planner-digitiz... │    │ (dailyplanner-...   │    │                     │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                           │                           │
         ▼                           ▼                           ▼
  • Folder watching           • OCR processing            • Data storage
  • Date validation           • AI parsing                • Page management
  • Notifications            • JSON generation
  • Scheduling
```

## Directory Structure

```
/Users/shashanksingh/Desktop/AI Projects/
├── planner-digitization-automation/     # New automation system
│   ├── automation_orchestrator.py       # Main coordinator
│   ├── folder_watcher.py                # File monitoring
│   ├── date_validator.py                # Date extraction
│   ├── digitizer_integration.py         # CLI integration
│   ├── notification_manager.py          # Slack/Notion alerts
│   └── .env.example                     # Configuration template
│
├── dailyplanner-digitizer-automation/   # Existing digitizer
│   ├── planner_digitizer.py            # Main processing script
│   ├── notion_uploader.py              # Notion integration
│   ├── notion_query.py                 # NEW: Query existing pages
│   ├── vision_ocr.py                   # OCR processing
│   └── .env                            # Environment config
│
└── AI Test Cases/Daily Planner Exports/
    ├── 2025 Daily Planner - Blue/      # Watch folder (input)
    └── Solution Outputs/                # Processed files (output)
```

## Integration Points

### 1. Two-Step Processing Workflow

The automation system uses your existing two-step process:

```bash
# Step 1: Process image → Generate JSON
python planner_digitizer.py image.jpg --parser simple
# → Creates: image_processed.json in Solution Outputs/

# Step 2: Upload JSON → Notion
python notion_uploader.py image_processed.json
# → Uploads to Notion database
```

### 2. Environment Configuration

The automation loads environment variables from your digitizer's `.env` file:

```bash
# From: /Users/shashanksingh/Desktop/AI Projects/dailyplanner-digitizer-automation/.env
OPENAI_API_KEY=your_key_here
NOTION_TOKEN=your_token_here
NOTION_DATABASE_ID=your_database_id
```

### 3. File Management

**Input Processing:**
- Automation monitors: `/Users/shashanksingh/Desktop/AI Test Cases/Daily Planner Exports/`
- Processes images with 2-minute pause trigger
- Validates dates and checks for duplicates

**Output Handling:**
- JSON files generated in: `Solution Outputs/[image_name]_processed.json`
- Follows existing naming convention
- Maintains file structure compatibility

### 4. Date Validation Integration

**New Component: `notion_query.py`**
- Queries existing Notion pages
- Generates `notion_pages_summary.json` with date mappings
- Used by automation for duplicate detection

**Date Extraction Process:**
1. Run `planner_digitizer.py` on image
2. Parse generated JSON file for `planner_data.date` field
3. Compare against existing Notion entries
4. Determine action: new/update/skip

## Configuration

### Automation System Setup

1. **Copy environment template:**
   ```bash
   cd planner-digitization-automation
   cp .env.example .env
   ```

2. **Configure paths in `.env`:**
   ```bash
   WATCH_FOLDER=/Users/shashanksingh/Desktop/AI Test Cases/Daily Planner Exports
   DIGITIZER_PATH=/Users/shashanksingh/Desktop/AI Projects/dailyplanner-digitizer-automation
   
   # Notion credentials (loaded from digitizer .env)
   NOTION_TOKEN=your_token_here
   NOTION_DATABASE_ID=your_database_id
   
   # Optional: Slack notifications
   SLACK_WEBHOOK_URL=your_webhook_url
   ```

### Environment Loading Priority

1. **Automation .env** (automation-specific settings)
2. **Digitizer .env** (API keys and credentials)
3. **System environment** (fallback)

## Processing Flow

### Automated Workflow

1. **File Detection**
   - New images dropped in watch folder
   - 2-minute pause after activity stops
   - Triggers batch processing

2. **Date Validation**
   - Extract date from each image using existing digitizer
   - Query Notion for existing entries
   - Determine processing action per file

3. **Batch Processing**
   - Process images in batches (default: 5)
   - Step 1: `planner_digitizer.py` → JSON files
   - Step 2: `notion_uploader.py` → Notion upload
   - Retry logic with exponential backoff

4. **Notifications**
   - Slack alerts on completion/errors
   - Processing statistics and success rates
   - Date gap detection reports

### Manual Override

Your existing manual workflow remains unchanged:

```bash
# Still works exactly as before
cd dailyplanner-digitizer-automation
python planner_digitizer.py image.jpg --parser simple
python notion_uploader.py
```

## Error Handling

### Integration Safety

- **Non-destructive**: Automation never modifies existing scripts
- **Graceful degradation**: Continues processing if individual files fail
- **Retry logic**: Automatic retries with backoff
- **Isolation**: Failed automation doesn't break manual workflow

### Error Recovery

1. **Step 1 failures**: Retry digitizer processing
2. **Step 2 failures**: Retry Notion upload separately
3. **Environment issues**: Load from multiple .env sources
4. **File conflicts**: Use timestamp-based file detection

## Monitoring

### Real-time Logging

```bash
# Start automation with logging
python automation_orchestrator.py

# Monitor logs
tail -f automation.log
```

### Slack Notifications

- **Processing summaries**: Success/failure counts
- **Error alerts**: Critical issues requiring attention
- **Weekly reminders**: Maintain consistent scanning
- **Gap detection**: Missing date sequences

### Statistics Tracking

- **Total files processed**
- **Success/failure rates**
- **Processing times**
- **Notion upload status**

## Testing

### Component Testing

```bash
# Test individual components
python digitizer_integration.py    # Test CLI integration
python date_validator.py          # Test date extraction
python notification_manager.py    # Test Slack alerts
python folder_watcher.py         # Test file monitoring
```

### Integration Testing

```bash
# Test with sample image
cd planner-digitization-automation
python -c "
from digitizer_integration import DigitizerIntegration, ProcessingConfig
config = ProcessingConfig(digitizer_path='../dailyplanner-digitizer-automation')
integration = DigitizerIntegration(config)
result = integration.process_single_image('/path/to/test/image.jpg')
print(f'Success: {result.success}')
"
```

## Troubleshooting

### Common Issues

1. **Environment Variables Not Found**
   ```bash
   # Check .env files exist
   ls -la */\.env
   
   # Test environment loading
   python -c "import os; print(os.getenv('OPENAI_API_KEY'))"
   ```

2. **Path Resolution Issues**
   ```bash
   # Verify paths in configuration
   python -c "
   from pathlib import Path
   print('Digitizer exists:', Path('../dailyplanner-digitizer-automation').exists())
   print('Watch folder exists:', Path('/Users/shashanksingh/Desktop/AI Test Cases/Daily Planner Exports').exists())
   "
   ```

3. **JSON File Not Found**
   ```bash
   # Check output directory permissions
   ls -la "/Users/shashanksingh/Desktop/AI Test Cases/Daily Planner Exports/Solution Outputs/"
   ```

4. **Notion Connection Issues**
   ```bash
   # Test Notion query script
   cd dailyplanner-digitizer-automation
   python notion_query.py
   ```

### Debug Mode

Enable verbose logging:

```bash
LOG_LEVEL=DEBUG python automation_orchestrator.py
```

## Maintenance

### Regular Tasks

1. **Monitor processing statistics**
2. **Review error logs weekly**
3. **Clean old output files periodically**
4. **Update API keys as needed**

### Backup Strategy

- **Configuration files**: Back up both .env files
- **Processing logs**: Archive automation.log monthly
- **JSON outputs**: Retain in Solution Outputs for recovery

## Future Enhancements

### Planned Improvements

1. **Enhanced error recovery**: Automatic environment repair
2. **Performance optimization**: Parallel processing
3. **Advanced filtering**: Content-based file validation
4. **Dashboard integration**: Web UI for monitoring

### Customization Points

- **Processing rules**: Modify `digitizer_integration.py`
- **Notification templates**: Update `notification_manager.py`
- **File patterns**: Adjust `folder_watcher.py`
- **Date validation**: Enhance `date_validator.py`

## Support

For integration issues:

1. Check this guide first
2. Review component logs
3. Test individual components
4. Verify environment configuration
5. Test manual workflow still works

The automation system is designed to be a transparent layer that enhances your existing workflow without disrupting it.