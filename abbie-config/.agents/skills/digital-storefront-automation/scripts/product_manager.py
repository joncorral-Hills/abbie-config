#!/usr/bin/env python3
"""
product_manager.py — Digital Storefront Product Lifecycle Manager

Complete product file management: creation, packaging, mockup generation,
hashing, metadata tracking, Notion sync, and change detection.

Usage:
    python product_manager.py --create my-product --category "Printable Art"
    python product_manager.py --package my-product
    python product_manager.py --mockup my-product --template device
    python product_manager.py --list --status draft
    python product_manager.py --sync my-product
    python product_manager.py --check-updates
    python product_manager.py --test
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFilter = None
    ImageFont = None

logger = logging.getLogger(__name__)

PRODUCTS_DIR = Path(os.path.expanduser("~/digital-products/"))

METADATA_SCHEMA = {
    "slug": "",
    "display_name": "",
    "category": "",
    "status": "draft",
    "created_at": None,
    "updated_at": None,
    "price": None,
    "tags": [],
    "description": "",
    "file_hash": None,
    "package_path": None,
    "package_date": None,
    "etsy_listing_id": None,
    "notion_page_id": None,
    "mockup_paths": {},
    "deliverable_count": 0,
    "version": 1,
}

VALID_STATUSES = {"draft", "ready", "listed", "archived", "paused"}
VALID_TEMPLATES = {"default", "device", "lifestyle"}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp", ".gif"}


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(name: str) -> str:
    """Convert a display name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = slug.replace("&", "and").replace("@", "at")
    cleaned = []
    for ch in slug:
        if ch.isalnum() or ch in ("-", "_"):
            cleaned.append(ch)
        elif ch in (" ", "/", "\\", "."):
            cleaned.append("-")
    result = "".join(cleaned)
    while "--" in result:
        result = result.replace("--", "-")
    return result.strip("-")


