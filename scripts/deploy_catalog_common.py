from pathlib import PurePath
from typing import Any


TABLE_COLUMNS = {
    "categories": ("id", "name", "slug"),
    "products": (
        "id",
        "category_id",
        "name",
        "slug",
        "description",
        "price",
        "stock",
        "image",
        "is_featured",
        "created_at",
        "short_description",
        "long_description",
        "leather_type",
        "hardware",
        "lining",
        "dimensions",
        "weight",
        "made_in",
        "warranty",
        "care",
        "is_bestseller",
        "is_active",
    ),
    "product_images": ("id", "product_id", "image", "sort_order"),
    "home_banners": (
        "id",
        "banner_group",
        "image",
        "title",
        "button_text",
        "link",
        "sort_order",
        "is_active",
        "eyebrow",
        "description",
    ),
}


def validate_asset_name(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or PurePath(name).name != name
    ):
        raise ValueError("Invalid catalog image filename.")
    return name


def referenced_assets(tables: dict[str, Any]) -> set[str]:
    names = set()
    for table in ("products", "product_images", "home_banners"):
        for row in tables[table]:
            if row["image"]:
                names.add(validate_asset_name(row["image"]))
    return names


def validate_tables(tables: Any) -> None:
    if not isinstance(tables, dict) or set(tables) != set(TABLE_COLUMNS):
        raise ValueError("Snapshot must contain only the supported catalog tables.")

    if not tables.get("categories") or not tables.get("products"):
        raise ValueError("Catalog snapshot must include categories and products.")

    for table, columns in TABLE_COLUMNS.items():
        rows = tables[table]
        if not isinstance(rows, list):
            raise ValueError(f"Invalid rows for {table}.")

        ids = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError(f"Invalid columns in {table} row.")
            if type(row["id"]) is not int or row["id"] < 1:
                raise ValueError(f"Invalid ID in {table}.")
            if row["id"] in ids:
                raise ValueError(f"Duplicate ID in {table}.")
            ids.add(row["id"])

    for row in tables["categories"]:
        if not isinstance(row["name"], str) or not row["name"]:
            raise ValueError("Invalid category name.")
        if not isinstance(row["slug"], str) or not row["slug"]:
            raise ValueError("Invalid category slug.")
    for row in tables["products"]:
        if not isinstance(row["slug"], str) or not row["slug"]:
            raise ValueError("Invalid product slug.")
        if row["category_id"] is not None and type(row["category_id"]) is not int:
            raise ValueError(f"Invalid category ID for product {row['id']}.")
    for row in tables["product_images"]:
        if type(row["product_id"]) is not int:
            raise ValueError(f"Invalid product ID for gallery image {row['id']}.")

    for table in ("categories", "products"):
        slugs = [row["slug"] for row in tables[table]]
        if len(slugs) != len(set(slugs)):
            raise ValueError(f"Duplicate slug in {table}.")

    for table in ("products", "product_images", "home_banners"):
        for row in tables[table]:
            if row["image"] is not None and not isinstance(row["image"], str):
                raise ValueError(f"Invalid image filename in {table}.")

    category_ids = {row["id"] for row in tables["categories"]}
    product_ids = {row["id"] for row in tables["products"]}
    for row in tables["products"]:
        if row["category_id"] is not None and row["category_id"] not in category_ids:
            raise ValueError(f"Product {row['id']} refers to a missing category.")
    for row in tables["product_images"]:
        if row["product_id"] not in product_ids:
            raise ValueError(f"Gallery image {row['id']} refers to a missing product.")

    referenced_assets(tables)
