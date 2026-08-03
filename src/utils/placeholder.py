import re
from typing import Set


PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


def extract_placeholders(text: str) -> Set[str]:
    return set(PLACEHOLDER_PATTERN.findall(text or ""))
