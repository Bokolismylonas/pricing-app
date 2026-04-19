
"""
central_engine.py

Clean rebuild of the matching engine.
No dependency on previous hybrid scoring logic.

Core ideas:
1) Register pairwise user choices on save.
2) Re-evaluate every N saved events.
3) Runtime:
   - central table lookup and STOP
   - otherwise simple family-specific fallback
4) Restrictions apply only during re-evaluation/quarantine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from pathlib import Path
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------
# Normalization / key helpers
# ---------------------------

BOARD_THICKNESS_CANONICAL = [6.0, 8.0, 9.5, 10.0, 12.5, 13.0, 15.0, 18.0, 20.0, 25.0]


COLOR_VARIANT_TERMS = [
    "λευκο", "λευκό", "γκρι", "γκριζ", "ροζ", "μπλε", "πρασινο", "πράσινο", "κοκκινο", "κόκκινο",
    "μαυρο", "μαύρο", "διαφανο", "διάφανο", "κεραμιδι", "κεραμιδί", "μπεζ", "καφε", "καφέ",
    "yellow", "red", "green", "blue", "grey", "gray", "white", "black", "beige", "pink", "transparent",
]

GENERIC_NONCRITICAL_VARIANT_TERMS = [
    "υγρο", "υγρό", "σκονη", "σκόνη", "paste", "παστα", "πάστα", "liquid", "powder",
]

PACKAGE_CONTAINER_TERMS = [
    "δοχειο", "δοχείο", "βαρελι", "βαρέλι", "σακι", "σακί", "φυσιγγ", "cartidge", "cartridge",
    "bucket", "pail", "tin", "can", "bottle", "bag", "drum", "pack", "κουβας", "κουβάς",
]


def extract_package_signature(product_text: str = "", category_text: str = "", mm_text: str = "") -> str:
    text = normalize_text(f"{product_text} {category_text} {mm_text}")
    if not text:
        return ""

    qty = ""
    unit = ""
    m = re.search(r'(?<!\d)(\d+(?:\.\d+)?)\s*(kg|gr|g|lt|l|ml|κιλ(?:α|ό)?|κιλο|λιτρ(?:α|ο)?)\b', text)
    if m:
        qty = m.group(1)
        unit = m.group(2)

    container = ""
    for term in PACKAGE_CONTAINER_TERMS:
        if term in text:
            container = normalize_text(term)
            break

    parts = []
    if container:
        parts.append(container)
    if qty and unit:
        parts.append(f"{qty}{unit}")
    elif qty:
        parts.append(qty)
    return " ".join(parts).strip()


def strip_generic_variant_descriptors(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    for term in COLOR_VARIANT_TERMS + GENERIC_NONCRITICAL_VARIANT_TERMS:
        text = re.sub(rf'(?<!\w){re.escape(normalize_text(term))}(?!\w)', ' ', text)
    text = re.sub(r'\b(?:ral\s*\d{3,4})\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' -,_/')
    return text


def generic_canonical_core(product_text: str = "", category_text: str = "", mm_text: str = "") -> str:
    text = normalize_text(product_text)
    package_sig = extract_package_signature(product_text, category_text, mm_text)
    if package_sig:
        for token in package_sig.split():
            text = re.sub(rf'(?<!\w){re.escape(token)}(?!\w)', ' ', text)
    # remove common package container words from the core once packaging has been captured separately
    for term in PACKAGE_CONTAINER_TERMS:
        text = re.sub(rf'(?<!\w){re.escape(normalize_text(term))}(?!\w)', ' ', text)
    text = strip_generic_variant_descriptors(text)
    text = extract_core_product_name(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return normalize_text(text)


def normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(",", ".")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_mm_unit(mm_text: str) -> str:
    t = normalize_text(mm_text)
    if not t:
        return ""
    if t in {"m2", "m²", "sqm", "sq m", "τετρ μετρο", "τετραγωνικο μετρο"}:
        return "m2"
    if t in {"m", "meter", "metre", "μετρο", "μέτρο"}:
        return "m"
    if t in {"tmx", "temaxio", "temachio", "temaxia", "temachia", "τεμ", "τεμ.", "τεμαχιο", "τεμαχια", "piece", "pieces", "pc", "pcs"}:
        return "piece"
    return t


def text_similarity(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa = set(a.split())
    sb = set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def extract_match_mm(text: str) -> Optional[float]:
    text = normalize_text(text)

    m = re.search(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*mm\b", text)
    if m:
        return float(m.group(1))

    m = re.search(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*[x×]\s*\d{3,4}\s*[x×]\s*\d{3,4}", text)
    if m:
        return float(m.group(1))

    m = re.search(r"(?<!\d)(9[05]|10[05]|12[05]|13[05]|15[05]|18[05]|20[05]|25[05])(?!(?:\d|\s*[x×]))", text)
    if m:
        return float(m.group(1)) / 10.0

    return None


def normalized_board_thickness_key(product_text: str = "", mm_text: str = "") -> str:
    t = extract_match_mm(f"{product_text} {mm_text}")
    if t is None:
        return ""
    for target in BOARD_THICKNESS_CANONICAL:
        if abs(float(t) - target) <= 0.15:
            return f"{target:.1f}"
    return f"{float(t):.1f}"


def infer_product_family(product_text: str, category_text: str = "", mm_text: str = "") -> str:
    text = normalize_text(f"{product_text} {category_text}")
    mm_norm = normalize_mm_unit(mm_text)

    board_tokens = ["γυψο", "γυψοσαν", "gypsum", "plasterboard", "drywall", "habito", "vidiwall", "massivbauplatte", "aquapanel"]
    profile_tokens = ["profil", "profile", "προφιλ", "ορθοστατ", "στρωτηρ", "uw", "cw", "ud", "cd", "ua"]
    waterproof_tokens = ["aquamat", "sikaelastic", "mapelastic", "στεγαν", "waterproof"]
    adhesive_tokens = ["adhes", "glue", "κολλα", "tilefix", "fix", "τσιμεντοκολλα"]
    insulation_tokens = ["insulation", "μονω", "xps", "eps", "πετροβαμβ", "ορυκτοβαμβ"]
    accessory_tokens = ["ντιζ", "anker", "anchor", "βιδ", "screw", "washer", "γωνιοκρανο", "tape", "joint"]

    def has_any(tokens):
        return any(tok in text for tok in tokens)

    if has_any(profile_tokens):
        return "profile"
    if has_any(accessory_tokens):
        return "accessory"
    if has_any(board_tokens):
        return "board"
    if has_any(waterproof_tokens):
        return "waterproofing"
    if has_any(adhesive_tokens):
        return "adhesive"
    if has_any(insulation_tokens):
        return "insulation"

    if mm_norm == "m":
        return "profile"
    if mm_norm == "m2":
        return "board"

    return "unknown"


def infer_board_type(product_text: str, category_text: str = "") -> str:
    text = normalize_text(f"{product_text} {category_text}")

    is_fire = any(tok in text for tok in ["flam", "fire", "πυραντ", " df ", " dfh", "rf", "type f", "f1", "smart f"])
    is_moisture = any(tok in text for tok in ["hydro", "h2", "ανθυγρ", "moist", "aqua", "smart h"])
    is_acoustic = any(tok in text for tok in ["acoustic", "sound", "phon", "silent", "ηχο"])

    tags = []
    if is_fire:
        tags.append("fire")
    if is_moisture:
        tags.append("moisture")
    if is_acoustic:
        tags.append("acoustic")

    return "+".join(sorted(tags)) if tags else "standard"


def strip_board_sheet_dimensions_keep_thickness(text: str) -> str:
    text = str(text or "").replace(",", ".")
    text = re.sub(r'(?<!\d)(\d{1,2}(?:\.\d+)?)\s*[x×]\s*\d{3,4}\s*[x×]\s*\d{3,4}\s*mm\b', r'\1 mm ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<!\d)(\d{1,2}(?:\.\d+)?)\s*[x×]\s*\d{3,4}\s*[x×]\s*\d{3,4}\b', r'\1 mm ', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d{3,4}\s*[x×]\s*\d{3,4}\s*mm\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d{3,4}\s*[x×]\s*\d{3,4}\b', ' ', text, flags=re.IGNORECASE)
    # Boards: ignore trailing sheet length whether written as 2500/2800/3000 or 2.5m/2,8m etc.
    text = re.sub(r'(?<![\dx×])[-–—\s]*\b(2000|2400|2500|2600|2700|2800|3000|3200|3600)\s*mm\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<![\dx×])[-–—\s]*\b(2000|2400|2500|2600|2700|2800|3000|3200|3600)\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<![\dx×])[-–—\s]*\b(2(?:\.0|\.4|\.5|\.6|\.7|\.8)?|3(?:\.0|\.2|\.6)?)\s*m\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' -_')


def extract_core_product_name(text: str) -> str:
    text = str(text or "").replace(",", ".")
    text = re.sub(r"\b(?:mm|m2|m²|kg|gr|g|lt|l|ml|cm|tmx|τεμ|τεμ\.|pcs|pc)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_profile_length_keep_width(text: str) -> str:
    text = str(text or "").replace(",", ".")
    text = re.sub(r'(?<![x×])\b(2500|2700|2800|3000|3500|3600|3700|3800|4000|4500|6000)\s*mm\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<![x×])\b(2500|2700|2800|3000|3500|3600|3700|3800|4000|4500|6000)\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<!\d)(2\.5|2\.7|2\.8|3(?:\.0|\.5|\.6|\.7|\.8)?|4(?:\.0|\.5)?|6(?:\.0)?)\s*m\b', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def board_canonical_core(product_text: str = "", category_text: str = "", mm_text: str = "") -> str:
    text = strip_board_sheet_dimensions_keep_thickness(product_text)
    text = extract_core_product_name(text)
    text = normalize_text(text)

    thickness_key = normalized_board_thickness_key(product_text, mm_text)
    if thickness_key:
        variants = {thickness_key, thickness_key.replace(".", ","), thickness_key.replace(".", "")}
        for tv in variants:
            text = re.sub(rf'(?<!\d){re.escape(tv)}(?!\d)', ' ', text)

    text = re.sub(r'\bmm\b', ' ', text)
    text = re.sub(r'\b(?:1200|1250|600|2000|2400|2500|2600|2800|3000)\b', ' ', text)
    text = re.sub(r'\b(?:ak|hrak|edge|edges|ακρα)\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    aliases = [
        ("nida hydroflam", "hydroflam"),
        ("hydroflam plus", "hydroflam"),
        ("nida hydro plus", "hydro plus"),
        ("nida smart h", "smart h"),
        ("nida smart f", "smart f"),
        ("nida flam plus", "flam"),
        ("nida flam", "flam"),
        ("γυψοσανιδα ανθυγροπυραντοχη", "dfh2"),
        ("γυψοσανιδα πυραντοχη", "df"),
        ("γυψοσανιδες ανθυγροπυραντοχες", "dfh2"),
        ("γυψοσανιδες ανθυγρες", "h2"),
        ("γυψοσανιδες standard", "standard"),
    ]
    for a, b in aliases:
        text = text.replace(a, b)

    text = re.sub(r'\s+', ' ', text).strip()
    return text


def simple_profile_subtype(product_text: str = "", category_text: str = "") -> str:
    text = normalize_text(f"{product_text} {category_text}")
    for subtype in ["uw", "cw", "ud", "cd", "ua"]:
        if re.search(rf'\b{subtype}\b', text) or re.search(rf'\b{subtype}\d+', text):
            return subtype
    if "ορθοστατ" in text or "stud" in text:
        return "stud"
    if "στρωτηρ" in text or "οδηγ" in text or "track" in text:
        return "track"
    if "γωνια" in text or "corner" in text or "γωνιοκρανο" in text:
        return "corner"
    return ""


def simple_profile_width(product_text: str = "", mm_text: str = "") -> str:
    text = normalize_text(f"{product_text} {mm_text}")
    m = re.search(r'\b(?:uw|cw|ud|cd|ua)?\s*(28|48|50|60|70|75|90|100|125|150)\b', text)
    if m:
        return m.group(1)
    m = re.search(r'\b(?:uw|cw|ud|cd|ua)(28|48|50|60|70|75|90|100|125|150)\b', text)
    return m.group(1) if m else ""


def simple_functional_tag(product_text: str = "", category_text: str = "", mm_text: str = "") -> str:
    family = infer_product_family(product_text, category_text, mm_text)
    if family == "board":
        return infer_board_type(product_text, category_text)
    text = normalize_text(f"{product_text} {category_text}")
    tags = []
    if any(tok in text for tok in ["hydro", "h2", "ανθυγρ", "moist", "aqua"]):
        tags.append("moisture")
    if any(tok in text for tok in ["flam", "fire", "πυραντ", " df ", " dfh", "rf", "type f", "smart f"]):
        tags.append("fire")
    if any(tok in text for tok in ["acoustic", "sound", "phon", "silent", "ηχο"]):
        tags.append("acoustic")
    return "+".join(sorted(tags))


def make_choice_key(product_text: str, category_text: str = "", mm_text: str = "") -> str:
    family = infer_product_family(product_text, category_text, mm_text)
    unit = normalize_mm_unit(mm_text)

    if family == "board":
        board_type = infer_board_type(product_text, category_text)
        thickness = normalized_board_thickness_key(product_text, mm_text)
        core = board_canonical_core(product_text, category_text, mm_text)
        return " | ".join([p for p in [family, board_type, thickness, core, unit] if p])

    if family == "profile":
        subtype = simple_profile_subtype(product_text, category_text)
        width = simple_profile_width(product_text, mm_text)
        core = normalize_text(extract_core_product_name(strip_profile_length_keep_width(product_text)))
        core = re.sub(r'\b(?:mm|m)\b', ' ', core).strip()
        core = re.sub(r'\s+', ' ', core).strip()
        return " | ".join([p for p in [family, subtype, width, unit, core] if p])

    func = simple_functional_tag(product_text, category_text, mm_text)
    package = extract_package_signature(product_text, category_text, mm_text)
    core = generic_canonical_core(product_text, category_text, mm_text)
    return " | ".join([p for p in [family, func, unit, package, core] if p])


def choice_key_from_row(row: Dict[str, Any]) -> str:
    return make_choice_key(
        str(row.get("Product", "") or ""),
        str(row.get("Category", "") or ""),
        str(row.get("MM", "") or ""),
    )


def parse_choice_key(choice_key: str) -> Dict[str, str]:
    parts = [p.strip() for p in str(choice_key or "").split("|")]
    family = parts[0] if len(parts) >= 1 else ""
    out = {"family": family, "raw": str(choice_key or ""), "parts_count": str(len(parts))}
    if family == "board":
        out["type"] = parts[1] if len(parts) >= 2 else ""
        out["thickness"] = parts[2] if len(parts) >= 3 else ""
        out["core"] = parts[3] if len(parts) >= 4 else ""
        out["unit"] = parts[4] if len(parts) >= 5 else ""
    elif family == "profile":
        out["subtype"] = parts[1] if len(parts) >= 2 else ""
        out["width"] = parts[2] if len(parts) >= 3 else ""
        out["unit"] = parts[3] if len(parts) >= 4 else ""
        out["core"] = parts[4] if len(parts) >= 5 else ""
    else:
        out["functional"] = parts[1] if len(parts) >= 2 else ""
        out["unit"] = parts[2] if len(parts) >= 3 else ""
        out["package"] = parts[3] if len(parts) >= 4 else ""
        out["core"] = parts[4] if len(parts) >= 5 else ""
    return out


# ------------------
# Table data engine
# ------------------

@dataclass
class CentralMatchEngine:
    table_path: Path
    reeval_threshold: int = 10

    def load(self) -> Dict[str, Any]:
        default = {
            "register": {},
            "stable": {},
            "quarantine": {},
            "seed": {},
            "meta": {
                "version": 3,
                "pair_mode": "symmetric_all_pairs",
                "reeval_threshold": self.reeval_threshold,
                "total_saved_events": 0,
                "last_reeval_at_saved_event": 0,
            },
        }
        if not self.table_path.exists():
            return default
        try:
            data = json.loads(self.table_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("register", {})
                data.setdefault("stable", {})
                data.setdefault("quarantine", {})
                data.setdefault("seed", {})
                data.setdefault("meta", {})
                data["meta"].setdefault("version", 3)
                data["meta"].setdefault("pair_mode", "symmetric_all_pairs")
                data["meta"].setdefault("has_seed_layer", True)
                data["meta"].setdefault("reeval_threshold", self.reeval_threshold)
                data["meta"].setdefault("total_saved_events", 0)
                data["meta"].setdefault("last_reeval_at_saved_event", 0)
                return data
        except Exception:
            pass
        return default

    def save(self, data: Dict[str, Any]) -> None:
        self.table_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_pair(
        self,
        data: Dict[str, Any],
        source_row: Dict[str, Any],
        target_company: str,
        target_row: Dict[str, Any],
        comparison_id: str = "",
        source_company: str = "",
    ) -> None:
        source_key = choice_key_from_row(source_row)
        target_key = choice_key_from_row(target_row)
        company_key = str(target_company or "").strip().upper()
        if not source_key or not target_key or not company_key:
            return

        bucket = data.setdefault("register", {}).setdefault(source_key, {}).setdefault(company_key, {}).setdefault(
            target_key,
            {"hits": 0, "last_seen": "", "examples": []},
        )
        if source_company:
            bucket["source_company"] = str(source_company or "").strip().upper()
        bucket["target_company"] = company_key
        bucket["source_product"] = str(source_row.get("Product", "") or bucket.get("source_product", "") or "")
        bucket["target_product"] = str(target_row.get("Product", "") or bucket.get("target_product", "") or "")
        bucket["hits"] = int(bucket.get("hits", 0)) + 1
        bucket["last_seen"] = datetime.now().isoformat(timespec="seconds")
        examples = bucket.setdefault("examples", [])
        if len(examples) < 5:
            examples.append(
                {
                    "source_product": str(source_row.get("Product", "") or ""),
                    "target_product": str(target_row.get("Product", "") or ""),
                    "comparison_id": comparison_id,
                }
            )

    def register_row_choices(
        self,
        data: Dict[str, Any],
        row_choices: Iterable[Tuple[str, Dict[str, Any]]],
        comparison_id: str = "",
    ) -> None:
        row_choices = list(row_choices)
        seen_pairs = set()
        for source_company, source_row in row_choices:
            for target_company, target_row in row_choices:
                if source_company == target_company:
                    continue
                source_key = choice_key_from_row(source_row)
                target_key = choice_key_from_row(target_row)
                pair_sig = (str(source_company), source_key, str(target_company), target_key)
                if pair_sig in seen_pairs:
                    continue
                seen_pairs.add(pair_sig)
                self.register_pair(
                    data,
                    source_row,
                    target_company,
                    target_row,
                    comparison_id=comparison_id,
                    source_company=source_company,
                )

    def register_seed_pair(
        self,
        data: Dict[str, Any],
        source_company: str,
        source_row: Dict[str, Any],
        target_company: str,
        target_row: Dict[str, Any],
        confidence: str = "high",
        group_id: str = "",
        notes: str = "",
    ) -> None:
        source_key = choice_key_from_row(source_row)
        target_key = choice_key_from_row(target_row)
        company_key = str(target_company or "").strip().upper()
        source_company_key = str(source_company or "").strip().upper()
        if not source_key or not target_key or not company_key or not source_company_key:
            return

        bucket = data.setdefault("seed", {}).setdefault(source_key, {}).setdefault(company_key, {}).setdefault(
            target_key,
            {"hits": 0, "confidence": "high", "examples": []},
        )
        bucket["source_company"] = source_company_key
        bucket["target_company"] = company_key
        bucket["source_product"] = str(source_row.get("Product", "") or bucket.get("source_product", "") or "")
        bucket["target_product"] = str(target_row.get("Product", "") or bucket.get("target_product", "") or "")
        bucket["group_id"] = str(group_id or bucket.get("group_id", "") or "")
        bucket["notes"] = str(notes or bucket.get("notes", "") or "")
        bucket["confidence"] = str(confidence or bucket.get("confidence", "high") or "high").strip().lower() or "high"
        bucket["hits"] = max(int(bucket.get("hits", 0) or 0), 100)
        examples = bucket.setdefault("examples", [])
        if not examples:
            examples.append({
                "source_product": str(source_row.get("Product", "") or ""),
                "target_product": str(target_row.get("Product", "") or ""),
                "group_id": str(group_id or ""),
            })

    def import_seed_rows(self, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        data = self.load()
        data["seed"] = {}

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            group_id = str(raw.get("group_id", "") or "").strip()
            company = str(raw.get("company", "") or "").strip().upper()
            product_name = str(raw.get("product_name", "") or "").strip()
            if not group_id or not company or not product_name:
                continue
            grouped.setdefault(group_id, []).append({
                "group_id": group_id,
                "company": company,
                "product_name": product_name,
                "confidence": str(raw.get("confidence", "high") or "high").strip().lower() or "high",
                "notes": str(raw.get("notes", "") or "").strip(),
                "row": {
                    "Product": product_name,
                    "Category": str(raw.get("category", "") or raw.get("subcategory", "") or "").strip(),
                    "MM": str(raw.get("mm", "") or "").strip(),
                },
            })

        for group_id, entries in grouped.items():
            if len(entries) < 2:
                continue
            for source in entries:
                for target in entries:
                    if source["company"] == target["company"]:
                        continue
                    self.register_seed_pair(
                        data,
                        source["company"],
                        source["row"],
                        target["company"],
                        target["row"],
                        confidence=source.get("confidence", "high"),
                        group_id=group_id,
                        notes=source.get("notes", ""),
                    )

        self.save(data)
        return data

    def restrictions_pass(self, source_key: str, target_key: str) -> Tuple[bool, str]:
        s = parse_choice_key(source_key)
        t = parse_choice_key(target_key)

        if s.get("family") != t.get("family"):
            return False, "family_mismatch"

        family = s.get("family")
        if family == "board":
            if s.get("type") != t.get("type"):
                return False, "board_type_mismatch"
            if s.get("thickness") != t.get("thickness"):
                return False, "board_thickness_mismatch"
            if s.get("unit") != t.get("unit"):
                return False, "unit_mismatch"
            return True, ""

        if family == "profile":
            if s.get("subtype") != t.get("subtype"):
                return False, "profile_subtype_mismatch"
            if s.get("width") != t.get("width"):
                return False, "profile_width_mismatch"
            if s.get("unit") != t.get("unit"):
                return False, "unit_mismatch"
            return True, ""

        if s.get("unit") and t.get("unit") and s.get("unit") != t.get("unit"):
            return False, "unit_mismatch"
        return True, ""

    def reevaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        stable = {}
        quarantine = {}

        for source_key, company_map in data.get("register", {}).items():
            if not isinstance(company_map, dict):
                continue

            for company_key, target_map in company_map.items():
                if not isinstance(target_map, dict) or not target_map:
                    continue

                valid = []
                for target_key, payload in target_map.items():
                    hits = int(payload.get("hits", 0)) if isinstance(payload, dict) else int(payload or 0)
                    ok, reason = self.restrictions_pass(source_key, target_key)
                    if ok:
                        valid.append((target_key, hits))
                    else:
                        quarantine.setdefault(source_key, {}).setdefault(company_key, {})[target_key] = {
                            "hits": hits,
                            "reason": reason,
                        }

                if not valid:
                    continue

                valid.sort(key=lambda x: x[1], reverse=True)
                total_hits = sum(h for _, h in valid)
                top_target, top_hits = valid[0]
                second_hits = valid[1][1] if len(valid) > 1 else 0

                threshold = int(data.get("meta", {}).get("reeval_threshold", self.reeval_threshold))
                if total_hits < threshold:
                    continue
                if top_hits < 2:
                    continue
                if second_hits > 0 and top_hits < second_hits * 1.35:
                    continue

                stable.setdefault(source_key, {})[company_key] = {
                    "target_key": top_target,
                    "hits": top_hits,
                    "confidence": "high" if top_hits >= max(3, second_hits + 1) else "medium",
                }

        data["stable"] = stable
        data["quarantine"] = quarantine
        data.setdefault("meta", {})["last_reeval_at_saved_event"] = int(data.get("meta", {}).get("total_saved_events", 0))
        return data

    def maybe_reevaluate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        total_events = int(data.get("meta", {}).get("total_saved_events", 0))
        last_reeval = int(data.get("meta", {}).get("last_reeval_at_saved_event", 0))
        threshold = int(data.get("meta", {}).get("reeval_threshold", self.reeval_threshold))
        if not data.get("stable") or (total_events - last_reeval) >= threshold:
            return self.reevaluate(data)
        return data

    def lookup(self, source_row: Dict[str, Any], target_company: str) -> Tuple[str, int]:
        data = self.load()
        source_key = choice_key_from_row(source_row)
        company_key = str(target_company or "").strip().upper()

        seed_bucket = data.get("seed", {}).get(source_key, {}).get(company_key, {})
        if isinstance(seed_bucket, dict) and seed_bucket:
            valid_seed = []
            for target_key, payload in seed_bucket.items():
                if not target_key or not isinstance(payload, dict):
                    continue
                valid_seed.append((str(target_key), int(payload.get("hits", 100) or 100)))
            if valid_seed:
                valid_seed.sort(key=lambda x: x[1], reverse=True)
                return valid_seed[0][0], valid_seed[0][1]

        entry = data.get("stable", {}).get(source_key, {}).get(company_key, {})
        if isinstance(entry, dict) and str(entry.get("target_key", "") or "").strip():
            return str(entry.get("target_key", "") or ""), int(entry.get("hits", 0))

        provisional = data.get("register", {}).get(source_key, {}).get(company_key, {})
        if isinstance(provisional, dict):
            valid = []
            for target_key, payload in provisional.items():
                try:
                    hits = int((payload or {}).get("hits", 0))
                except Exception:
                    hits = 0
                if target_key and hits > 0:
                    valid.append((str(target_key), hits))
            if valid:
                valid.sort(key=lambda x: x[1], reverse=True)
                top_target, top_hits = valid[0]
                second_hits = valid[1][1] if len(valid) > 1 else 0
                if top_hits >= 2 and (second_hits == 0 or top_hits >= second_hits):
                    return top_target, top_hits

        return "", 0


    def _display_product_from_key(self, choice_key: str) -> str:
        parsed = parse_choice_key(str(choice_key or ""))
        family = parsed.get("family", "")
        if family == "board":
            parts = [parsed.get("type", ""), parsed.get("thickness", "")]
            return " ".join([p for p in parts if p]).strip()
        if family == "profile":
            parts = [parsed.get("subtype", ""), parsed.get("width", "")]
            return " ".join([p for p in parts if p]).strip()
        parts = [parsed.get("functional", ""), parsed.get("core", "")]
        return " ".join([p for p in parts if p]).strip() or str(choice_key or "")

    def _display_labels_for_pair(
        self,
        data: Dict[str, Any],
        source_key: str,
        target_company: str,
        target_key: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, str]:
        source_company_value = ""
        source_product_value = ""
        target_product_value = ""

        if isinstance(payload, dict):
            source_company_value = str(payload.get("source_company", "") or "").strip().upper()
            source_product_value = str(payload.get("source_product", "") or "").strip()
            target_product_value = str(payload.get("target_product", "") or "").strip()
            examples = payload.get("examples", [])
            if isinstance(examples, list) and examples:
                first = examples[0] if isinstance(examples[0], dict) else {}
                source_product_value = source_product_value or str(first.get("source_product", "") or "").strip()
                target_product_value = target_product_value or str(first.get("target_product", "") or "").strip()

        register_payload = (
            data.get("register", {})
            .get(str(source_key), {})
            .get(str(target_company or "").strip().upper(), {})
            .get(str(target_key), {})
        )
        if isinstance(register_payload, dict):
            source_company_value = source_company_value or str(register_payload.get("source_company", "") or "").strip().upper()
            source_product_value = source_product_value or str(register_payload.get("source_product", "") or "").strip()
            target_product_value = target_product_value or str(register_payload.get("target_product", "") or "").strip()
            examples = register_payload.get("examples", [])
            if isinstance(examples, list) and examples:
                first = examples[0] if isinstance(examples[0], dict) else {}
                source_product_value = source_product_value or str(first.get("source_product", "") or "").strip()
                target_product_value = target_product_value or str(first.get("target_product", "") or "").strip()

        source_product_value = source_product_value or self._display_product_from_key(str(source_key))
        target_product_value = target_product_value or self._display_product_from_key(str(target_key))
        return source_company_value, source_product_value, target_product_value

    def export_rows(self) -> List[Dict[str, Any]]:
        data = self.load()
        rows: List[Dict[str, Any]] = []

        seed = data.get("seed", {}) if isinstance(data.get("seed", {}), dict) else {}
        stable = data.get("stable", {}) if isinstance(data.get("stable", {}), dict) else {}
        register = data.get("register", {}) if isinstance(data.get("register", {}), dict) else {}

        for source_key, company_map in seed.items():
            if not isinstance(company_map, dict):
                continue
            for target_company, target_map in company_map.items():
                if not isinstance(target_map, dict):
                    continue
                for target_key, payload in target_map.items():
                    if not isinstance(payload, dict):
                        continue
                    source_company_value, source_product_value, target_product_value = self._display_labels_for_pair(
                        data,
                        str(source_key),
                        str(target_company or "").strip().upper(),
                        str(target_key),
                        payload,
                    )
                    rows.append({
                        "source_company": source_company_value,
                        "source_product": source_product_value,
                        "target_company": str(target_company or "").strip().upper(),
                        "matched_product": target_product_value,
                        "hits": int(payload.get("hits", 100) or 100),
                        "confidence": str(payload.get("confidence", "high") or "high").strip().lower() or "high",
                        "table_source": "seed",
                        "source_key": str(source_key),
                        "target_key": str(target_key),
                    })

        for source_key, company_map in stable.items():
            if not isinstance(company_map, dict):
                continue
            for target_company, entry in company_map.items():
                if not isinstance(entry, dict):
                    continue
                target_key = str(entry.get("target_key", "") or "").strip()
                hits = int(entry.get("hits", 0) or 0)
                confidence = str(entry.get("confidence", "") or "").strip().lower()
                if not target_key:
                    continue
                source_company_value, source_product_value, target_product_value = self._display_labels_for_pair(
                    data,
                    str(source_key),
                    str(target_company or "").strip().upper(),
                    target_key,
                    data.get("register", {}).get(str(source_key), {}).get(str(target_company or "").strip().upper(), {}).get(target_key, {}),
                )
                rows.append({
                    "source_company": source_company_value,
                    "source_product": source_product_value,
                    "target_company": str(target_company or "").strip().upper(),
                    "matched_product": target_product_value,
                    "hits": hits,
                    "confidence": confidence or ("high" if hits >= 3 else "medium"),
                    "table_source": "stable",
                    "source_key": str(source_key),
                    "target_key": target_key,
                })

        stable_pairs = {(r["source_key"], r["target_company"], r["target_key"]) for r in rows}

        for source_key, company_map in register.items():
            if not isinstance(company_map, dict):
                continue
            for target_company, target_map in company_map.items():
                if not isinstance(target_map, dict):
                    continue
                for target_key, payload in target_map.items():
                    if (str(source_key), str(target_company or "").strip().upper(), str(target_key)) in stable_pairs:
                        continue
                    try:
                        hits = int((payload or {}).get("hits", 0))
                    except Exception:
                        hits = 0
                    if hits <= 0:
                        continue
                    source_company_value, source_product_value, target_product_value = self._display_labels_for_pair(
                        data,
                        str(source_key),
                        str(target_company or "").strip().upper(),
                        str(target_key),
                        payload if isinstance(payload, dict) else {},
                    )
                    confidence = "high" if hits >= 5 else ("medium" if hits >= 3 else "low")
                    rows.append({
                        "source_company": source_company_value,
                        "source_product": source_product_value,
                        "target_company": str(target_company or "").strip().upper(),
                        "matched_product": target_product_value,
                        "hits": hits,
                        "confidence": confidence,
                        "table_source": "register",
                        "source_key": str(source_key),
                        "target_key": str(target_key),
                    })

        rows.sort(key=lambda r: (-int(r.get("hits", 0) or 0), str(r.get("source_company", "")), str(r.get("target_company", "")), str(r.get("source_product", ""))))
        return rows


# ----------------
# Runtime matcher
# ----------------

def products_are_compatible(source_row: Dict[str, Any], target_row: Dict[str, Any]) -> bool:
    src_key = choice_key_from_row(source_row)
    tgt_key = choice_key_from_row(target_row)
    src = parse_choice_key(src_key)
    tgt = parse_choice_key(tgt_key)

    if src.get("family") != tgt.get("family"):
        return False

    if src.get("family") == "board":
        return src.get("type") == tgt.get("type") and src.get("thickness") == tgt.get("thickness") and src.get("unit") == tgt.get("unit")
    if src.get("family") == "profile":
        return src.get("subtype") == tgt.get("subtype") and src.get("width") == tgt.get("width") and src.get("unit") == tgt.get("unit")

    if src.get("unit") and tgt.get("unit") and src.get("unit") != tgt.get("unit"):
        return False
    return True


def simple_clean_fallback(source_row: Dict[str, Any], target_rows: Iterable[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    source_key = parse_choice_key(choice_key_from_row(source_row))
    family = source_key.get("family")
    candidates = []

    for row in target_rows:
        if not products_are_compatible(source_row, row):
            continue

        score = 0.0
        target_key = parse_choice_key(choice_key_from_row(row))
        if family == "board":
            score += text_similarity(source_key.get("core", ""), target_key.get("core", "")) * 10.0
        elif family == "profile":
            score += text_similarity(source_key.get("core", ""), target_key.get("core", "")) * 10.0
        else:
            score += text_similarity(source_key.get("core", ""), target_key.get("core", "")) * 10.0

        candidates.append((row, score))

    if not candidates:
        return None, 0.0

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0], candidates[0][1]


def suggest_product(
    engine: CentralMatchEngine,
    source_row: Dict[str, Any],
    target_company: str,
    target_rows: Iterable[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], float, str, str]:
    target_key, hits = engine.lookup(source_row, target_company)

    if target_key:
        confidence = "high" if hits >= 4 else "medium" if hits >= 2 else "low"
        for row in target_rows:
            if choice_key_from_row(row) == target_key:
                return row, float(hits), "table", confidence

    row, score = simple_clean_fallback(source_row, target_rows)
    if row is not None:
        confidence = "high" if score >= 9 else "medium" if score >= 6 else "low"
        return row, score, "fallback", confidence

    return None, 0.0, "none", ""
