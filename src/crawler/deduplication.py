"""Content-based deduplication for crawler.

Prevents storing duplicate content that appears at different URLs.
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional


class ContentDeduplicator:
    """Tracks content hashes to prevent storing duplicates."""

    def __init__(self):
        """Initialize empty hash store."""
        self.content_hashes: Dict[str, str] = {}  # {hash: filename}

    def get_content_hash(self, text: str) -> str:
        """Compute MD5 hash of content."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def is_duplicate(
        self, text: str, proposed_filename: str
    ) -> tuple[bool, Optional[str]]:
        """Check if content is a duplicate.

        Args:
            text: Content to check
            proposed_filename: Filename we'd use for this content

        Returns:
            (is_duplicate, original_filename) - (True, filename) if duplicate found
        """
        content_hash = self.get_content_hash(text)

        if content_hash in self.content_hashes:
            original = self.content_hashes[content_hash]
            return True, original

        # Not a duplicate, register this hash
        self.content_hashes[content_hash] = proposed_filename
        return False, None

    def load_existing_hashes(self, output_dir: Path):
        """Load hashes of already-stored files.

        Allows deduplication across crawler sessions.
        """
        if not output_dir.exists():
            return

        for file_path in output_dir.glob("*.txt"):
            try:
                text = file_path.read_text(encoding="utf-8")
                content_hash = self.get_content_hash(text)
                self.content_hashes[content_hash] = file_path.name
            except Exception as e:
                print(f"  [WARNING] Could not load hash for {file_path.name}: {e}")

    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        return {
            "unique_files": len(self.content_hashes),
            "hashes_tracked": len(self.content_hashes),
        }
