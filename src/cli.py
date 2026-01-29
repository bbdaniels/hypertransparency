#!/usr/bin/env python3
"""
Hypertransparency CLI
=====================
Command-line interface for building hypertransparency documentation sites.
"""

import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .builder import HypertransparencyBuilder


def main():
    parser = argparse.ArgumentParser(
        prog="hypertransparency",
        description="Generate beautiful documentation sites from Claude Code conversations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hypertransparency build                    # Build in current directory
  hypertransparency build /path/to/repo      # Build for specific repo
  hypertransparency build -o ./site          # Custom output directory
  hypertransparency init                     # Create config file
  hypertransparency serve                    # Preview locally

For more info: https://github.com/bbdaniels/hypertransparency
        """
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build the documentation site")
    build_parser.add_argument("repo", nargs="?", default=".", help="Repository path (default: current directory)")
    build_parser.add_argument("-o", "--output", help="Output directory (default: repo/docs)")
    build_parser.add_argument("-c", "--config", help="Config file path (default: .hypertransparency.json)")
    build_parser.add_argument("--name", help="Project name")
    build_parser.add_argument("--description", help="Project description")
    build_parser.add_argument("--repo-url", help="Repository URL (for GitHub links)")
    build_parser.add_argument("--branch", default="main", help="Main branch name")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize configuration file")
    init_parser.add_argument("repo", nargs="?", default=".", help="Repository path")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Preview site locally")
    serve_parser.add_argument("dir", nargs="?", default="docs", help="Directory to serve")
    serve_parser.add_argument("-p", "--port", type=int, default=8000, help="Port number")

    args = parser.parse_args()

    if args.command == "build":
        cmd_build(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


def cmd_build(args):
    """Build the documentation site."""
    repo_path = Path(args.repo).resolve()

    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)

    # Load config file if exists
    config = {}
    project_config = {}

    config_file = Path(args.config) if args.config else repo_path / ".hypertransparency.json"
    if config_file.exists():
        print(f"Loading config from {config_file}")
        with open(config_file) as f:
            loaded = json.load(f)
            config = loaded.get("build", {})
            project_config = loaded.get("project", {})

    # Override with command-line arguments
    if args.name:
        project_config["name"] = args.name
    if args.description:
        project_config["description"] = args.description
    if args.repo_url:
        project_config["repository"] = args.repo_url
    if args.branch:
        project_config["branch"] = args.branch

    # Set defaults
    if "name" not in project_config:
        project_config["name"] = repo_path.name
    if "description" not in project_config:
        project_config["description"] = "AI-assisted development documentation"

    output_dir = Path(args.output) if args.output else None

    try:
        builder = HypertransparencyBuilder(str(repo_path), str(output_dir) if output_dir else None, config)
        stats = builder.build(project_config)

        print("\n" + "=" * 50)
        print("Build complete!")
        print(f"  Messages: {stats['totalMessages']}")
        print(f"  Commits:  {stats['totalCommits']}")
        print(f"  Images:   {stats['totalImages']}")
        print(f"  Sessions: {stats['sessions']}")
        print("=" * 50)
        print(f"\nTo preview: hypertransparency serve {builder.output_dir}")
        print(f"To deploy:  Push {builder.output_dir} to GitHub Pages")

    except Exception as e:
        print(f"Error building site: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_init(args):
    """Initialize configuration file."""
    repo_path = Path(args.repo).resolve()
    config_file = repo_path / ".hypertransparency.json"

    if config_file.exists():
        print(f"Config file already exists: {config_file}")
        response = input("Overwrite? [y/N] ")
        if response.lower() != "y":
            return

    # Try to detect project info from git
    name = repo_path.name
    description = "AI-assisted development documentation"
    repo_url = ""

    try:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path, capture_output=True, text=True
        )
        if result.returncode == 0:
            repo_url = result.stdout.strip()
            # Convert SSH to HTTPS
            if repo_url.startswith("git@github.com:"):
                repo_url = repo_url.replace("git@github.com:", "https://github.com/")
            if repo_url.endswith(".git"):
                repo_url = repo_url[:-4]
    except:
        pass

    config = {
        "project": {
            "name": name,
            "description": description,
            "repository": repo_url,
            "branch": "main"
        },
        "build": {
            "messages_per_page": 100,
            "image_folders": ["explore", "outputs", "figures"],
            "show_thinking_preview": True
        }
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Created config file: {config_file}")
    print("\nEdit this file to customize your site, then run:")
    print(f"  hypertransparency build {args.repo}")


def cmd_serve(args):
    """Serve the site locally for preview."""
    import http.server
    import socketserver

    directory = Path(args.dir).resolve()
    if not directory.exists():
        print(f"Error: Directory does not exist: {directory}")
        print("Run 'hypertransparency build' first to generate the site.")
        sys.exit(1)

    port = args.port

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving {directory} at http://localhost:{port}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped")


if __name__ == "__main__":
    main()
