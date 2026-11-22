#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from deploy_catalog_common import (
    TABLE_COLUMNS,
    referenced_assets,
    validate_asset_name,
    validate_tables,
)


def read_tables(database_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not database_path.is_file():
        raise ValueError(f"Local database not found: {database_path}")

    database_uri = database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(database_uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {}
        for table, columns in TABLE_COLUMNS.items():
            column_list = ", ".join(columns)
            rows = connection.execute(
                f"SELECT {column_list} FROM {table} ORDER BY id"
            ).fetchall()
            tables[table] = [dict(row) for row in rows]

    validate_tables(tables)
    if not tables["categories"] or not tables["products"]:
        raise ValueError("Local catalog is empty; refusing to export it.")
    return tables


def build_snapshot(
    project_dir: Path,
    database_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    tables = read_tables(database_path)
    source_uploads = project_dir / "static" / "uploads"
    names = referenced_assets(tables)
    if (source_uploads / "made-to-order.jpg").is_file():
        names.add("made-to-order.jpg")

    assets = {}
    asset_rows = []
    for name in sorted(names):
        source = source_uploads / name
        if not source.is_file():
            raise ValueError(f"Referenced image is missing: {source}")
        data = source.read_bytes()
        assets[name] = data
        asset_rows.append({
            "name": name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    manifest = {
        "format": 1,
        "tables": tables,
        "assets": asset_rows,
    }
    return manifest, assets


def write_snapshot(
    output_dir: Path,
    manifest: dict[str, Any],
    assets: dict[str, bytes],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "catalog.json"
    uploads_path = output_dir / "uploads"
    previous_names = set()
    had_manifest = manifest_path.exists()
    if had_manifest:
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(previous_manifest, dict) or not isinstance(
            previous_manifest.get("assets"), list
        ):
            raise ValueError("Existing deployment catalog snapshot is invalid.")
        for item in previous_manifest.get("assets", []):
            if not isinstance(item, dict) or "name" not in item:
                raise ValueError("Existing deployment image list is invalid.")
            previous_names.add(validate_asset_name(item["name"]))
    if uploads_path.is_symlink():
        raise ValueError("The deployment image folder must not be a symbolic link.")
    if uploads_path.exists():
        entries = list(uploads_path.iterdir())
        if any(not path.is_file() or path.is_symlink() for path in entries):
            raise ValueError("The deployment image folder contains a non-file entry.")
        actual_names = {path.name for path in entries}
        if had_manifest and actual_names - previous_names:
            raise ValueError(
                "The deployment image folder contains files not created "
                "by the catalog exporter."
            )
        if not had_manifest and actual_names != set(assets):
            raise ValueError(
                "The deployment image folder has no manifest and does not "
                "match the current catalog export."
            )

    with tempfile.TemporaryDirectory(
        prefix=".catalog-export-",
        dir=output_dir,
    ) as temporary:
        temporary_dir = Path(temporary)
        staged_manifest = temporary_dir / "catalog.json"
        staged_uploads = temporary_dir / "uploads"
        staged_uploads.mkdir()
        saved_files = temporary_dir / "saved-files"
        saved_files.mkdir()

        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        for name, data in assets.items():
            (staged_uploads / name).write_bytes(data)

        uploads_path.mkdir(exist_ok=True)
        changed_files = []
        old_manifest = temporary_dir / "old-catalog.json"
        manifest_backup = None
        manifest_installed = False
        try:
            for name in sorted(assets):
                target = uploads_path / name
                data = assets[name]
                if (
                    target.is_file()
                    and hashlib.sha256(target.read_bytes()).digest()
                    == hashlib.sha256(data).digest()
                ):
                    continue
                backup = None
                if target.exists():
                    backup = saved_files / name
                    shutil.copy2(target, backup)
                changed_files.append((target, backup))
                os.replace(staged_uploads / name, target)

            for name in sorted(previous_names - set(assets)):
                target = uploads_path / name
                if target.exists():
                    backup = saved_files / name
                    shutil.copy2(target, backup)
                    changed_files.append((target, backup))
                    target.unlink()

            if manifest_path.exists():
                shutil.copy2(manifest_path, old_manifest)
                manifest_backup = old_manifest
            os.replace(staged_manifest, manifest_path)
            manifest_installed = True
        except Exception:
            for target, backup in reversed(changed_files):
                if backup is None:
                    if target.exists():
                        target.unlink()
                else:
                    shutil.copy2(backup, target)
            if manifest_installed:
                if manifest_backup is not None:
                    shutil.copy2(manifest_backup, manifest_path)
                elif manifest_path.exists():
                    manifest_path.unlink()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export public catalog data without orders or customer records."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "instance"
        / "forge_and_hide.db",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "deployment",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    manifest, assets = build_snapshot(
        project_dir,
        args.database.resolve(),
        args.output.resolve(),
    )
    write_snapshot(args.output.resolve(), manifest, assets)
    counts = {
        table: len(manifest["tables"][table]) for table in TABLE_COLUMNS
    }
    print(f"Catalog snapshot ready: {counts}")
    print(f"Referenced images included: {len(assets)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
        print(f"Catalog export stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
