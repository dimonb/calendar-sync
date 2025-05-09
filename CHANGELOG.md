# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2025-05-09

- fdfc380 - Refactor documentation and improve logging messages in calendar sync
- 4132811 - Enhance calendar sync event processing and logging
- 02871dd - Update logging in CaldavCalendar to use repr for event details
- 6ec1a7d - Add log level configuration to calendar sync service
- cdeccbc - Enhance event fetching and processing in calendar sync service
- 06d76ae - Update deployment configuration and environment settings for calendar sync service
- 3ceefca - Refactor calendar sync service and enhance configuration management
- 4bb8b10 - Implement token saving after refresh in Google Calendar authentication
- 27c1611 - Update Dockerfile and GitHub Actions workflow for improved dependency management
- 949915d - Refactor Dockerfile and update dependencies for calendar sync service
- 28e4815 - Enhance calendar sync Helm chart and GitHub Actions workflow
- b448e5c - Refactor GitHub Actions workflow to compute and use Docker image hash
- 242d4ba - Enhance Kubernetes deployment configuration and update Helm chart
- df51552 - Add GitHub Actions workflow for deploying Calendar Sync Chart to Kubernetes
- 4dfc85f - Refactor Dockerfile for calendar sync service: update file paths and command execution
- 27ce488 - Update .gitignore to exclude .kube_config file
- 4c97333 - Update README.md to clarify usage of `onlysource` flag for Google Calendar configuration
- 1f6e476 - Add optional `onlysource` flag for Google Calendar configuration in README
- 658281d - Refactor calendar integration: consolidate calendar classes under BaseCalendar, enhance event handling, and improve logging
- ac2f34e - Add Google Calendar and CalDAV integration with event handling, enhance logging, and update dependencies
- f14750f - Update calendar sync service: add support for username and password in CalDAV integration, enhance logging, and include Google and Outlook calendar classes with mock implementations. Update dependencies and .gitignore for new configuration files.
- 213d52c - Initial implementation of the calendar-sync service, including Dockerfile, project configuration, and core functionality for synchronizing events across Google Calendar, Outlook, and CalDAV. Added CI/CD setup with Helm for Kubernetes deployment.
- 0201f67 - Initial commit