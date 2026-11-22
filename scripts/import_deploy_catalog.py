#!/usr/bin/env python3

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deploy_catalog_common import (
    TABLE_COLUMNS,
    referenced_assets,
    validate_asset_name,
    validate_tables,
)


PROTECTED_TABLES = ("orders", "order_items", "customers", "admins")


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_snapshot(
    snapshot_path: Path,
    assets_dir: Path,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        manifest = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Catalog snapshot is not valid JSON.") from error

    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"format", "tables", "assets"}
        or manifest["format"] != 1
        or not isinstance(manifest["assets"], list)
    ):
        fail("Unsupported catalog snapshot format.")

    tables = manifest["tables"]
    validate_tables(tables)

    asset_rows = {}
    for item in manifest["assets"]:
        if not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}:
            fail("Invalid asset entry in catalog snapshot.")
        name = validate_asset_name(item["name"])
        if name in asset_rows:
            fail(f"Duplicate image in snapshot: {name}")
        if type(item["size"]) is not int or item["size"] < 0:
            fail(f"Invalid image size in snapshot: {name}")
        if not isinstance(item["sha256"], str):
            fail(f"Invalid image hash in snapshot: {name}")
        asset_rows[name] = item

    expected_assets = referenced_assets(tables)
    if "made-to-order.jpg" in asset_rows:
        expected_assets.add("made-to-order.jpg")
    if set(asset_rows) != expected_assets:
        fail("Image list does not match the catalog snapshot.")
    if not assets_dir.is_dir():
        fail(f"Catalog image directory not found: {assets_dir}")

    entries = list(assets_dir.iterdir())
    if any(not path.is_file() or path.is_symlink() for path in entries):
        fail("Catalog image directory contains a non-file entry.")
    actual_files = {path.name for path in entries}
    if actual_files != set(asset_rows):
        fail("Catalog image directory contains missing or unexpected files.")

    assets = {}
    for name, item in asset_rows.items():
        data = (assets_dir / name).read_bytes()
        if len(data) != item["size"] or sha256(data) != item["sha256"]:
            fail(f"Catalog image verification failed: {name}")
        assets[name] = data

    return tables, assets


def check_schema(connection: sqlite3.Connection) -> None:
    for table, columns in TABLE_COLUMNS.items():
        actual = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if actual != set(columns):
            fail(f"Unexpected live database schema for {table}.")

    for table in PROTECTED_TABLES:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if exists is None:
            fail(f"Required protected table is missing: {table}.")


def protected_rows(connection: sqlite3.Connection) -> dict[str, list[tuple]]:
    return {
        table: [
            tuple(row)
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")
        ]
        for table in PROTECTED_TABLES
    }


def protected_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in PROTECTED_TABLES
    }


def check_unique_conflicts(
    connection: sqlite3.Connection,
    tables: dict[str, Any],
) -> None:
    unique_columns = {
        "categories": ("name", "slug"),
        "products": ("slug",),
    }
    for table, columns in unique_columns.items():
        for row in tables[table]:
            for column in columns:
                conflict = connection.execute(
                    f"SELECT id FROM {table} WHERE {column}=? AND id<>?",
                    (row[column], row["id"]),
                ).fetchone()
                if conflict is not None:
                    fail(
                        f"Unique {column} conflict in {table}; "
                        "no catalog data changed."
                    )


def make_backup(database_path: Path) -> Path:
    backup_dir = Path.home() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"forge-hide-before-catalog-sync-{stamp}.sqlite3"
    with closing(sqlite3.connect(database_path, timeout=30)) as source:
        with closing(sqlite3.connect(backup_path)) as destination:
            source.backup(destination)
    return backup_path


