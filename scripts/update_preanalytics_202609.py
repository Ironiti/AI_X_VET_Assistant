"""Apply the September lab changes to an existing Chroma store, without rebuilding it.

Run with the bot stopped: python scripts/update_preanalytics_202609.py --apply
The default run only reports changes. Existing records are saved before applying.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path


CHANGES = {
    "AN116": {"patient_preparation": "Специальной подготовки не требуется"},
    "AN239RAB": {"form_name": "Сопроводительное письмо от врача на бешенство", "form_link": ""},
    "AN239RABCT": {"form_name": "Сопроводительное письмо от врача на бешенство", "form_link": ""},
}
DELETE_CODE = "AN371КР"
PDF_NAME = "БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT"
for code in ("AN239RAB", "AN239RABCT"):
    CHANGES[code]["additional_information_name"] = PDF_NAME


def plan(collection):
    records = collection.get(
        where={"test_code": {"$in": [*CHANGES, DELETE_CODE]}},
        include=["metadatas", "documents", "embeddings"],
    )
    found = {m["test_code"] for m in records["metadatas"]}
    missing = set(CHANGES) - found
    if missing:
        raise ValueError(f"Required tests missing: {sorted(missing)}")
    updates, deleted = [], []
    for record_id, metadata in zip(records["ids"], records["metadatas"]):
        code = metadata["test_code"]
        if code == DELETE_CODE:
            deleted.append(record_id)
        elif any(metadata.get(key) != val for key, val in CHANGES[code].items()):
            updates.append((record_id, CHANGES[code]))
    return records, updates, deleted


def apply_changes(collection, backup_path):
    records, updates, deleted = plan(collection)
    if not updates and not deleted:
        return {"updated": 0, "removed": 0}
    snapshot = dict(records)
    if snapshot.get("embeddings") is not None:
        snapshot["embeddings"] = snapshot["embeddings"].tolist()
    backup_path = Path(backup_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with backup_path.open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False)
    # Metadata-only updates preserve the existing search vectors and descriptions.
    if updates:
        collection.update(ids=[r[0] for r in updates], metadatas=[r[1] for r in updates])
    if deleted:
        collection.delete(ids=deleted)
    _, remaining_updates, remaining_deleted = plan(collection)
    if remaining_updates or remaining_deleted:
        raise RuntimeError("The store did not retain all changes")
    return {"updated": len(updates), "removed": len(deleted), "backup": str(backup_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store = args.repo / "data/chroma_db"
    if not (store / "chroma.sqlite3").is_file():
        raise SystemExit(f"Existing local store not found: {store}")
    for filename in (PDF_NAME + ".pdf", CHANGES["AN239RAB"]["form_name"] + ".xlsx"):
        if not (args.repo / "data/documents" / filename).is_file():
            raise SystemExit(f"Required document missing: {filename}")
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path=str(store), settings=Settings(anonymized_telemetry=False))
    collection = client.get_collection("langchain", embedding_function=None)
    before = collection.count()
    _, updates, deleted = plan(collection)
    summary = {"repo": str(args.repo), "total_before": before,
               "would_update": len(updates), "would_remove": len(deleted)}
    if args.apply:
        backup = args.repo / "data/backups" / (
            "preanalytics_202609_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
        )
        summary.update(apply_changes(collection, backup))
        if collection.count() != before - len(deleted):
            raise RuntimeError("Unexpected change in total record count")
        summary["total_after"] = collection.count()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
