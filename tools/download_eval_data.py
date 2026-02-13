"""Download the top most-voted CSV datasets under 3MB from Kaggle.

Datasets are saved to tools/evals/data/<owner--dataset>/ with their CSV files
and a manifest.json describing the dataset.
No authentication required — uses Kaggle's public API endpoints.
"""

import csv
import io
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

import httpx

KAGGLE_API = "https://www.kaggle.com/api/v1"
EVALS_DATA_DIR = Path(__file__).resolve().parent / "evals" / "data"
MAX_SIZE_BYTES = 3 * 1024 * 1024  # 3 MB
TARGET_COUNT = 10
PAGE_SIZE = 20

MAX_RETRIES = 5
RETRY_BACKOFF = 5  # seconds


def api_get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """GET with retry on 429."""
    kwargs.setdefault("timeout", 30)
    resp: httpx.Response | None = None
    for attempt in range(MAX_RETRIES):
        resp = client.get(url, **kwargs)
        if resp.status_code == 429:
            wait = RETRY_BACKOFF * (attempt + 1)
            print(f" [rate limited, waiting {wait}s]", end="", flush=True)
            time.sleep(wait)
            continue
        return resp
    if resp is None:
        raise RuntimeError("MAX_RETRIES must be >= 1")
    return resp