def copy_assets(
    project_dir: Path,
    assets: dict[str, bytes],
    backup_path: Path,
) -> list[tuple[Path, Path | None, Path]]:
    upload_dir = project_dir / "static" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    media_backup_dir = backup_path.with_suffix("")
    changed_assets = []

    try:
        for name, data in assets.items():
            target = upload_dir / name
            if target.is_symlink():
                fail(f"Refusing to overwrite a symbolic link: {target}")
            if target.is_file() and sha256(target.read_bytes()) == sha256(data):
                continue

            old_copy = None
            if target.exists():
                media_backup_dir.mkdir(parents=True, exist_ok=True)
                old_copy = media_backup_dir / name
                shutil.copy2(target, old_copy)

            temp_path = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            changed_assets.append((target, old_copy, temp_path))
            temp_path.write_bytes(data)
            temp_path.replace(target)
    except Exception:
        restore_assets(changed_assets)
        raise

    return changed_assets


def restore_assets(
    changed_assets: list[tuple[Path, Path | None, Path]],
) -> None:
    for target, old_copy, temp_path in reversed(changed_assets):
        if temp_path.exists():
            temp_path.unlink()
        if old_copy is None:
            if target.exists():
                target.unlink()
        else:
            shutil.copy2(old_copy, target)


def apply_snapshot(
    database_path: Path,
    project_dir: Path,
    tables: dict[str, Any],
    assets: dict[str, bytes],
) -> Path:
    backup_path = make_backup(database_path)
    changed_assets = []
    committed = False

    try:
        with closing(sqlite3.connect(database_path, timeout=30)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            check_schema(connection)
            check_unique_conflicts(connection, tables)

            connection.execute("BEGIN IMMEDIATE")
            before = protected_rows(connection)
            changed_assets = copy_assets(project_dir, assets, backup_path)

            for table in ("categories", "products"):
                columns = TABLE_COLUMNS[table]
                for row in tables[table]:
                    values = dict(row)
                    updates = ", ".join(
                        f"{column}=excluded.{column}"
                        for column in columns
                        if column != "id" and not (
                            table == "products" and column == "stock"
                        )
                    )
                    placeholders = ", ".join("?" for _ in columns)
                    connection.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) "
                        f"VALUES ({placeholders}) "
                        f"ON CONFLICT(id) DO UPDATE SET {updates}",
                        tuple(values[column] for column in columns),
                    )

            local_product_ids = [row["id"] for row in tables["products"]]
            placeholders = ", ".join("?" for _ in local_product_ids)
            connection.execute(
                f"UPDATE products SET is_active=0 "
                f"WHERE id NOT IN ({placeholders})",
                tuple(local_product_ids),
            )

            for table in ("product_images", "home_banners"):
                columns = TABLE_COLUMNS[table]
                connection.execute(f"DELETE FROM {table}")
                placeholders = ", ".join("?" for _ in columns)
                connection.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({placeholders})",
                    [
                        tuple(row[column] for column in columns)
                        for row in tables[table]
                    ],
                )

            if protected_rows(connection) != before:
                fail("Protected order/customer/admin data changed.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                fail("Foreign-key check failed; catalog update rolled back.")
            connection.commit()
            committed = True
    except Exception:
        if not committed:
            restore_assets(changed_assets)
        raise

    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely import catalog data while preserving live orders."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "deployment"
        / "catalog.json",
    )
    parser.add_argument(
        "--assets",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "deployment"
        / "uploads",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "instance"
        / "forge_and_hide.db",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    snapshot_path = args.snapshot.resolve()
    assets_dir = args.assets.resolve()
    database_path = args.database.resolve()
    project_dir = Path(__file__).resolve().parents[1]

    tables, assets = read_snapshot(snapshot_path, assets_dir)
    if not database_path.is_file():
        fail(f"Database not found: {database_path}")
    with closing(sqlite3.connect(database_path, timeout=30)) as connection:
        connection.row_factory = sqlite3.Row
        check_schema(connection)
        check_unique_conflicts(connection, tables)
        protected = protected_counts(connection)

    counts = {
        table: len(tables[table]) for table in TABLE_COLUMNS
    }
    print(f"Catalog rows to sync: {counts}")
    print(f"Verified image files: {len(assets)}")
    print(f"Protected live row counts: {protected}")
    if not args.apply:
        print("Dry run only; database and live images were not changed.")
        return 0

    backup_path = apply_snapshot(
        database_path,
        project_dir,
        tables,
        assets,
    )
    print(f"Catalog sync completed. Database backup: {backup_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
        print(f"Catalog sync stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
