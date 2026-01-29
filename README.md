# Hypertransparency

**Generate beautiful documentation sites from Claude Code conversations.**

Hypertransparency creates searchable, navigable documentation of your AI-assisted development process, showing the complete conversation history between you and Claude.

![Demo](demo/screenshot.png)

## Features

- **iMessage-style chat interface** - Clean, familiar UI for browsing conversations
- **Git integration** - Links commits to the conversations that created them
- **Image versioning** - Shows historical versions of images in context
- **Searchable** - Full-text search across all messages
- **Minimap navigation** - Quick access to exhibits and commits
- **Responsive design** - Works on desktop and mobile
- **GitHub Pages ready** - Deploy with a single push

## Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/bbdaniels/hypertransparency.git
cd hypertransparency

# Install (editable mode for development)
pip install -e .
```

Or install directly from GitHub:

```bash
pip install git+https://github.com/bbdaniels/hypertransparency.git
```

### Usage

1. **Navigate to your project repository:**

```bash
cd /path/to/your/repo
```

2. **Initialize configuration (optional):**

```bash
hypertransparency init
```

This creates a `.hypertransparency.json` config file you can customize.

3. **Build the documentation site:**

```bash
hypertransparency build
```

4. **Preview locally:**

```bash
hypertransparency serve
```

Open http://localhost:8000 in your browser.

5. **Deploy to GitHub Pages:**

```bash
# Enable GitHub Pages in your repo settings, pointing to /docs on main branch
git add docs/
git commit -m "Add hypertransparency documentation"
git push
```

## Configuration

Create a `.hypertransparency.json` file in your repo root:

```json
{
  "project": {
    "name": "My Project",
    "description": "AI-assisted development of awesome things",
    "repository": "https://github.com/username/repo",
    "branch": "main"
  },
  "build": {
    "messages_per_page": 100,
    "image_folders": ["explore", "outputs", "figures"],
    "show_thinking_preview": true
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `project.name` | Repo folder name | Display name for the project |
| `project.description` | - | Description shown on landing page |
| `project.repository` | Auto-detected | GitHub URL for commit links |
| `project.branch` | `main` | Default branch name |
| `build.messages_per_page` | `100` | Messages per page (for pagination) |
| `build.image_folders` | `["explore", "outputs", "figures"]` | Folders to scan for images |
| `build.show_thinking_preview` | `true` | Show Claude's thinking process |

## Command Reference

### `hypertransparency build`

Build the documentation site.

```bash
hypertransparency build [REPO_PATH] [OPTIONS]

Options:
  -o, --output DIR      Output directory (default: repo/docs)
  -c, --config FILE     Config file path
  --name NAME           Project name
  --description DESC    Project description
  --repo-url URL        Repository URL
  --branch BRANCH       Main branch name
```

### `hypertransparency init`

Create a configuration file.

```bash
hypertransparency init [REPO_PATH]
```

### `hypertransparency serve`

Preview the site locally.

```bash
hypertransparency serve [DIR] [OPTIONS]

Options:
  -p, --port PORT       Port number (default: 8000)
```

## How It Works

1. **Session Detection**: Finds Claude Code session files in `~/.claude/projects/`
2. **Transcript Parsing**: Extracts messages, tool calls, and artifacts from JSONL transcripts
3. **Git Integration**: Links commits to messages by timestamp proximity
4. **Image Versioning**: Extracts historical versions of images from git history
5. **Site Generation**: Creates paginated JSON data files and HTML/JS templates
6. **Search Index**: Builds an inverted index for full-text search

## Requirements

- Python 3.8+
- Git (for commit integration)
- Claude Code sessions in `~/.claude/projects/`

## Example Sites

- [Estonia QBS Analysis](https://bbdaniels.github.io/estonia-qbs/) - Econometric analysis development

## Contributing

Contributions welcome! Please open an issue or PR.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with Claude Code.
