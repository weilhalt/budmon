# Changelog

All notable changes to this project will be documented in this file.

## [1.0.1] — 2026-04-03

### Added
- Real-time dashboard for Claude Code token usage monitoring
- 5h / 7d quota progress bars with configurable warning and alarm thresholds
- Burn rate analysis (% per hour / per day)
- Expiry estimate with reserve calculation (time until quota exhaustion vs. reset)
- Countdown ring showing reset or expiry (whichever comes first)
- Token breakdown per request and cumulative (input, output, cache create, cache read)
- Cost display in USD based on model-specific token prices
- Cache ratio sparkline with historical trend and average
- Model presets: Opus, Sonnet, Haiku, Custom
- Multi-language support: German and English, auto-detects system language
- INI configuration file (~/.claude/budmon.ini) with commented defaults
- Dark theme with consistent custom popup menus
- HiDPI / 4K support (Windows, Linux, macOS)
- Window position persistence with screen bounds check
- Read-only Node.js fetch interceptor for Claude Code API response capture
- CLI: `budmon --setup`, `--uninstall`, `--version`, `--help`
- Auto-setup dialog on first start when no data is found
- Desktop entry generation on Linux (`budmon --setup`)
- Application icon (Lucide "activity", MIT licensed)
- About dialog with version, author, license, homepage
- Logs menu: session log, history log, open folder
- Settings menu: language, model, INI editor
- Fallback to budget_velocity.json for users with existing interceptors
- Cross-platform file viewer and folder opener (Linux, macOS, Windows)
- 50 unit tests