def list_datasets(client: httpx.Client, page: int) -> list[dict]:
    """List CSV datasets sorted by votes, under 3MB."""
    resp = api_get(
        client,
        f"{KAGGLE_API}/datasets/list",
        params={
            "sortBy": "votes",
            "fileType": "csv",
            "maxSize": MAX_SIZE_BYTES,
            "page": page,
        },
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def download_and_extract(client: httpx.Client, ref: str, dest: Path) -> list[str]:
    """Download dataset zip, extract CSVs. Returns list of CSV filenames."""
    resp = api_get(
        client,
        f"{KAGGLE_API}/datasets/download/{ref}",
        follow_redirects=True,
        timeout=60,
    )
    if resp.status_code != 200:
        return []

    content = resp.content
    csv_files: list[tuple[str, bytes]] = []

    if content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if info.filename.lower().endswith(".csv"):
                        csv_files.append((Path(info.filename).name, zf.read(info)))
        except zipfile.BadZipFile:
            return []
    elif len(content) > 0:
        name = ref.split("/")[-1] + ".csv"
        csv_files.append((name, content))

    if not csv_files:
        return []

    dest.mkdir(parents=True, exist_ok=True)
    filenames = []
    for filename, data in csv_files:
        (dest / filename).write_bytes(data)
        filenames.append(filename)

    return filenames


def get_dataset_description(client: httpx.Client, ref: str) -> str:
    """Fetch the full 'About Dataset' description from the Kaggle view endpoint."""
    owner, name = ref.split("/", 1)
    resp = api_get(client, f"{KAGGLE_API}/datasets/view/{owner}/{name}")
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return data.get("description") or data.get("descriptionNullable") or ""


def get_csv_columns(filepath: Path) -> dict:
    """Read a CSV file and return column metadata: names, types, row count."""
    try:
        with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return {"columns": [], "rows": 0}

            # Sample rows to infer types
            sample_size = 100
            sample_rows = []
            row_count = 0
            for row in reader:
                row_count += 1
                if len(sample_rows) < sample_size:
                    sample_rows.append(row)

            columns = []
            for i, name in enumerate(headers):
                values = [r[i] for r in sample_rows if i < len(r) and r[i].strip()]
                col_type = _infer_type(values)
                columns.append({"name": name.strip(), "type": col_type})

            return {"columns": columns, "rows": row_count}
    except Exception:
        return {"columns": [], "rows": 0}


def _infer_type(values: list[str]) -> str:
    """Infer a simple type from sampled string values."""
    if not values:
        return "string"

    int_count = 0
    float_count = 0
    for v in values:
        v = v.strip()
        try:
            int(v)
            int_count += 1
            continue
        except ValueError:
            pass
        try:
            float(v)
            float_count += 1
        except ValueError:
            pass

    total = len(values)
    if int_count == total:
        return "integer"
    if (int_count + float_count) == total:
        return "float"
    return "string"


def write_folder_manifest(
    client: httpx.Client, dest: Path, ds: dict, csv_filenames: list[str]
):
    """Write a manifest.json inside the dataset folder with Kaggle metadata."""
    ref = ds.get("ref", "")
    csvs = [dest / f for f in csv_filenames]

    description = get_dataset_description(client, ref)

    files = []
    for f in sorted(csvs):
        if not f.exists():
            continue
        col_info = get_csv_columns(f)
        files.append(
            {
                "name": f.name,
                "bytes": f.stat().st_size,
                "rows": col_info["rows"],
                "columns": col_info["columns"],
            }
        )

    manifest = {
        "slug": ref,
        "title": ds.get("title", ""),
        "subtitle": ds.get("subtitle", ""),
        "description": description,
        "creator": ds.get("creatorName", ""),
        "license": ds.get("licenseName", ""),
        "kaggle_url": f"https://www.kaggle.com/datasets/{ref}",
        "votes": ds.get("voteCount", 0),
        "downloads": ds.get("downloadCount", 0),
        "views": ds.get("viewCount", 0),
        "usability_rating": ds.get("usabilityRating", 0),
        "total_bytes": ds.get("totalBytes", 0),
        "files": files,
    }

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def refresh_manifests(client: httpx.Client):
    """Regenerate manifest.json for all existing dataset folders."""
    if not EVALS_DATA_DIR.exists():
        print("No data directory found")
        return

    folders = sorted(d for d in EVALS_DATA_DIR.iterdir() if d.is_dir())
    print(f"Refreshing manifests for {len(folders)} datasets...\n")

    for dest in folders:
        ref = dest.name.replace("--", "/")
        csv_filenames = [f.name for f in dest.iterdir() if f.suffix == ".csv"]
        if not csv_filenames:
            continue

        print(f"  {ref} ... ", end="", flush=True)

        # Fetch dataset info from Kaggle API
        owner, name = ref.split("/", 1)
        resp = api_get(client, f"{KAGGLE_API}/datasets/view/{owner}/{name}")
        if resp.status_code != 200:
            print("SKIP (API error)")
            continue

        ds = resp.json()
        write_folder_manifest(client, dest, ds, csv_filenames)
        print(f"OK ({len(csv_filenames)} csv)")
        time.sleep(0.5)

    print("\nDone")


def main():
    if "--refresh-manifests" in sys.argv:
        with httpx.Client() as client:
            refresh_manifests(client)
        return

    EVALS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = {d.name for d in EVALS_DATA_DIR.iterdir() if d.is_dir()}
    collected = len(existing)

    if collected >= TARGET_COUNT:
        print(f"Already have {collected} datasets, nothing to do")
        return

    print(f"Target: {TARGET_COUNT} most-voted CSV datasets (< 3MB) from Kaggle")
    print(f"Have {collected}, need {TARGET_COUNT - collected} more...\n")

    page = 1
    max_pages = 50

    with httpx.Client() as client:
        while collected < TARGET_COUNT and page <= max_pages:
            datasets = list_datasets(client, page)
            if not datasets:
                print(f"No more datasets at page {page}")
                break

            for ds in datasets:
                if collected >= TARGET_COUNT:
                    break

                ref = ds.get("ref", "")
                votes = ds.get("voteCount", 0)
                size = ds.get("totalBytes", 0)
                if not ref:
                    continue

                folder_name = ref.replace("/", "--")
                if folder_name in existing:
                    continue

                dest = EVALS_DATA_DIR / folder_name
                print(
                    f"  [{collected + 1}/{TARGET_COUNT}] "
                    f"{ref} ({votes} votes, {size // 1024}KB) ... ",
                    end="",
                    flush=True,
                )

                csv_filenames = download_and_extract(client, ref, dest)

                if csv_filenames:
                    write_folder_manifest(client, dest, ds, csv_filenames)
                    print(f"OK ({len(csv_filenames)} csv)")
                    collected += 1
                else:
                    print("SKIP")
                    shutil.rmtree(dest, ignore_errors=True)

                time.sleep(0.5)

            page += 1

    print(f"\nDone: {collected} datasets in {EVALS_DATA_DIR}")


if __name__ == "__main__":
    main()
