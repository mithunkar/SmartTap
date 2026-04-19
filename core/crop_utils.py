from __future__ import annotations

import re
from typing import Dict, Iterable, List


def normalize_free_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())
    return " ".join(cleaned.split())


def canonicalize_crop_name(name: str) -> str:
    cleaned = " ".join(str(name or "").strip().split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.endswith("oes") and len(cleaned) > 4:
        cleaned = cleaned[:-2]
        lowered = cleaned.lower()
    if lowered.endswith("ies") and len(cleaned) > 3:
        cleaned = cleaned[:-3] + "y"
        lowered = cleaned.lower()
    if lowered.endswith("s") and not lowered.endswith("ss") and len(cleaned) > 3:
        cleaned = cleaned[:-1]
    return cleaned.title()


def crop_name_variants(name: str) -> set[str]:
    canonical = canonicalize_crop_name(name).lower()
    if not canonical:
        return set()
    variants = {canonical}
    if canonical.endswith("y"):
        variants.add(canonical[:-1] + "ies")
    elif canonical.endswith(("o", "s", "x", "z", "ch", "sh")):
        variants.add(canonical + "es")
    else:
        variants.add(canonical + "s")
    return variants


def normalize_crop_phrase(phrase: str) -> str:
    cleaned = canonicalize_crop_name(phrase)
    lowered = cleaned.lower()
    leading_terms = (
        "irrigated vs non irrigated ",
        "irrigated versus non irrigated ",
        "non irrigated vs irrigated ",
        "non irrigated versus irrigated ",
        "irrigated ",
        "non irrigated ",
    )
    for term in leading_terms:
        if lowered.startswith(term):
            cleaned = cleaned[len(term):].strip()
            lowered = cleaned.lower()
    trailing_terms = (" farm", " farms", " field", " fields", " orchard", " orchards", " vineyard", " vineyards", " crop", " crops")
    for term in trailing_terms:
        if lowered.endswith(term):
            cleaned = cleaned[: -len(term)].strip()
            lowered = cleaned.lower()
    return canonicalize_crop_name(cleaned)


def matching_crop_codes(crop_filter: str, crop_names: Dict[int, Dict]) -> List[int]:
    canonical = canonicalize_crop_name(crop_filter)
    if not canonical:
        return []

    normalized_filter = canonical.lower()
    codes: List[int] = []
    for code, info in crop_names.items():
        crop_name = canonicalize_crop_name(str(info.get("name") or ""))
        if not crop_name:
            continue
        crop_lower = crop_name.lower()
        if (
            normalized_filter in crop_lower
            or crop_lower in normalized_filter
            or normalized_filter.rstrip("s") in crop_lower
            or crop_lower.rstrip("s") in normalized_filter
        ):
            codes.append(code)
    return codes


def best_crop_keyword_match(text: str, crop_candidates: Iterable[str]) -> str:
    normalized_query = f" {normalize_free_text(text)} "
    best_match = ""
    best_length = 0
    for crop_name in crop_candidates:
        canonical = canonicalize_crop_name(crop_name)
        for variant in crop_name_variants(crop_name):
            if f" {variant} " in normalized_query and len(variant) > best_length:
                best_match = canonical
                best_length = len(variant)
    return best_match
