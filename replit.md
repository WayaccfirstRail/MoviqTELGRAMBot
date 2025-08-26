# Captain M Telegram Bot

## Overview

This is an Arabic Telegram bot that serves as a companion to the Captain M entertainment platform. The bot provides users with access to movie and series catalogs, website status monitoring, and administrative user management features. Built with Python using the python-telegram-bot library, it offers a native Arabic language experience for users in the Middle East and North Africa region.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Bot Framework
The application is built using the `python-telegram-bot` library (version 20.3), which provides a high-level interface for interacting with the Telegram Bot API. The bot uses a command-based architecture where users interact through slash commands and inline keyboard buttons.

### Data Management
The bot employs an in-memory data storage approach for simplicity and quick deployment:
- **Static Content**: Movies and series catalogs are hardcoded as Python lists, mirroring content from the Captain M website
- **User State**: Banned, blocked, and flagged users are tracked in Python sets during runtime
- **Configuration**: Admin user IDs and invite codes are stored as constants and variables

### Command Structure
The bot implements a hierarchical command system:
- **Public Commands**: `/start`, `/movies`, `/series`, `/status`, `/invite` - available to all users
- **Admin Commands**: `/ban`, `/block`, `/flag`, `/change_invite` - restricted to admin users
- **Interactive Elements**: Inline keyboards for navigation between movies and series listings

### User Management System
A three-tier user classification system provides granular control:
- **Banned Users**: Completely ignored by the bot (silent treatment)
- **Blocked Users**: Tracked but receive warning messages when attempting interaction
- **Flagged Users**: Marked for admin review but retain full access

### Website Integration
The bot performs external website monitoring through HTTP requests to check the status of the Captain M platform, providing users with real-time availability information.

## External Dependencies

### Telegram Bot API
- **python-telegram-bot (v20.3)**: Core framework for bot functionality and message handling
- **Purpose**: Handles all Telegram-specific operations including message sending, command processing, and inline keyboards

### Web Scraping and HTTP
- **requests**: HTTP client for website status checking
- **beautifulsoup4**: HTML parsing capabilities for potential future content scraping

### Captain M Website
- **captainm.netlify.app**: External website for status monitoring
- **Integration**: HTTP GET requests to check site availability

### Deployment Platform
- **Replit**: Configured for deployment with environment variable support
- **Environment Variables**: `BOT_TOKEN` stored in Replit Secrets for secure token management

### Language Support
- **Arabic Language**: Full RTL (Right-to-Left) text support for native user experience
- **Unicode Handling**: Built-in Python Unicode support for Arabic character rendering