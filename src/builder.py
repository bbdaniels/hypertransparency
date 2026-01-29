#!/usr/bin/env python3
"""
Hypertransparency Site Builder
==============================
Generates a performant static site from Claude conversation transcripts.

Features:
- iMessage-style chat interface
- Paginated JSON data for large conversations
- Git commit integration with bidirectional linking
- Image versioning (shows historical versions in context)
- Search functionality
- Responsive minimap navigation
"""

import json
import re
import os
import subprocess
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Any
import shutil

class HypertransparencyBuilder:
    """Main builder class for generating hypertransparency documentation sites."""

    DEFAULT_CONFIG = {
        "messages_per_page": 100,
        "search_enabled": True,
        "show_thinking_preview": True,
        "tool_result_max_length": 500,
        "exclude_patterns": ["*.env", "*password*", "*secret*", "*token*"],
        "image_folders": ["explore", "outputs", "figures"],
        "time_window_minutes": 5,  # For matching images to messages
    }

    def __init__(self, repo_path: str, output_dir: str = None, config: dict = None):
        """
        Initialize the builder.

        Args:
            repo_path: Path to the git repository
            output_dir: Output directory for the site (default: repo_path/docs)
            config: Optional configuration overrides
        """
        self.repo_path = Path(repo_path).resolve()
        self.output_dir = Path(output_dir) if output_dir else self.repo_path / "docs"
        self.data_dir = self.output_dir / "data"
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.artifacts = {}

    def get_claude_project_dir(self) -> Path:
        """Auto-detect Claude project directory for this repo."""
        claude_base = Path.home() / ".claude" / "projects"
        path_key = str(self.repo_path).replace("/", "-")
        return claude_base / path_key

    def get_all_sessions(self) -> List[dict]:
        """Get all session JSONL files for this project."""
        project_dir = self.get_claude_project_dir()
        if not project_dir.exists():
            return []

        sessions = []
        indexed_ids = set()
        index_file = project_dir / "sessions-index.json"

        if index_file.exists():
            with open(index_file) as f:
                index = json.load(f)
                for entry in index.get("entries", []):
                    indexed_ids.add(entry["sessionId"])
                    sessions.append({
                        "id": entry["sessionId"],
                        "path": Path(entry["fullPath"]),
                        "created": entry.get("created"),
                        "modified": entry.get("modified"),
                        "messageCount": entry.get("messageCount", 0),
                        "firstPrompt": entry.get("firstPrompt", "")[:100],
                        "branch": entry.get("gitBranch", "unknown")
                    })

        # Also scan for any JSONL files not in the index
        for jsonl in project_dir.glob("*.jsonl"):
            if jsonl.stem not in indexed_ids:
                sessions.append({
                    "id": jsonl.stem,
                    "path": jsonl,
                    "created": datetime.fromtimestamp(jsonl.stat().st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(jsonl.stat().st_mtime).isoformat(),
                })

        return sorted(sessions, key=lambda s: s.get("created", ""))

    def parse_transcript(self, path: Path) -> List[dict]:
        """Parse a single JSONL transcript into messages."""
        messages = []

        with open(path, "r") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                if entry.get("type") not in ["user", "assistant"]:
                    continue

                msg = self._parse_message_entry(entry, line_num)
                if msg and (msg["content"]["text"] or msg["content"]["toolCalls"]):
                    messages.append(msg)

        return messages

    def _parse_message_entry(self, entry: dict, line_num: int) -> Optional[dict]:
        """Parse a single message entry from JSONL."""
        message_data = entry.get("message", {})
        content_list = message_data.get("content", [])

        msg = {
            "id": f"msg_{entry.get('uuid', '')[:8]}",
            "uuid": entry.get("uuid", ""),
            "parentUuid": entry.get("parentUuid"),
            "role": entry["type"],
            "timestamp": entry.get("timestamp", ""),
            "sessionId": entry.get("sessionId", ""),
            "lineNum": line_num,
            "content": {
                "text": "",
                "textPreview": "",
                "hasThinking": False,
                "thinkingPreview": None,
                "toolCalls": []
            },
            "artifacts": [],
            "relatedCommits": [],
            "searchText": ""
        }

        text_parts = []
        search_parts = []

        for item in content_list:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type", "")

            if item_type == "text":
                text = item.get("text", "")
                # Strip system reminders and IDE context
                text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
                text = re.sub(r"<ide_opened_file>.*?</ide_opened_file>", "", text, flags=re.DOTALL)
                text = re.sub(r"<ide_selection>.*?</ide_selection>", "", text, flags=re.DOTALL)
                text = re.sub(r"<ide_file_context>.*?</ide_file_context>", "", text, flags=re.DOTALL)
                text = text.strip()
                if text:
                    text_parts.append(text)
                    search_parts.append(text.lower())

            elif item_type == "thinking":
                thinking = item.get("thinking", "")
                if thinking:
                    msg["content"]["hasThinking"] = True
                    if self.config["show_thinking_preview"]:
                        msg["content"]["thinkingPreview"] = thinking[:300] + "..." if len(thinking) > 300 else thinking

            elif item_type == "tool_result":
                tr_content = item.get("content", [])
                if isinstance(tr_content, str):
                    if tr_content.startswith("User has answered"):
                        text_parts.append(tr_content)
                        search_parts.append(tr_content.lower())
                elif isinstance(tr_content, list):
                    for trc in tr_content:
                        if isinstance(trc, dict) and trc.get("type") == "text":
                            text = trc.get("text", "")
                            if text.startswith("User has answered"):
                                text_parts.append(text)
                                search_parts.append(text.lower())

            elif item_type == "tool_use":
                tool_call = self._parse_tool_use(item)
                msg["content"]["toolCalls"].append(tool_call)

                artifact = self._extract_artifact_from_tool(tool_call, msg)
                if artifact:
                    msg["artifacts"].append(artifact["id"])

        msg["content"]["text"] = "\n\n".join(text_parts)
        msg["content"]["textPreview"] = msg["content"]["text"][:200] + "..." if len(msg["content"]["text"]) > 200 else msg["content"]["text"]
        msg["searchText"] = " ".join(search_parts)

        return msg

    def _parse_tool_use(self, item: dict) -> dict:
        """Parse a tool_use item into a structured format."""
        tool_name = item.get("name", "unknown")
        tool_input = item.get("input", {})
        preview = self._create_tool_preview(tool_name, tool_input)

        return {
            "id": item.get("id", ""),
            "name": tool_name,
            "input": self._sanitize_tool_input(tool_input),
            "inputPreview": preview,
            "hasResult": False,
            "resultPreview": None
        }

    def _create_tool_preview(self, name: str, input_data: dict) -> str:
        """Create a human-readable preview of a tool call."""
        previews = {
            "Read": lambda: f"Read {Path(input_data.get('file_path', '')).name}",
            "Write": lambda: f"Write {Path(input_data.get('file_path', '')).name}",
            "Edit": lambda: f"Edit {Path(input_data.get('file_path', '')).name}",
            "Bash": lambda: f"Run: {input_data.get('command', '')[:50]}{'...' if len(input_data.get('command', '')) > 50 else ''}",
            "Glob": lambda: f"Find files: {input_data.get('pattern', '')}",
            "Grep": lambda: f"Search: {input_data.get('pattern', '')[:30]}{'...' if len(input_data.get('pattern', '')) > 30 else ''}",
        }
        return previews.get(name, lambda: name)()

    def _sanitize_tool_input(self, input_data: dict) -> dict:
        """Remove potentially sensitive data from tool input."""
        sanitized = {}
        for key, value in input_data.items():
            if isinstance(value, str) and len(value) > self.config["tool_result_max_length"]:
                sanitized[key] = value[:self.config["tool_result_max_length"]] + "..."
            else:
                sanitized[key] = value
        return sanitized

    def _extract_artifact_from_tool(self, tool_call: dict, message: dict) -> Optional[dict]:
        """Extract file artifact from a tool call."""
        name = tool_call["name"]
        input_data = tool_call["input"]

        if name not in ["Write", "Edit", "Read"]:
            return None

        file_path = input_data.get("file_path", "")
        if not file_path:
            return None

        artifact_id = f"art_{hashlib.md5(f'{message['uuid']}_{file_path}'.encode()).hexdigest()[:8]}"

        artifact = {
            "id": artifact_id,
            "type": "file_edit" if name == "Edit" else "file_create" if name == "Write" else "file_read",
            "path": file_path,
            "relativePath": self._make_relative_path(file_path),
            "operation": name,
            "timestamp": message["timestamp"],
            "messageId": message["id"],
            "toolCallId": tool_call["id"],
            "metadata": {"language": self._detect_language(file_path)}
        }

        if name == "Edit":
            artifact["preview"] = {
                "before": (input_data.get("old_string", ""))[:100],
                "after": (input_data.get("new_string", ""))[:100]
            }

        self.artifacts[artifact_id] = artifact
        return artifact

    def _make_relative_path(self, abs_path: str) -> str:
        """Convert absolute path to relative path from repo root."""
        try:
            return str(Path(abs_path).relative_to(self.repo_path))
        except ValueError:
            return Path(abs_path).name

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python", ".do": "stata", ".js": "javascript", ".ts": "typescript",
            ".html": "html", ".css": "css", ".json": "json", ".md": "markdown",
            ".sh": "bash", ".r": "r", ".R": "r"
        }
        return ext_map.get(Path(file_path).suffix.lower(), "text")

    def get_git_commits(self) -> List[dict]:
        """Get all commits with timestamps and file changes."""
        try:
            result = subprocess.run(
                ["git", "log", "--format=%H|%ci|%s|%an", "--name-status", "--reverse"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=30
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        commits = []
        current_commit = None

        for line in result.stdout.split("\n"):
            if "|" in line and line.count("|") >= 3:
                if current_commit:
                    commits.append(current_commit)

                parts = line.split("|", 3)
                current_commit = {
                    "hash": parts[0][:7],
                    "fullHash": parts[0],
                    "timestamp": parts[1].strip(),
                    "message": parts[2].strip(),
                    "author": parts[3].strip() if len(parts) > 3 else "",
                    "filesChanged": [],
                    "relatedMessages": [],
                    "relatedArtifacts": []
                }
            elif current_commit and line.strip():
                parts = line.split("\t")
                if len(parts) >= 2:
                    current_commit["filesChanged"].append({
                        "status": parts[0],
                        "path": parts[1]
                    })

        if current_commit:
            commits.append(current_commit)

        return commits

    def match_commits_to_messages(self, messages: List[dict], commits: List[dict]):
        """Link commits to messages by timestamp proximity."""
        for commit in commits:
            try:
                ts = commit["timestamp"].split(" ")[0:2]
                commit_time = datetime.fromisoformat(" ".join(ts).replace(" ", "T"))
            except:
                continue

            for msg in messages:
                if msg["role"] != "assistant":
                    continue

                try:
                    ts = msg["timestamp"].replace("Z", "").split(".")[0]
                    msg_time = datetime.fromisoformat(ts)
                except:
                    continue

                delta = commit_time - msg_time
                if timedelta(0) <= delta <= timedelta(hours=1):
                    for artifact_id in msg["artifacts"]:
                        artifact = self.artifacts.get(artifact_id, {})
                        rel_path = artifact.get("relativePath", "")

                        for file_change in commit["filesChanged"]:
                            if rel_path and rel_path in file_change.get("path", ""):
                                commit["relatedMessages"].append(msg["id"])
                                commit["relatedArtifacts"].append(artifact_id)
                                msg["relatedCommits"].append(commit["hash"])
                                break

    def extract_versioned_artifacts(self, commits: List[dict]) -> dict:
        """Extract and store artifacts at each commit version."""
        artifacts_dir = self.data_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        image_versions = defaultdict(list)

        for commit in commits:
            commit_hash = commit["hash"]
            commit_dir = artifacts_dir / commit_hash
            commit_timestamp = commit.get("timestamp", "")

            for file_change in commit.get("filesChanged", []):
                file_path = file_change.get("path", "")
                if file_path.endswith(".png") or file_path.endswith(".jpg"):
                    try:
                        result = subprocess.run(
                            ["git", "show", f"{commit['fullHash']}:{file_path}"],
                            cwd=self.repo_path, capture_output=True, timeout=10
                        )
                        if result.returncode == 0:
                            commit_dir.mkdir(exist_ok=True)
                            image_name = Path(file_path).name
                            output_path = commit_dir / image_name
                            output_path.write_bytes(result.stdout)

                            local_path = f"data/artifacts/{commit_hash}/{image_name}"

                            commit.setdefault("versionedArtifacts", []).append({
                                "path": file_path,
                                "localPath": local_path
                            })

                            image_versions[image_name].append({
                                "commitHash": commit_hash,
                                "timestamp": commit_timestamp,
                                "localPath": local_path
                            })
                    except Exception:
                        pass

        return dict(image_versions)

    def get_images(self) -> List[dict]:
        """Get all PNG images from configured folders."""
        images_dir = self.output_dir / "images"
        images_dir.mkdir(exist_ok=True)

        images = []

        for folder in self.config["image_folders"]:
            folder_path = self.repo_path / folder
            if folder_path.exists():
                for img in sorted(folder_path.glob("*.png")):
                    stat = img.stat()
                    dest = images_dir / img.name
                    shutil.copy2(img, dest)

                    images.append({
                        "id": f"img_{img.stem}",
                        "name": img.name,
                        "path": f"images/{img.name}",
                        "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "fileSize": stat.st_size
                    })

        return images

    def build_search_index(self, messages: List[dict]) -> dict:
        """Build an inverted index for full-text search."""
        index = {
            "version": "1.0",
            "type": "inverted_index",
            "documents": len(messages),
            "terms": defaultdict(list),
            "documentMap": {}
        }

        for i, msg in enumerate(messages):
            index["documentMap"][str(i)] = {
                "id": msg["id"],
                "page": i // self.config["messages_per_page"] + 1,
                "role": msg["role"],
                "preview": msg["content"]["textPreview"][:50]
            }

            words = re.findall(r"\b\w+\b", msg["searchText"].lower())
            seen = set()
            for word in words:
                if len(word) >= 3 and word not in seen:
                    index["terms"][word].append(i)
                    seen.add(word)

        index["terms"] = dict(index["terms"])
        return index

    def paginate_messages(self, messages: List[dict]) -> List[dict]:
        """Split messages into pages."""
        pages = []
        page_size = self.config["messages_per_page"]

        for i in range(0, len(messages), page_size):
            page_num = i // page_size + 1
            page_messages = messages[i:i + page_size]

            pages.append({
                "version": "1.0",
                "page": page_num,
                "totalPages": (len(messages) + page_size - 1) // page_size,
                "startIndex": i,
                "endIndex": i + len(page_messages),
                "messages": page_messages
            })

        return pages

    def generate_manifest(self, messages: List[dict], commits: List[dict],
                         images: List[dict], sessions: List[dict], project_config: dict) -> dict:
        """Generate the manifest file with project metadata."""
        return {
            "version": "1.0",
            "project": project_config,
            "generated": datetime.now().isoformat(),
            "stats": {
                "totalMessages": len(messages),
                "userMessages": sum(1 for m in messages if m["role"] == "user"),
                "assistantMessages": sum(1 for m in messages if m["role"] == "assistant"),
                "totalArtifacts": len(self.artifacts),
                "totalCommits": len(commits),
                "totalImages": len(images),
                "sessions": len(sessions)
            },
            "pagination": {
                "messagesPerPage": self.config["messages_per_page"],
                "totalPages": (len(messages) + self.config["messages_per_page"] - 1) // self.config["messages_per_page"]
            },
            "sources": {
                "sessions": [s["id"] for s in sessions],
                "lastModified": max((s.get("modified", "") for s in sessions), default="")
            }
        }

    def build(self, project_config: dict = None) -> dict:
        """
        Build the complete transparency site.

        Args:
            project_config: Project metadata (name, description, repository URL)

        Returns:
            Build statistics
        """
        project_config = project_config or {
            "name": self.repo_path.name,
            "description": "AI-assisted development documentation",
            "repository": "",
            "branch": "main"
        }

        print(f"Building Hypertransparency site...")
        print(f"  Repository: {self.repo_path}")
        print(f"  Output: {self.output_dir}")

        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Get sessions and parse transcripts
        sessions = self.get_all_sessions()
        print(f"Found {len(sessions)} sessions")

        all_messages = []
        for session in sessions:
            if session["path"].exists():
                print(f"  Parsing {session['id'][:8]}...")
                messages = self.parse_transcript(session["path"])
                all_messages.extend(messages)

        all_messages.sort(key=lambda m: m.get("timestamp", ""))
        print(f"Total messages: {len(all_messages)}")

        # Git integration
        commits = self.get_git_commits()
        print(f"Found {len(commits)} commits")

        self.match_commits_to_messages(all_messages, commits)

        # Images
        images = self.get_images()
        print(f"Found {len(images)} images")

        # Versioned artifacts
        image_versions = self.extract_versioned_artifacts(commits)
        print(f"Tracked {len(image_versions)} images with version history")

        # Search index
        search_index = self.build_search_index(all_messages)
        print(f"Search index: {len(search_index['terms'])} terms")

        # Pagination
        pages = self.paginate_messages(all_messages)
        print(f"Paginated into {len(pages)} pages")

        # Manifest
        manifest = self.generate_manifest(all_messages, commits, images, sessions, project_config)

        # Write data files
        print("Writing data files...")

        with open(self.data_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        for page in pages:
            page_num = str(page["page"]).zfill(3)
            with open(self.data_dir / f"messages-{page_num}.json", "w") as f:
                json.dump(page, f)

        with open(self.data_dir / "commits.json", "w") as f:
            json.dump({"version": "1.0", "commits": commits}, f, indent=2)

        with open(self.data_dir / "artifacts.json", "w") as f:
            json.dump({"version": "1.0", "artifacts": self.artifacts}, f, indent=2)

        with open(self.data_dir / "images.json", "w") as f:
            json.dump({"version": "1.0", "images": images}, f, indent=2)

        with open(self.data_dir / "image-versions.json", "w") as f:
            json.dump({"version": "1.0", "imageVersions": image_versions}, f, indent=2)

        with open(self.data_dir / "index.json", "w") as f:
            json.dump(search_index, f)

        # Copy templates
        self._copy_templates()

        print(f"\nSite built successfully!")
        return manifest["stats"]

    def _copy_templates(self):
        """Copy HTML/CSS/JS templates to output directory."""
        templates_dir = Path(__file__).parent.parent / "templates"

        for template in ["chat.html", "index.html", "styles.css", "app.js"]:
            src = templates_dir / template
            if src.exists():
                shutil.copy(src, self.output_dir / template)


def build_site(repo_path: str, output_dir: str = None, config: dict = None,
               project_config: dict = None) -> dict:
    """
    Convenience function to build a site.

    Args:
        repo_path: Path to the git repository
        output_dir: Output directory (default: repo_path/docs)
        config: Builder configuration
        project_config: Project metadata

    Returns:
        Build statistics
    """
    builder = HypertransparencyBuilder(repo_path, output_dir, config)
    return builder.build(project_config)
