"""CFPMonitor extractor module.

Simplified rule extraction from conference CFP text files.

Public API:
    extract_and_save() - Main entry point (only function needed externally)

Advanced usage (if needed):
    extract_conference() - Extract rules without saving
    load_patterns() - Load pattern definitions
    load_fields() - Load field schema
"""

from .extractor import extract_and_save, extract_rules

__all__ = ["extract_and_save", "extract_rules"]
