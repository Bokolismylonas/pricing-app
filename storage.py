import json
import uuid
from datetime import datetime
from pathlib import Path


def _read_json(file_path: Path):
    if not file_path.exists():
        return []

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_json(file_path: Path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_comparisons(file_path: Path):
    data = _read_json(file_path)
    return sorted(
        data,
        key=lambda x: x.get("updated_at", x.get("created_at", "")),
        reverse=True,
    )


def save_new_comparison(
    file_path: Path,
    owner_sub: str,
    owner_email: str,
    name: str,
    companies: list,
    source_files: dict,
    state: dict,
):
    data = _read_json(file_path)

    comparison_id = str(uuid.uuid4())
    now_str = datetime.utcnow().isoformat()

    record = {
        "id": comparison_id,
        "owner_sub": owner_sub,
        "owner_email": owner_email,
        "name": name,
        "companies": companies,
        "source_files": source_files,
        "state": state,
        "created_at": now_str,
        "updated_at": now_str,
    }

    data.append(record)
    _write_json(file_path, data)
    return comparison_id


def update_comparison(
    file_path: Path,
    comparison_id: str,
    owner_sub: str,
    owner_email: str,
    name: str,
    companies: list,
    source_files: dict,
    state: dict,
):
    data = _read_json(file_path)
    now_str = datetime.utcnow().isoformat()

    for row in data:
        if row.get("id") == comparison_id:
            row["owner_sub"] = owner_sub
            row["owner_email"] = owner_email
            row["name"] = name
            row["companies"] = companies
            row["source_files"] = source_files
            row["state"] = state
            row["updated_at"] = now_str
            _write_json(file_path, data)
            return True

    return False


def get_comparison(file_path: Path, comparison_id: str):
    data = _read_json(file_path)
    for row in data:
        if row.get("id") == comparison_id:
            return row
    return None


def delete_comparison(file_path: Path, comparison_id: str):
    data = _read_json(file_path)
    new_data = [r for r in data if r.get("id") != comparison_id]
    _write_json(file_path, new_data)
    return len(data) != len(new_data)


def build_display_label(record: dict):
    name = record.get("name", "Untitled Comparison")
    companies = ", ".join(record.get("companies", []))
    updated_at = record.get("updated_at", "")[:16].replace("T", " ")
    return f"{name} | {companies} | {updated_at}"