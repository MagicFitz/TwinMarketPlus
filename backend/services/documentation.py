"""Published-document discovery with a fail-closed Markdown boundary."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from backend.settings import Settings

from .read_only import ReadOnlyStore


class FrontmatterLoader(yaml.SafeLoader):
    """Reject duplicate or non-string YAML mapping keys before publication checks."""

    def construct_mapping(self, node, deep: bool = False):  # type: ignore[no-untyped-def]
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if any(not isinstance(key, str) for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("Invalid frontmatter keys")
        return super().construct_mapping(node, deep=deep)


class DocumentationService:
    """Read only explicitly published Markdown files under ``project_root/docs``."""

    def __init__(self, settings: Settings, store: ReadOnlyStore | None = None):
        self.settings = settings
        self.store = store or ReadOnlyStore(settings)
        self.project_root = Path(settings.project_root).resolve()

    @property
    def docs_root(self) -> Path:
        return self.store.local(self.project_root / "docs")

    def published_documents(self) -> list[dict[str, Any]]:
        root = self.docs_root
        result: list[dict[str, Any]] = []
        if not root.is_dir():
            return result
        for candidate in sorted(root.rglob("*.md")):
            try:
                path = candidate.resolve()
                if not path.is_relative_to(root) or path.is_symlink() or candidate.is_symlink():
                    continue
                if not path.is_file() or path.stat().st_size > 1024 * 1024:
                    continue
                source = path.read_text(encoding="utf-8-sig")
                match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", source, re.S)
                if not match or len(match.group(1)) > 16384:
                    continue
                metadata = yaml.load(match.group(1), Loader=FrontmatterLoader)
                if not isinstance(metadata, dict) or metadata.get("published") is not True:
                    continue
                body = source[match.end() :].lstrip("\r\n")
                heading = re.search(r"^#\s+(.+)$", body, re.M)
                title = metadata.get("title", heading.group(1) if heading else path.stem)
                category = metadata.get("category", "文档")
                order = metadata.get("order", 100)
                if not isinstance(title, str) or not isinstance(category, str):
                    continue
                if type(order) is not int:
                    order = 100
                result.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "title": title[:160],
                        "category": category[:80],
                        "order": order,
                        "content": body,
                    }
                )
            except (OSError, ValueError, yaml.YAMLError, RecursionError):
                # An unreadable or malformed file is private by default.
                continue
        return sorted(result, key=lambda item: (item["order"], item["title"], item["path"]))

    def documentation(self, path: str | None = None) -> dict[str, Any]:
        # Re-read on every request so publication revocation and edits are immediate.
        documents = self.published_documents()
        if path is not None:
            for document in documents:
                if document["path"] == path:
                    return document
            raise KeyError("Unpublished or unknown document")
        return {"items": [{key: value for key, value in doc.items() if key != "content"} for doc in documents]}


def published_documents(settings: Settings) -> list[dict[str, Any]]:
    return DocumentationService(settings).published_documents()


def documentation(settings: Settings, path: str | None = None) -> dict[str, Any]:
    """Return the legacy list DTO or a single published document DTO."""
    return DocumentationService(settings).documentation(path)