class ProductManager:
    """Manages the full lifecycle of digital products on disk."""

    def __init__(self, products_dir: Path = PRODUCTS_DIR):
        self.products_dir = Path(products_dir)
        self.products_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def create_product(
        self, slug: str, category: str, display_name: str = ""
    ) -> Path:
        """
        Create a new product directory with standard structure and metadata.

        Args:
            slug: URL-safe identifier for the product.
            category: Product category (e.g. "Printable Art").
            display_name: Human-readable name. Derived from slug if empty.

        Returns:
            Path to the newly created product directory.

        Raises:
            FileExistsError: If a product with this slug already exists.
            ValueError: If slug is empty or invalid.
        """
        if not slug or not slug.strip():
            raise ValueError("Product slug cannot be empty")
        slug = _slugify(slug) if " " in slug else slug
        product_dir = self.products_dir / slug

        if product_dir.exists():
            raise FileExistsError(f"Product '{slug}' already exists at {product_dir}")

        # Build directory tree
        for subdir in ("source", "deliverables", "mockups"):
            (product_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Derive display name from slug if not provided
        if not display_name:
            display_name = slug.replace("-", " ").replace("_", " ").title()

        now = _now_iso()
        metadata = {
            **METADATA_SCHEMA,
            "slug": slug,
            "display_name": display_name,
            "category": category,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "tags": [],
            "description": "",
            "file_hash": None,
            "package_path": None,
            "package_date": None,
            "etsy_listing_id": None,
            "notion_page_id": None,
            "mockup_paths": {},
            "deliverable_count": 0,
            "version": 1,
        }

        meta_path = product_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        logger.info("Created product '%s' at %s", slug, product_dir)
        return product_dir

    def get_metadata(self, slug: str) -> Dict[str, Any]:
        """
        Read and return the metadata.json for a product.

        Raises:
            FileNotFoundError: If product or metadata file does not exist.
        """
        meta_path = self.products_dir / slug / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No metadata found for product '{slug}'")
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def update_metadata(self, slug: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge updates into a product's metadata.json and save.

        Automatically bumps `updated_at` and `version`.

        Returns:
            The updated metadata dict.
        """
        metadata = self.get_metadata(slug)

        # Prevent overwriting immutable fields
        protected = {"slug", "created_at"}
        for key in protected:
            updates.pop(key, None)

        metadata.update(updates)
        metadata["updated_at"] = _now_iso()
        metadata["version"] = metadata.get("version", 0) + 1

        meta_path = self.products_dir / slug / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        logger.info("Updated metadata for '%s' (v%d)", slug, metadata["version"])
        return metadata

    def list_products(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all products, optionally filtered by status.

        Args:
            status: If provided, only return products matching this status.

        Returns:
            List of metadata dicts for matching products.
        """
        if status and status not in VALID_STATUSES:
            logger.warning("Unknown status filter '%s'. Valid: %s", status, VALID_STATUSES)

        products = []
        if not self.products_dir.exists():
            return products

        for entry in sorted(self.products_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping '%s': %s", entry.name, exc)
                continue

            if status is None or meta.get("status") == status:
                products.append(meta)

        return products

    # ------------------------------------------------------------------
    # Packaging
    # ------------------------------------------------------------------

    def package_deliverables(self, slug: str) -> Path:
        """
        ZIP everything in the deliverables/ folder into <slug>.zip.

        Updates metadata with file_hash, package_path, package_date,
        and deliverable_count.

        Returns:
            Path to the created ZIP file.

        Raises:
            FileNotFoundError: If deliverables directory is empty or missing.
        """
        product_dir = self.products_dir / slug
        deliverables_dir = product_dir / "deliverables"

        if not deliverables_dir.exists():
            raise FileNotFoundError(f"No deliverables directory for '{slug}'")

        # Collect all files recursively
        files_to_zip = []
        for root, _dirs, files in os.walk(deliverables_dir):
            for fname in files:
                full_path = Path(root) / fname
                arc_name = full_path.relative_to(deliverables_dir)
                files_to_zip.append((full_path, str(arc_name)))

        if not files_to_zip:
            raise FileNotFoundError(f"No files found in deliverables/ for '{slug}'")

        zip_path = product_dir / f"{slug}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full_path, arc_name in sorted(files_to_zip):
                zf.write(full_path, arc_name)
                logger.debug("  Added: %s", arc_name)

        file_hash = self.compute_file_hash(slug)
        now = _now_iso()

        self.update_metadata(slug, {
            "file_hash": file_hash,
            "package_path": str(zip_path),
            "package_date": now,
            "deliverable_count": len(files_to_zip),
        })

        logger.info(
            "Packaged %d files into %s (SHA-256: %s)",
            len(files_to_zip), zip_path.name, file_hash[:16],
        )
        return zip_path

    def compute_file_hash(self, slug: str) -> str:
        """
        Compute SHA-256 hash of the deliverable ZIP file.

        Returns:
            Hex digest of the file hash.

        Raises:
            FileNotFoundError: If the ZIP file does not exist.
        """
        zip_path = self.products_dir / slug / f"{slug}.zip"
        if not zip_path.exists():
            raise FileNotFoundError(f"No package found at {zip_path}")

        sha256 = hashlib.sha256()
        with open(zip_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    # ------------------------------------------------------------------
    # Mockup Generation
    # ------------------------------------------------------------------

    def generate_mockup(self, slug: str, template: str = "default") -> Path:
        """
        Composite the first image in deliverables/ onto a mockup template.

        Templates:
            - 'default': White background (2000x2000), product centered with shadow.
            - 'device':  Tablet frame overlay (product shown on iPad-like frame).
            - 'lifestyle': Desk background with product at angle.

        Returns:
            Path to the saved mockup PNG.

        Raises:
            ImportError: If Pillow is not installed.
            FileNotFoundError: If no image deliverables found.
            ValueError: If template name is invalid.
        """
        if Image is None:
            raise ImportError(
                "Pillow is required for mockup generation. "
                "Install with: pip install Pillow"
            )

        if template not in VALID_TEMPLATES:
            raise ValueError(
                f"Invalid template '{template}'. Choose from: {VALID_TEMPLATES}"
            )

        deliverables_dir = self.products_dir / slug / "deliverables"
        source_image = self._find_first_image(deliverables_dir)
        if source_image is None:
            raise FileNotFoundError(
                f"No image files found in deliverables/ for '{slug}'"
            )

        product_img = Image.open(source_image).convert("RGBA")
        mockups_dir = self.products_dir / slug / "mockups"
        mockups_dir.mkdir(parents=True, exist_ok=True)

        if template == "default":
            mockup = self._mockup_default(product_img)
        elif template == "device":
            mockup = self._mockup_device(product_img)
        elif template == "lifestyle":
            mockup = self._mockup_lifestyle(product_img)
        else:
            raise ValueError(f"Unknown template: {template}")

        output_path = mockups_dir / f"{template}_mockup.png"
        mockup.save(str(output_path), "PNG", quality=95)

        # Update metadata with mockup path
        metadata = self.get_metadata(slug)
        mockup_paths = metadata.get("mockup_paths", {})
        mockup_paths[template] = str(output_path)
        self.update_metadata(slug, {"mockup_paths": mockup_paths})

        logger.info("Generated '%s' mockup at %s", template, output_path)
        return output_path

    def _find_first_image(self, directory: Path) -> Optional[Path]:
        """Find the first image file in a directory (sorted alphabetically)."""
        if not directory.exists():
            return None
        for entry in sorted(directory.iterdir()):
            if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
                return entry
        return None

    def _create_drop_shadow(
        self, image: "Image.Image", offset: tuple = (12, 12),
        shadow_color: tuple = (0, 0, 0, 80), blur_radius: int = 25,
        canvas_expand: int = 60,
    ) -> "Image.Image":
        """Create a drop shadow behind an RGBA image."""
        w, h = image.size
        canvas_w = w + canvas_expand * 2
        canvas_h = h + canvas_expand * 2

        # Shadow layer
        shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_rect = Image.new("RGBA", (w, h), shadow_color)

        # Use the alpha channel of the source as a mask for the shadow shape
        if image.mode == "RGBA":
            shadow_rect.putalpha(image.split()[3])

        shadow_x = canvas_expand + offset[0]
        shadow_y = canvas_expand + offset[1]
        shadow.paste(shadow_rect, (shadow_x, shadow_y))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Composite product on top of shadow
        product_x = canvas_expand
        product_y = canvas_expand
        shadow.paste(image, (product_x, product_y), image)

        return shadow

    def _mockup_default(self, product_img: "Image.Image") -> "Image.Image":
        """
        Default mockup: White background (2000x2000), product centered with
        a soft drop shadow.
        """
        canvas_size = (2000, 2000)
        canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 255))

        # Scale product to fit within 1400x1400 while preserving aspect ratio
        max_dim = 1400
        pw, ph = product_img.size
        scale = min(max_dim / pw, max_dim / ph, 1.0)
        new_w = int(pw * scale)
        new_h = int(ph * scale)
        resized = product_img.resize((new_w, new_h), Image.LANCZOS)

        # Add drop shadow
        with_shadow = self._create_drop_shadow(
            resized, offset=(15, 15), shadow_color=(0, 0, 0, 60),
            blur_radius=30, canvas_expand=80,
        )

        # Center on canvas
        sw, sh = with_shadow.size
        paste_x = (canvas_size[0] - sw) // 2
        paste_y = (canvas_size[1] - sh) // 2
        canvas.paste(with_shadow, (paste_x, paste_y), with_shadow)

        return canvas.convert("RGB")

    def _mockup_device(self, product_img: "Image.Image") -> "Image.Image":
        """
        Device mockup: iPad-like tablet frame with the product shown on screen.
        Programmatically draws a rounded-rectangle tablet body with bezel.
        """
        canvas_size = (2400, 1800)
        canvas = Image.new("RGBA", canvas_size, (245, 245, 247, 255))

        # Tablet dimensions
        tablet_w, tablet_h = 1600, 1200
        bezel = 50
        corner_radius = 40

        # Draw tablet body (dark frame)
        tablet_x = (canvas_size[0] - tablet_w) // 2
        tablet_y = (canvas_size[1] - tablet_h) // 2

        tablet_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(tablet_layer)

        # Outer body (rounded rectangle)
        draw.rounded_rectangle(
            [tablet_x, tablet_y, tablet_x + tablet_w, tablet_y + tablet_h],
            radius=corner_radius,
            fill=(44, 44, 46, 255),
        )

        # Inner screen area (slightly lighter background)
        screen_x = tablet_x + bezel
        screen_y = tablet_y + bezel
        screen_w = tablet_w - bezel * 2
        screen_h = tablet_h - bezel * 2

        draw.rounded_rectangle(
            [screen_x, screen_y, screen_x + screen_w, screen_y + screen_h],
            radius=12,
            fill=(255, 255, 255, 255),
        )

        # Draw home button / camera dot on bezel
        camera_x = tablet_x + tablet_w // 2
        camera_y = tablet_y + bezel // 2
        draw.ellipse(
            [camera_x - 6, camera_y - 6, camera_x + 6, camera_y + 6],
            fill=(60, 60, 62, 255),
        )

        canvas.paste(tablet_layer, (0, 0), tablet_layer)

        # Fit product image into screen area
        pw, ph = product_img.size
        scale = min(screen_w / pw, screen_h / ph, 1.0)
        new_w = int(pw * scale)
        new_h = int(ph * scale)
        resized = product_img.resize((new_w, new_h), Image.LANCZOS)

        # Center on screen
        img_x = screen_x + (screen_w - new_w) // 2
        img_y = screen_y + (screen_h - new_h) // 2
        canvas.paste(resized, (img_x, img_y), resized)

        # Add subtle shadow beneath the tablet
        shadow_strip = Image.new("RGBA", (tablet_w + 40, 30), (0, 0, 0, 35))
        shadow_strip = shadow_strip.filter(ImageFilter.GaussianBlur(radius=12))
        shadow_y_pos = tablet_y + tablet_h + 5
        canvas.paste(
            shadow_strip,
            (tablet_x - 20, shadow_y_pos),
            shadow_strip,
        )

        return canvas.convert("RGB")

    def _mockup_lifestyle(self, product_img: "Image.Image") -> "Image.Image":
        """
        Lifestyle mockup: Warm desk background with the product placed at a
        slight perspective. Includes decorative elements (coffee cup, plant dot).
        """
        canvas_size = (2400, 1600)

        # Warm desk gradient background
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # Desk surface — warm wood tone gradient
        for y in range(canvas_size[1]):
            ratio = y / canvas_size[1]
            r = int(210 - ratio * 30)
            g = int(180 - ratio * 35)
            b = int(140 - ratio * 30)
            draw.line([(0, y), (canvas_size[0], y)], fill=(r, g, b, 255))

        # Subtle wood grain lines
        for i in range(0, canvas_size[1], 80):
            grain_y = i + 40
            draw.line(
                [(0, grain_y), (canvas_size[0], grain_y)],
                fill=(195, 165, 125, 40), width=1,
            )

        # Decorative: small coffee-cup circle in top-right area
        cup_x, cup_y = 1900, 250
        draw.ellipse(
            [cup_x - 55, cup_y - 55, cup_x + 55, cup_y + 55],
            fill=(240, 235, 228, 255), outline=(200, 190, 175, 255), width=3,
        )
        draw.ellipse(
            [cup_x - 30, cup_y - 30, cup_x + 30, cup_y + 30],
            fill=(120, 80, 50, 200),
        )

        # Decorative: plant dot in top-left
        plant_x, plant_y = 200, 200
        draw.ellipse(
            [plant_x - 40, plant_y - 40, plant_x + 40, plant_y + 40],
            fill=(90, 140, 90, 200),
        )
        draw.ellipse(
            [plant_x - 50, plant_y + 20, plant_x + 50, plant_y + 80],
            fill=(160, 130, 100, 220),
        )

        # Place product: slight scale-down and simulate perspective via shear
        pw, ph = product_img.size
        max_dim = 1100
        scale = min(max_dim / pw, max_dim / ph, 1.0)
        new_w = int(pw * scale)
        new_h = int(ph * scale)
        resized = product_img.resize((new_w, new_h), Image.LANCZOS)

        # Apply a subtle affine transform for perspective look
        # Coefficients for a slight skew
        skew_amount = 0.05
        transform_data = (
            1, skew_amount, -skew_amount * new_h / 2,
            0, 1, 0,
        )
        transformed = resized.transform(
            (new_w, new_h), Image.AFFINE, transform_data,
            resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0),
        )

        # Add shadow under the product
        with_shadow = self._create_drop_shadow(
            transformed, offset=(20, 20), shadow_color=(0, 0, 0, 70),
            blur_radius=35, canvas_expand=70,
        )

        # Position product slightly off-center
        sw, sh = with_shadow.size
        paste_x = (canvas_size[0] - sw) // 2 + 50
        paste_y = (canvas_size[1] - sh) // 2 + 40
        canvas.paste(with_shadow, (paste_x, paste_y), with_shadow)

        return canvas.convert("RGB")

    # ------------------------------------------------------------------
    # Notion Sync
    # ------------------------------------------------------------------

    def sync_to_notion(self, slug: str, notion_sync: object) -> str:
        """
        Upsert product data into the Notion Products database.

        Expects `notion_sync` to have an `upsert_product(metadata: dict) -> str`
        method that returns the Notion page_id.

        Args:
            slug: Product slug.
            notion_sync: Object with an `upsert_product` method.

        Returns:
            The Notion page_id from the upsert.
        """
        metadata = self.get_metadata(slug)

        if not hasattr(notion_sync, "upsert_product"):
            raise AttributeError(
                "notion_sync object must have an 'upsert_product(metadata)' method"
            )

        page_id = notion_sync.upsert_product(metadata)
        self.update_metadata(slug, {"notion_page_id": page_id})
        logger.info("Synced '%s' to Notion (page_id=%s)", slug, page_id)
        return page_id

    # ------------------------------------------------------------------
    # Change Detection
    # ------------------------------------------------------------------

    def check_for_updates(self) -> List[Dict[str, Any]]:
        """
        Compare current file hashes of all products vs stored hashes.

        Re-packages deliverables for each product (into a temp ZIP) and compares
        against the stored file_hash. Returns a list of dicts for changed
        products with keys: slug, old_hash, new_hash.
        """
        changed = []

        for entry in sorted(self.products_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            slug = meta.get("slug", entry.name)
            stored_hash = meta.get("file_hash")
            deliverables_dir = entry / "deliverables"

            if not deliverables_dir.exists():
                continue

            # Collect deliverable files
            files = []
            for root, _dirs, fnames in os.walk(deliverables_dir):
                for fname in fnames:
                    fp = Path(root) / fname
                    arc = fp.relative_to(deliverables_dir)
                    files.append((fp, str(arc)))

            if not files:
                continue

            # Build a temp ZIP and hash it
            current_hash = self._hash_files_as_zip(files)

            if stored_hash is None or current_hash != stored_hash:
                changed.append({
                    "slug": slug,
                    "old_hash": stored_hash,
                    "new_hash": current_hash,
                    "deliverable_count": len(files),
                })

        return changed

    def _hash_files_as_zip(self, files: list) -> str:
        """Create a temporary ZIP of files and return its SHA-256 hash."""
        sha256 = hashlib.sha256()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for full_path, arc_name in sorted(files):
                    zf.write(full_path, arc_name)
            # Read back and hash
            with open(tmp.name, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)
        return sha256.hexdigest()


# ======================================================================
# Self-Tests
# ======================================================================

class ProductManagerTests(unittest.TestCase):
    """Self-tests for ProductManager."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pm_test_"))
        self.pm = ProductManager(products_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_product_basic(self):
        path = self.pm.create_product("test-art", "Printable Art")
        self.assertTrue(path.exists())
        self.assertTrue((path / "source").is_dir())
        self.assertTrue((path / "deliverables").is_dir())
        self.assertTrue((path / "mockups").is_dir())
        self.assertTrue((path / "metadata.json").is_file())

    def test_create_product_with_display_name(self):
        self.pm.create_product("my-thing", "Templates", display_name="My Cool Thing")
        meta = self.pm.get_metadata("my-thing")
        self.assertEqual(meta["display_name"], "My Cool Thing")
        self.assertEqual(meta["category"], "Templates")
        self.assertEqual(meta["status"], "draft")

    def test_create_duplicate_raises(self):
        self.pm.create_product("dup-test", "Art")
        with self.assertRaises(FileExistsError):
            self.pm.create_product("dup-test", "Art")

    def test_create_empty_slug_raises(self):
        with self.assertRaises(ValueError):
            self.pm.create_product("", "Art")

    def test_metadata_roundtrip(self):
        self.pm.create_product("rt-test", "Digital")
        meta = self.pm.get_metadata("rt-test")
        self.assertEqual(meta["slug"], "rt-test")
        self.assertIsNone(meta["price"])

    def test_update_metadata(self):
        self.pm.create_product("upd-test", "Art")
        updated = self.pm.update_metadata("upd-test", {"price": 9.99, "tags": ["wall"]})
        self.assertEqual(updated["price"], 9.99)
        self.assertIn("wall", updated["tags"])
        self.assertEqual(updated["version"], 2)

    def test_update_metadata_protected_fields(self):
        self.pm.create_product("prot-test", "Art")
        original = self.pm.get_metadata("prot-test")
        self.pm.update_metadata("prot-test", {"slug": "hacked", "created_at": "never"})
        meta = self.pm.get_metadata("prot-test")
        self.assertEqual(meta["slug"], original["slug"])
        self.assertEqual(meta["created_at"], original["created_at"])

    def test_list_products_all(self):
        self.pm.create_product("list-a", "Art")
        self.pm.create_product("list-b", "Templates")
        products = self.pm.list_products()
        slugs = {p["slug"] for p in products}
        self.assertIn("list-a", slugs)
        self.assertIn("list-b", slugs)

    def test_list_products_filtered(self):
        self.pm.create_product("filt-a", "Art")
        self.pm.create_product("filt-b", "Art")
        self.pm.update_metadata("filt-b", {"status": "ready"})
        drafts = self.pm.list_products(status="draft")
        ready = self.pm.list_products(status="ready")
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["slug"], "filt-a")
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["slug"], "filt-b")

    def test_package_deliverables(self):
        self.pm.create_product("pkg-test", "Art")
        # Create a dummy deliverable
        deliv_dir = self.test_dir / "pkg-test" / "deliverables"
        (deliv_dir / "sample.txt").write_text("hello world")
        (deliv_dir / "bonus.txt").write_text("bonus content")

        zip_path = self.pm.package_deliverables("pkg-test")
        self.assertTrue(zip_path.exists())
        self.assertTrue(zip_path.name.endswith(".zip"))

        meta = self.pm.get_metadata("pkg-test")
        self.assertIsNotNone(meta["file_hash"])
        self.assertEqual(meta["deliverable_count"], 2)
        self.assertIsNotNone(meta["package_date"])

    def test_package_empty_raises(self):
        self.pm.create_product("empty-pkg", "Art")
        with self.assertRaises(FileNotFoundError):
            self.pm.package_deliverables("empty-pkg")

    def test_compute_file_hash(self):
        self.pm.create_product("hash-test", "Art")
        deliv_dir = self.test_dir / "hash-test" / "deliverables"
        (deliv_dir / "file.txt").write_text("hash me")
        self.pm.package_deliverables("hash-test")
        h = self.pm.compute_file_hash("hash-test")
        self.assertEqual(len(h), 64)  # SHA-256 hex digest length

    def test_compute_hash_missing_raises(self):
        self.pm.create_product("nopkg", "Art")
        with self.assertRaises(FileNotFoundError):
            self.pm.compute_file_hash("nopkg")

    def test_check_for_updates_detects_new(self):
        self.pm.create_product("chk-test", "Art")
        deliv_dir = self.test_dir / "chk-test" / "deliverables"
        (deliv_dir / "art.txt").write_text("version 1")
        changed = self.pm.check_for_updates()
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["slug"], "chk-test")
        self.assertIsNone(changed[0]["old_hash"])

    def test_check_for_updates_no_change(self):
        self.pm.create_product("stable", "Art")
        deliv_dir = self.test_dir / "stable" / "deliverables"
        (deliv_dir / "art.txt").write_text("stable content")
        self.pm.package_deliverables("stable")
        changed = self.pm.check_for_updates()
        unchanged_slugs = [c["slug"] for c in changed]
        self.assertNotIn("stable", unchanged_slugs)

    def test_sync_to_notion(self):
        self.pm.create_product("sync-test", "Art")

        class MockNotionSync:
            def upsert_product(self, metadata):
                return "notion-page-abc123"

        page_id = self.pm.sync_to_notion("sync-test", MockNotionSync())
        self.assertEqual(page_id, "notion-page-abc123")
        meta = self.pm.get_metadata("sync-test")
        self.assertEqual(meta["notion_page_id"], "notion-page-abc123")

    def test_sync_bad_object_raises(self):
        self.pm.create_product("sync-bad", "Art")
        with self.assertRaises(AttributeError):
            self.pm.sync_to_notion("sync-bad", object())

    def test_generate_mockup_no_pillow_skips(self):
        """Validates error handling when Pillow is unavailable."""
        self.pm.create_product("mock-test", "Art")
        deliv_dir = self.test_dir / "mock-test" / "deliverables"
        (deliv_dir / "test.txt").write_text("not an image")
        if Image is None:
            with self.assertRaises(ImportError):
                self.pm.generate_mockup("mock-test")
        else:
            with self.assertRaises(FileNotFoundError):
                self.pm.generate_mockup("mock-test")

    def test_generate_mockup_invalid_template(self):
        self.pm.create_product("tmpl-test", "Art")
        if Image is not None:
            with self.assertRaises(ValueError):
                self.pm.generate_mockup("tmpl-test", template="nonexistent")

    def test_slugify(self):
        self.assertEqual(_slugify("My Cool Art"), "my-cool-art")
        self.assertEqual(_slugify("Hello & World"), "hello-and-world")
        self.assertEqual(_slugify("test--double"), "test-double")


# ======================================================================
# CLI
# ======================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Digital Storefront Product Lifecycle Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --create minimalist-wall-art --category 'Printable Art'\n"
            "  %(prog)s --package minimalist-wall-art\n"
            "  %(prog)s --mockup minimalist-wall-art --template device\n"
            "  %(prog)s --list --status draft\n"
            "  %(prog)s --check-updates\n"
            "  %(prog)s --test\n"
        ),
    )

    parser.add_argument(
        "--create", metavar="SLUG",
        help="Create a new product with the given slug",
    )
    parser.add_argument(
        "--category", metavar="CATEGORY",
        help="Product category (required with --create)",
    )
    parser.add_argument(
        "--name", metavar="NAME", default="",
        help="Display name for the product (optional with --create)",
    )
    parser.add_argument(
        "--package", metavar="SLUG",
        help="Package deliverables into a ZIP for the given product",
    )
    parser.add_argument(
        "--mockup", metavar="SLUG",
        help="Generate a mockup image for the given product",
    )
    parser.add_argument(
        "--template", metavar="TEMPLATE", default="default",
        choices=sorted(VALID_TEMPLATES),
        help="Mockup template to use (default, device, lifestyle)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all products",
    )
    parser.add_argument(
        "--status", metavar="STATUS",
        help="Filter products by status (used with --list)",
    )
    parser.add_argument(
        "--sync", metavar="SLUG",
        help="Sync a product to Notion (requires notion_sync integration)",
    )
    parser.add_argument(
        "--check-updates", action="store_true",
        help="Check all products for file changes vs stored hashes",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run self-tests",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging output",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.test:
        # Run self-tests and exit
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(ProductManagerTests)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1

    pm = ProductManager()

    if args.create:
        if not args.category:
            parser.error("--category is required with --create")
        try:
            path = pm.create_product(args.create, args.category, args.name)
            print(f"✅ Created product '{args.create}' at {path}")
        except FileExistsError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1

    elif args.package:
        try:
            zip_path = pm.package_deliverables(args.package)
            meta = pm.get_metadata(args.package)
            print(f"📦 Packaged '{args.package}' → {zip_path}")
            print(f"   Files: {meta['deliverable_count']} | Hash: {meta['file_hash'][:16]}…")
        except FileNotFoundError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1

    elif args.mockup:
        try:
            mockup_path = pm.generate_mockup(args.mockup, args.template)
            print(f"🖼️  Generated '{args.template}' mockup → {mockup_path}")
        except (FileNotFoundError, ImportError, ValueError) as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1

    elif args.list:
        products = pm.list_products(status=args.status)
        if not products:
            print("No products found.")
            return 0
        # Table header
        print(f"{'Slug':<35} {'Category':<20} {'Status':<10} {'Files':<6} {'Version'}")
        print("-" * 85)
        for p in products:
            print(
                f"{p['slug']:<35} {p['category']:<20} {p['status']:<10} "
                f"{p['deliverable_count']:<6} v{p['version']}"
            )
        print(f"\nTotal: {len(products)} product(s)")

    elif args.sync:
        print(
            "❌ Notion sync requires a configured notion_sync object.\n"
            "   Use ProductManager.sync_to_notion() programmatically.",
            file=sys.stderr,
        )
        return 1

    elif args.check_updates:
        changed = pm.check_for_updates()
        if not changed:
            print("✅ All products up to date — no changes detected.")
        else:
            print(f"⚠️  {len(changed)} product(s) have changed:\n")
            for c in changed:
                old_h = c["old_hash"][:16] + "…" if c["old_hash"] else "none"
                new_h = c["new_hash"][:16] + "…"
                print(f"  • {c['slug']}: {old_h} → {new_h} ({c['deliverable_count']} files)")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
