"""Validated, offline-only service for the synthetic public demo catalog."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "demo_data" / "products.json"
EXPECTED_PRODUCT_IDS = (
    "DEMO-CASUAL-001",
    "DEMO-RUN-002",
    "DEMO-WIDE-003",
    "DEMO-WORK-004",
    "DEMO-RAIN-005",
    "DEMO-PREORDER-006",
)
PRODUCT_ID_PATTERN = re.compile(r"^DEMO-[A-Z]+-\d{3}$")
SYNTHETIC_SKU_PATTERN = re.compile(r"^SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
VARIANT_ID_PATTERN = re.compile(r"^DEMO-[A-Z]+-\d{3}-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
SAFE_ASSET_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PRODUCT_LINK_PATTERN = re.compile(
    r"(?<![\w/])(?:https?://[^\s/]+)?/products/"
    r"(?P<product_id>DEMO-[A-Z]+-\d{3})(?=$|[\s/?#，。！？])",
    re.IGNORECASE,
)
ALLOWED_IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".avif"}
ALLOWED_SALE_TYPES = {"in_stock", "preorder"}
ALLOWED_FITS = {"standard", "runs_small", "wide_friendly"}
ALLOWED_UPPER_MATERIALS = {"PVC", "PU", "织物", "混合材料", "合成革"}
ALLOWED_LINING_MATERIALS = {"织物", "PU", "合成革", "保暖织物"}
ALLOWED_SOLE_MATERIALS = {"橡胶", "PU", "PVC", "复合底"}
ALLOWED_TOE_SHAPES = {"round", "almond", "wide_round"}
ALLOWED_UPPER_HEIGHTS = {"low", "mid", "high"}
ALLOWED_CLOSURES = {"lace_up", "slip_on", "buckle", "hook_and_loop"}
ALLOWED_PROCESSES = {"cemented", "injection_molded", "stitched"}
ALLOWED_HEEL_TYPES = {"flat", "low", "medium", "platform"}
ALLOWED_THICKNESSES = {"thin", "medium", "thick"}
ALLOWED_GENDERS = {"unisex", "men", "women"}
ALLOWED_SEASONS = {"春季", "夏季", "秋季", "冬季"}
FUNCTION_LEVELS = {
    "lightweight": {"standard", "light"},
    "breathability": {"low", "moderate", "high"},
    "slip_resistance": {"basic_daily", "enhanced_daily", "high_daily"},
    "wear_resistance": {"standard_daily", "enhanced_daily"},
    "water_resistance": {"none", "daily_splash", "light_rain"},
}
REQUIRED_PRODUCT_FIELDS = {
    "product_id",
    "data_classification",
    "identity",
    "pricing",
    "construction",
    "style",
    "functions",
    "sizing",
    "sale",
    "variants",
    "media",
}
PUBLIC_PRODUCT_FIELDS = frozenset(
    REQUIRED_PRODUCT_FIELDS
    | {
        "product_path",
        "thumbnail_url",
        "thumbnail_alt",
        "name",
        "short_description",
        "display_price",
        "fit",
        "fit_note",
        "sale_type",
        "available_colors",
        "available_sizes",
        "key_function",
    }
)
MISSING_PRODUCT_SELECTION_ANSWER = (
    "请先选择或告诉我您咨询的是哪款演示商品，我再根据对应商品信息为您确认。"
)
UNKNOWN_PRODUCT_LINK_ANSWER = "未找到该演示商品，请从页面中的演示商品列表重新选择。"
UNSPECIFIED_PRODUCT_FIELD_ANSWER = "当前演示商品信息没有说明这项内容。"

_EXPLICIT_FOOT_LENGTH_UNIT_PATTERN = re.compile(
    r"(?<![\d.])\d+(?:\.\d+)?(?:厘米|公分|毫米|cm|mm)(?![a-z])",
    re.IGNORECASE,
)
_IMPLICIT_FOOT_LENGTH_PATTERN = re.compile(
    r"(?:脚长|足长|脚)(?:是|为|有|约|大概|[:：])?(?P<value>\d+(?:\.\d+)?)"
)
_SIZE_RECOMMENDATION_PATTERN = re.compile(
    r"多大码|多少码|几码|选多大|穿多大|"
    r"尺码.{0,4}(?:怎么选|如何选)|"
    r"(?:这款|这双|鞋)(?:应该)?(?:怎么选|如何选)"
)
_SIZE_TERMS = re.compile(r"(?:穿|选|买|推荐|适合).{0,6}(?:(?:多大|多少|几)(?:码)?)|尺码|脚长|足长")
_FIT_TERMS = re.compile(r"偏大|偏小|标准码|宽脚|宽楦|脚宽|版型|合脚")
_COLOR_TERMS = re.compile(r"颜色|什么色|哪些色")
_AVAILABLE_SIZE_TERMS = re.compile(r"有哪些尺码|有什么尺码|尺码有哪些|有(?:没有)?\d{2}码")
_MATERIAL_TERMS = re.compile(r"(?:这款|这双|鞋子).{0,4}(?:什么|哪些)?材质|材质(?:是什么|有哪些)")
_UPPER_TERMS = re.compile(r"鞋面|面料|上层材质|upper", re.IGNORECASE)
_LINING_TERMS = re.compile(r"内里|里料|内衬|lining", re.IGNORECASE)
_SOLE_TERMS = re.compile(r"鞋底.{0,4}材质|底是什么|底部材质|sole", re.IGNORECASE)
_BREATH_TERMS = re.compile(r"透气")
_WATER_TERMS = re.compile(r"防水|防泼水|下雨|雨天")
_SLIP_TERMS = re.compile(r"防滑|打滑|抓地")
_WEAR_TERMS = re.compile(r"耐磨")
_SOLE_THICKNESS_TERMS = re.compile(r"鞋底.{0,3}(?:多厚|厚度)|底多厚|厚底")
_HEEL_HEIGHT_TERMS = re.compile(r"跟高|鞋跟.{0,3}(?:多高|高度)")
_WEIGHT_TERMS = re.compile(r"单只.{0,3}(?:多重|重量)|单鞋重量|鞋重")
_UPPER_HEIGHT_TERMS = re.compile(r"高帮|低帮|中帮|帮高")
_CLOSURE_TERMS = re.compile(r"怎么闭合|闭合方式|系带|套脚|搭扣|魔术贴")
_SEASON_TERMS = re.compile(r"适合什么季节|适合哪(?:个|些)?季节|季节")
_GENDER_TERMS = re.compile(r"适合男生还是女生|男款|女款|男女|性别")
_PRICE_TERMS = re.compile(r"多少钱|价格|售价")
_SHIPPING_TERMS = re.compile(r"发货|发出|发吗|几点前下单|什么时候发")
_PREORDER_TERMS = re.compile(r"预售|现货")
_POLICY_TERMS = re.compile(r"退货|换货|退款|售后|保修")
_PRODUCT_REFERENCE_TERMS = re.compile(r"这款|这个商品|这双|该商品")
_OUTDOOR_SCENARIO_TERMS = re.compile(r"爬山|登山|徒步|山路|户外")
_AUTHENTICITY_TERMS = re.compile(r"正品|假货|真假|验真|保真")
_AUTHENTICITY_INSURANCE_TERMS = re.compile(
    r"正品险|正品保险|保险|承保|PICC|中国人保",
    re.IGNORECASE,
)

AUTHENTICITY_POLICY_ANSWER = (
    "亲，本店所售商品均为正品，您可以放心选购哦。"
    "具体商品信息和售后保障以商品详情页及订单页展示为准。"
)

_PRODUCT_FEATURE_QUERIES = (
    (_BREATH_TERMS, "breathability", "透气"),
    (_WATER_TERMS, "water_resistance", "雨天穿着"),
    (_SLIP_TERMS, "slip_resistance", "防滑"),
    (_WEAR_TERMS, "wear_resistance", "耐磨"),
)

_UPPER_HEIGHT_LABELS = {"low": "低帮", "mid": "中帮", "high": "高帮"}
_CLOSURE_LABELS = {
    "lace_up": "系带",
    "slip_on": "套脚",
    "buckle": "搭扣",
    "hook_and_loop": "魔术贴",
}
_GENDER_LABELS = {"unisex": "男女均可", "men": "男式", "women": "女式"}


class CatalogValidationError(ValueError):
    """Raised when the tracked synthetic catalog violates its schema."""


@dataclass(frozen=True)
class ProductLinkReference:
    matched: bool
    product_id: str | None = None
    is_known: bool = False


def resolve_media_asset_ref(product_id: str, asset_ref: str | None) -> str | None:
    """Validate one inert local asset reference and derive its public URL."""
    if asset_ref is None:
        return None
    if not isinstance(asset_ref, str) or not asset_ref:
        raise CatalogValidationError("image asset_ref must be null or non-empty text")
    if not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise CatalogValidationError("invalid product_id for image asset")
    if any(token in asset_ref for token in ("\\", ":", "?", "#")) or asset_ref.startswith("/"):
        raise CatalogValidationError("unsafe image asset reference")
    path = PurePosixPath(asset_ref)
    if path.is_absolute() or len(path.parts) < 2 or path.parts[0] != product_id:
        raise CatalogValidationError("image asset must remain in its product namespace")
    if any(part in {".", ".."} or not SAFE_ASSET_SEGMENT_PATTERN.fullmatch(part) for part in path.parts):
        raise CatalogValidationError("unsafe image asset path segment")
    if path.suffix.casefold() not in ALLOWED_IMAGE_EXTENSIONS:
        raise CatalogValidationError("unsupported image extension")
    return f"/static/demo-products/{asset_ref}"


def _available_colors(product: Mapping[str, Any]) -> list[str]:
    return [str(variant["color_name"]) for variant in product["variants"]]


def _available_sizes(product: Mapping[str, Any]) -> list[int]:
    return sorted({int(size) for variant in product["variants"] for size in variant["available_sizes"]})


def _key_function(product: Mapping[str, Any]) -> str:
    candidates = (
        ("slip_resistance", "日常防滑", {"high_daily": 5, "enhanced_daily": 3, "basic_daily": 1}),
        ("water_resistance", "防泼水", {"light_rain": 5, "daily_splash": 3, "none": 0}),
        ("lightweight", "轻量", {"light": 4, "standard": 1}),
        ("breathability", "透气", {"high": 4, "moderate": 2, "low": 0}),
        ("wear_resistance", "日常耐磨", {"enhanced_daily": 3, "standard_daily": 1}),
    )
    scored = [
        (scores.get(product["functions"][key]["level"], 0), label)
        for key, label, scores in candidates
    ]
    return max(scored, key=lambda item: item[0])[1]


def _public_image(product_id: str, image: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "image_url": resolve_media_asset_ref(product_id, image["asset_ref"]),
        "alt": str(image["alt"]),
    }


class DemoCatalog:
    """Immutable-by-copy view of a fully validated local catalog."""

    def __init__(self, products: list[dict[str, Any]]) -> None:
        self._products = tuple(deepcopy(products))
        self._by_id = {product["product_id"]: product for product in self._products}

    @property
    def products(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(product) for product in self._products)

    @property
    def product_ids(self) -> tuple[str, ...]:
        return tuple(product["product_id"] for product in self._products)

    def lookup(self, product_id: str | None) -> dict[str, Any] | None:
        if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
            return None
        product = self._by_id.get(product_id)
        return deepcopy(product) if product else None

    def public_product(self, product_id: str | None) -> dict[str, Any] | None:
        product = self.lookup(product_id)
        if product is None:
            return None
        identity = product["identity"]
        pricing = product["pricing"]
        sizing = product["sizing"]
        sale = product["sale"]
        primary = _public_image(product_id, product["media"]["primary_image"])
        public_variants = [
            {
                "variant_id": variant["variant_id"],
                "color_name": variant["color_name"],
                "variant_label": variant["variant_label"],
                "available_sizes": deepcopy(variant["available_sizes"]),
                "image_url": resolve_media_asset_ref(product_id, variant["image_asset_ref"]),
            }
            for variant in product["variants"]
        ]
        public_media = {
            "primary_image": primary,
            "gallery": [_public_image(product_id, item) for item in product["media"]["gallery"]],
            "detail_images": [
                _public_image(product_id, item) for item in product["media"]["detail_images"]
            ],
        }
        public = {
            "product_id": product_id,
            "data_classification": product["data_classification"],
            "identity": deepcopy(identity),
            "pricing": deepcopy(pricing),
            "construction": deepcopy(product["construction"]),
            "style": deepcopy(product["style"]),
            "functions": deepcopy(product["functions"]),
            "sizing": deepcopy(sizing),
            "sale": deepcopy(sale),
            "variants": public_variants,
            "media": public_media,
            "product_path": f"/products/{product_id}",
            "thumbnail_url": primary["image_url"],
            "thumbnail_alt": primary["alt"],
            "name": identity["name"],
            "short_description": identity["short_description"],
            "display_price": pricing["display_price"],
            "fit": sizing["fit"],
            "fit_note": sizing["fit_note"],
            "sale_type": sale["sale_type"],
            "available_colors": _available_colors(product),
            "available_sizes": _available_sizes(product),
            "key_function": _key_function(product),
        }
        return {field: deepcopy(public[field]) for field in PUBLIC_PRODUCT_FIELDS}

    def public_products(self) -> list[dict[str, Any]]:
        return [self.public_product(product_id) for product_id in self.product_ids]


def _require_exact_fields(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CatalogValidationError(f"{label} has an invalid shape")
    return value


def _require_nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{label} must be non-empty text")
    return value


def _require_text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CatalogValidationError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise CatalogValidationError(f"{label} contains invalid text")
    if len(value) != len(set(value)):
        raise CatalogValidationError(f"{label} must be unique")
    return value


def _validate_optional_number(value: Any, label: str, *, maximum: float) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < float(value) <= maximum:
        raise CatalogValidationError(f"{label} is invalid")


def _validate_image(product_id: str, image: Any, label: str) -> None:
    record = _require_exact_fields(image, {"asset_ref", "alt"}, label)
    _require_nonempty_text(record["alt"], f"{label}.alt")
    resolve_media_asset_ref(product_id, record["asset_ref"])


def _validate_size_chart(sizing: Mapping[str, Any]) -> set[int]:
    chart = sizing["size_chart"]
    if not isinstance(chart, list) or not chart:
        raise CatalogValidationError("size_chart must be a non-empty list")
    previous_length: float | None = None
    previous_size: int | None = None
    sizes: set[int] = set()
    for row in chart:
        row = _require_exact_fields(row, {"foot_length_cm", "recommended_size"}, "size_chart row")
        length = row["foot_length_cm"]
        size = row["recommended_size"]
        if not isinstance(length, (int, float)) or isinstance(length, bool) or not 20 <= float(length) <= 32:
            raise CatalogValidationError("foot_length_cm must be a plausible number")
        if not isinstance(size, int) or isinstance(size, bool) or not 30 <= size <= 50:
            raise CatalogValidationError("recommended_size must be an adult shoe size")
        if previous_length is not None and float(length) <= previous_length:
            raise CatalogValidationError("size_chart foot lengths must increase")
        if previous_size is not None and size <= previous_size:
            raise CatalogValidationError("size_chart sizes must increase")
        previous_length = float(length)
        previous_size = size
        sizes.add(size)
    return sizes


def validate_catalog_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "products"}:
        raise CatalogValidationError("catalog root has an invalid shape")
    if payload["schema_version"] != 2:
        raise CatalogValidationError("unsupported catalog schema")
    products = payload["products"]
    if not isinstance(products, list) or len(products) != 6:
        raise CatalogValidationError("catalog must contain exactly six products")

    seen_products: set[str] = set()
    seen_skus: set[str] = set()
    seen_variants: set[str] = set()
    validated: list[dict[str, Any]] = []
    for product in products:
        product = _require_exact_fields(product, REQUIRED_PRODUCT_FIELDS, "product")
        product_id = product["product_id"]
        if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
            raise CatalogValidationError("invalid product_id")
        if product_id in seen_products:
            raise CatalogValidationError("duplicate product_id")
        seen_products.add(product_id)
        if product["data_classification"] != "synthetic_demo_data":
            raise CatalogValidationError("invalid data classification")

        identity = _require_exact_fields(
            product["identity"],
            {"name", "short_description", "category", "synthetic_sku", "target_gender", "target_audience", "seasons", "scenarios"},
            "identity",
        )
        for field in ("name", "short_description", "category", "target_audience"):
            _require_nonempty_text(identity[field], f"identity.{field}")
        sku = identity["synthetic_sku"]
        if not isinstance(sku, str) or not SYNTHETIC_SKU_PATTERN.fullmatch(sku) or sku in seen_skus:
            raise CatalogValidationError("invalid or duplicate synthetic_sku")
        seen_skus.add(sku)
        if identity["target_gender"] not in ALLOWED_GENDERS:
            raise CatalogValidationError("invalid target_gender")
        seasons = _require_text_list(identity["seasons"], "identity.seasons")
        if not set(seasons).issubset(ALLOWED_SEASONS):
            raise CatalogValidationError("invalid season")
        _require_text_list(identity["scenarios"], "identity.scenarios")

        pricing = _require_exact_fields(product["pricing"], {"currency", "display_price", "classification"}, "pricing")
        if pricing["currency"] != "CNY" or pricing["classification"] != "synthetic_demo_price":
            raise CatalogValidationError("invalid synthetic pricing classification")
        price = pricing["display_price"]
        if not isinstance(price, (int, float)) or isinstance(price, bool) or not 0 < float(price) < 10000 or round(float(price), 2) != float(price):
            raise CatalogValidationError("malformed display_price")

        construction = _require_exact_fields(
            product["construction"],
            {"upper_material", "lining_material", "sole_material", "toe_shape", "upper_height", "closure_type", "manufacturing_process", "heel_type", "heel_height_cm", "platform_height_cm", "thickness", "single_shoe_weight_g"},
            "construction",
        )
        enum_checks = (
            ("upper_material", ALLOWED_UPPER_MATERIALS),
            ("lining_material", ALLOWED_LINING_MATERIALS),
            ("sole_material", ALLOWED_SOLE_MATERIALS),
            ("toe_shape", ALLOWED_TOE_SHAPES),
            ("upper_height", ALLOWED_UPPER_HEIGHTS),
            ("closure_type", ALLOWED_CLOSURES),
            ("manufacturing_process", ALLOWED_PROCESSES),
            ("heel_type", ALLOWED_HEEL_TYPES),
            ("thickness", ALLOWED_THICKNESSES),
        )
        for field, allowed in enum_checks:
            if construction[field] not in allowed:
                raise CatalogValidationError(f"invalid construction.{field}")
        _validate_optional_number(construction["heel_height_cm"], "heel_height_cm", maximum=15)
        _validate_optional_number(construction["platform_height_cm"], "platform_height_cm", maximum=10)
        _validate_optional_number(construction["single_shoe_weight_g"], "single_shoe_weight_g", maximum=2000)

        style = _require_exact_fields(product["style"], {"style_name", "pattern", "fashion_elements"}, "style")
        _require_nonempty_text(style["style_name"], "style.style_name")
        _require_nonempty_text(style["pattern"], "style.pattern")
        _require_text_list(style["fashion_elements"], "style.fashion_elements")

        functions = _require_exact_fields(product["functions"], set(FUNCTION_LEVELS), "functions")
        for function_name, allowed_levels in FUNCTION_LEVELS.items():
            feature = _require_exact_fields(functions[function_name], {"level", "description"}, f"functions.{function_name}")
            if feature["level"] not in allowed_levels:
                raise CatalogValidationError(f"invalid {function_name} level")
            _require_nonempty_text(feature["description"], f"functions.{function_name}.description")

        sizing = _require_exact_fields(product["sizing"], {"fit", "fit_note", "size_chart"}, "sizing")
        if sizing["fit"] not in ALLOWED_FITS:
            raise CatalogValidationError("invalid fit")
        _require_nonempty_text(sizing["fit_note"], "sizing.fit_note")
        chart_sizes = _validate_size_chart(sizing)

        sale = _require_exact_fields(product["sale"], {"sale_type", "preorder_note"}, "sale")
        if sale["sale_type"] not in ALLOWED_SALE_TYPES:
            raise CatalogValidationError("invalid sale_type")
        if sale["sale_type"] == "preorder":
            _require_nonempty_text(sale["preorder_note"], "sale.preorder_note")
        elif sale["preorder_note"] is not None:
            raise CatalogValidationError("in-stock products cannot have preorder_note")

        if not isinstance(product["variants"], list) or not product["variants"]:
            raise CatalogValidationError("variants must be a non-empty list")
        for variant in product["variants"]:
            variant = _require_exact_fields(variant, {"variant_id", "color_name", "variant_label", "available_sizes", "image_asset_ref"}, "variant")
            variant_id = variant["variant_id"]
            if not isinstance(variant_id, str) or not VARIANT_ID_PATTERN.fullmatch(variant_id) or not variant_id.startswith(f"{product_id}-") or variant_id in seen_variants:
                raise CatalogValidationError("invalid or duplicate variant_id")
            seen_variants.add(variant_id)
            _require_nonempty_text(variant["color_name"], "variant.color_name")
            _require_nonempty_text(variant["variant_label"], "variant.variant_label")
            sizes = variant["available_sizes"]
            if not isinstance(sizes, list) or not sizes or not all(isinstance(size, int) and not isinstance(size, bool) for size in sizes):
                raise CatalogValidationError("variant sizes are invalid")
            if sizes != sorted(set(sizes)) or not set(sizes).issubset(chart_sizes):
                raise CatalogValidationError("variant sizes must be unique and inside the chart")
            resolve_media_asset_ref(product_id, variant["image_asset_ref"])

        media = _require_exact_fields(product["media"], {"primary_image", "gallery", "detail_images"}, "media")
        _validate_image(product_id, media["primary_image"], "media.primary_image")
        for collection_name in ("gallery", "detail_images"):
            collection = media[collection_name]
            if not isinstance(collection, list):
                raise CatalogValidationError(f"media.{collection_name} must be a list")
            for index, image in enumerate(collection):
                _validate_image(product_id, image, f"media.{collection_name}[{index}]")
        validated.append(deepcopy(product))

    if tuple(product["product_id"] for product in validated) != EXPECTED_PRODUCT_IDS:
        raise CatalogValidationError("catalog product inventory is incomplete or out of order")
    return validated


def load_catalog(path: Path = CATALOG_PATH) -> DemoCatalog:
    """Load one explicit local JSON file once; URLs are never accepted."""
    if not isinstance(path, Path):
        raise CatalogValidationError("catalog path must be a local Path")
    resolved = path.resolve()
    if resolved != CATALOG_PATH.resolve():
        raise CatalogValidationError("only the tracked demo catalog is allowed")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogValidationError("unable to load the demo catalog") from exc
    return DemoCatalog(validate_catalog_payload(payload))


def extract_demo_product_link(text: str, catalog: DemoCatalog) -> ProductLinkReference:
    match = PRODUCT_LINK_PATTERN.search(text or "")
    if not match:
        return ProductLinkReference(matched=False)
    product_id = match.group("product_id").upper()
    return ProductLinkReference(matched=True, product_id=product_id, is_known=catalog.lookup(product_id) is not None)


def is_product_specific_query(question: str) -> bool:
    text = question or ""
    if _POLICY_TERMS.search(text) or _AUTHENTICITY_INSURANCE_TERMS.search(text):
        return False
    patterns = (
        _PRODUCT_REFERENCE_TERMS, _SIZE_TERMS, _FIT_TERMS, _COLOR_TERMS,
        _AVAILABLE_SIZE_TERMS, _MATERIAL_TERMS, _UPPER_TERMS, _LINING_TERMS,
        _SOLE_TERMS, _BREATH_TERMS, _WATER_TERMS, _SLIP_TERMS, _WEAR_TERMS,
        _SOLE_THICKNESS_TERMS, _HEEL_HEIGHT_TERMS, _WEIGHT_TERMS,
        _UPPER_HEIGHT_TERMS, _CLOSURE_TERMS, _SEASON_TERMS, _GENDER_TERMS,
        _PRICE_TERMS, _PREORDER_TERMS, _OUTDOOR_SCENARIO_TERMS,
    )
    return any(pattern.search(text) for pattern in patterns)


def _exact_size_for_length(product: Mapping[str, Any], foot_length_cm: float) -> int | None:
    for row in product["sizing"]["size_chart"]:
        if abs(float(row["foot_length_cm"]) - foot_length_cm) < 0.001:
            return int(row["recommended_size"])
    return None


def _is_size_recommendation_intent(text: str) -> bool:
    return bool(_SIZE_RECOMMENDATION_PATTERN.search(re.sub(r"\s+", "", str(text or "")).casefold()))


def _parse_selected_product_foot_length(text: str):
    """Reuse the core parser, with a narrow product-size implicit-unit boundary."""
    from outputs.rag_answer_demo import FootLengthParse, parse_foot_length_expression

    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    if _EXPLICIT_FOOT_LENGTH_UNIT_PATTERN.search(normalized):
        return parse_foot_length_expression(text)
    marker_match = _IMPLICIT_FOOT_LENGTH_PATTERN.search(normalized)
    if marker_match is None or normalized[marker_match.end():].startswith("码"):
        return FootLengthParse(status="not_found")
    value = float(marker_match.group("value"))
    if not (20 <= value <= 32 or 200 <= value <= 320):
        return FootLengthParse(status="ambiguous", unit_inferred=True)
    return parse_foot_length_expression(f"脚长{marker_match.group('value')}")


def _size_measurement_clarification(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", normalized)
    if len(numbers) == 1 and 20 <= float(numbers[0]) <= 32:
        value = float(numbers[0])
        return f"请问您说的{value:g}是指脚长{value:g}厘米吗？确认后我再按这款商品的尺码表为您推荐。"
    return "请问您的脚长是多少厘米？确认后我再按这款商品的尺码表为您推荐。"


def _matched_variant(product: Mapping[str, Any], text: str) -> Mapping[str, Any] | None:
    normalized = re.sub(r"\s+", "", text or "").casefold()
    for variant in product["variants"]:
        for marker in (variant["variant_label"], variant["color_name"]):
            if re.sub(r"\s+", "", marker).casefold() in normalized:
                return variant
    return None


def _natural_product_size_answer(product: Mapping[str, Any], foot_length_cm: float, size: int, text: str) -> str:
    identity = product["identity"]
    fit = product["sizing"]["fit"]
    fit_guidance = {
        "standard": "这款是标准版型，下单前再对照一下商品详情页的尺码表会更稳妥。",
        "runs_small": "这款版型偏小，下单前建议再对照一下商品详情页尺码表。",
        "wide_friendly": "这款是宽楦友好版型，下单前再对照一下商品详情页的尺码表会更稳妥。",
    }[fit]
    variant = _matched_variant(product, text)
    available = variant["available_sizes"] if variant else _available_sizes(product)
    availability_note = ""
    if size not in available:
        scope = variant["variant_label"] if variant else "这款当前模拟颜色"
        availability_note = f"{scope}的模拟可选尺码暂不含{size}码；"
    return (
        f"亲，您脚长{foot_length_cm:g}厘米的话，‘{identity['name']}’建议选{size}码哦。"
        f"{availability_note}{fit_guidance}"
    )


def _list_text(values: list[Any], suffix: str = "") -> str:
    return "、".join(f"{value}{suffix}" for value in values)


def _render_product_service_reply(
    fact: str | list[str],
    guidance: str | None = None,
) -> str:
    """Render catalog-grounded facts through one deterministic service voice."""
    facts = [fact] if isinstance(fact, str) else list(fact)
    clean_facts = [
        re.sub(r"\s+", "", str(item)).rstrip("。！？；")
        for item in facts
        if str(item).strip()
    ]
    for index in range(1, len(clean_facts)):
        if clean_facts[index].startswith("这款的"):
            clean_facts[index] = clean_facts[index][3:]
        elif clean_facts[index].startswith("这款"):
            clean_facts[index] = clean_facts[index][2:]
    answer = f"亲，{'；'.join(clean_facts)}哦。"
    if guidance:
        clean_guidance = re.sub(r"\s+", "", str(guidance)).rstrip("。！？；")
        answer += f"{clean_guidance}。"
    return answer


def _missing_parameter(label: str) -> str:
    return _render_product_service_reply(
        f"这款暂时没有标注{label}",
        "建议以商品详情页展示为准",
    )


def _description_as_product_fact(description: str) -> str:
    text = str(description).strip().rstrip("。")
    if text.startswith(("未", "可", "不", "适合", "采用", "属于", "建议")):
        return f"这款{text}"
    return f"这款的{text.replace('提供', '可以提供', 1)}"


def _feature_fact(
    product: Mapping[str, Any],
    feature: str,
    label: str,
) -> str | None:
    description = product["functions"].get(feature, {}).get("description")
    if not description:
        return None
    return (
        _description_as_product_fact(description)
        if label in description
        else f"这款在{label}方面，{str(description).strip().rstrip('。')}"
    )


def _feature_answer(product: Mapping[str, Any], feature: str, label: str) -> str:
    fact = _feature_fact(product, feature, label)
    if fact is None:
        return _missing_parameter(label)
    guidance = (
        "遇到湿滑路面时，还是建议您多注意脚下"
        if feature == "slip_resistance"
        else None
    )
    return _render_product_service_reply(fact, guidance)


def _contextual_product_answer(
    text: str,
    product: Mapping[str, Any],
) -> str | None:
    matched_features = [
        (feature, label)
        for pattern, feature, label in _PRODUCT_FEATURE_QUERIES
        if pattern.search(text)
    ]
    has_outdoor_context = bool(_OUTDOOR_SCENARIO_TERMS.search(text))
    if len(matched_features) < 2 and not has_outdoor_context:
        return None

    facts: list[str] = []
    missing_labels: list[str] = []
    for feature, label in matched_features:
        fact = _feature_fact(product, feature, label)
        if fact is None:
            missing_labels.append(label)
        else:
            facts.append(fact)
    facts.extend(f"这款暂时没有标注{label}" for label in missing_labels)

    scenarios = [str(item) for item in product["identity"]["scenarios"]]
    scenario_text = _list_text(scenarios)
    guidance = None
    if has_outdoor_context:
        supports_outdoor = any(
            _OUTDOOR_SCENARIO_TERMS.search(scenario) for scenario in scenarios
        )
        if supports_outdoor:
            guidance = f"这款标注的使用场景包括{scenario_text}，实际穿着仍要结合路况"
        else:
            guidance = (
                f"这款标注的使用场景是{scenario_text}，没有标注登山或徒步用途，"
                "不建议把它当作登山鞋在湿滑山路使用"
            )
    elif any(feature == "slip_resistance" for feature, _label in matched_features):
        guidance = "遇到湿滑路面时，还是建议您多注意脚下"

    if not facts:
        facts = [f"这款标注的使用场景是{scenario_text}"]
    return _render_product_service_reply(facts, guidance)


def answer_product_question(
    question: str,
    product: Mapping[str, Any] | None,
    *,
    business_now: datetime | None = None,
) -> str | None:
    """Return a catalog-grounded deterministic answer, or ``None`` for safe RAG."""
    text = question or ""
    if _AUTHENTICITY_INSURANCE_TERMS.search(text):
        return None
    if _AUTHENTICITY_TERMS.search(text):
        return AUTHENTICITY_POLICY_ANSWER
    if product is None:
        return MISSING_PRODUCT_SELECTION_ANSWER if is_product_specific_query(question) else None

    identity = product["identity"]
    construction = product["construction"]
    sizing = product["sizing"]
    sale = product["sale"]
    has_size_intent = _is_size_recommendation_intent(text)
    foot_length_parse = _parse_selected_product_foot_length(text) if has_size_intent else None
    if foot_length_parse and foot_length_parse.status == "valid":
        foot_length = float(foot_length_parse.normalized_cm)
        size = _exact_size_for_length(product, foot_length)
        if size is None:
            return f"亲，这款尺码表暂时没有脚长{foot_length:g}厘米的精确码数，先不建议猜码哦。请在下单前对照商品详情页尺码表，或补充更准确的脚长。"
        return _natural_product_size_answer(product, foot_length, size, text)
    if has_size_intent:
        return _size_measurement_clarification(text)

    contextual_answer = _contextual_product_answer(text, product)
    if contextual_answer is not None:
        return contextual_answer

    if _FIT_TERMS.search(text):
        return _render_product_service_reply(f"这款是{sizing['fit_note']}")
    if _AVAILABLE_SIZE_TERMS.search(text):
        return _render_product_service_reply(
            f"这款可选尺码有{_list_text(_available_sizes(product), '码')}"
        )
    if _COLOR_TERMS.search(text):
        return _render_product_service_reply(
            f"这款有{_list_text(_available_colors(product))}这些颜色可选"
        )
    if _SOLE_THICKNESS_TERMS.search(text):
        value = construction["platform_height_cm"]
        return (
            _render_product_service_reply(f"这款鞋底前掌厚度约为{value:g}厘米")
            if value is not None
            else _missing_parameter("鞋底厚度")
        )
    if _HEEL_HEIGHT_TERMS.search(text):
        value = construction["heel_height_cm"]
        return (
            _render_product_service_reply(f"这款跟高约为{value:g}厘米")
            if value is not None
            else _missing_parameter("跟高")
        )
    if _WEIGHT_TERMS.search(text):
        value = construction["single_shoe_weight_g"]
        return (
            _render_product_service_reply(f"这款单只鞋约重{value:g}克")
            if value is not None
            else _missing_parameter("单只鞋重量")
        )
    if _UPPER_HEIGHT_TERMS.search(text):
        return _render_product_service_reply(
            f"这款是{_UPPER_HEIGHT_LABELS[construction['upper_height']]}设计"
        )
    if _CLOSURE_TERMS.search(text):
        return _render_product_service_reply(
            f"这款采用{_CLOSURE_LABELS[construction['closure_type']]}设计"
        )
    if _SEASON_TERMS.search(text):
        return _render_product_service_reply(
            f"这款比较适合{_list_text(identity['seasons'])}穿着"
        )
    if _GENDER_TERMS.search(text):
        gender = identity["target_gender"]
        gender_fact = (
            "这款男女都可以穿"
            if gender == "unisex"
            else f"这款是{_GENDER_LABELS[gender]}设计"
        )
        return _render_product_service_reply(
            f"{gender_fact}，比较适合{identity['target_audience']}"
        )
    if _PRICE_TERMS.search(text):
        return _render_product_service_reply(
            f"这款展示价格是¥{product['pricing']['display_price']:.2f}",
            "这里只作为功能演示参考",
        )
    if _LINING_TERMS.search(text):
        return _render_product_service_reply(
            f"这款内里用的是{construction['lining_material']}"
        )
    if _SOLE_TERMS.search(text):
        return _render_product_service_reply(
            f"这款鞋底用的是{construction['sole_material']}"
        )
    if _UPPER_TERMS.search(text):
        return _render_product_service_reply(
            f"这款鞋面用的是{construction['upper_material']}"
        )
    if _MATERIAL_TERMS.search(text):
        return _render_product_service_reply(
            f"这款鞋面用的是{construction['upper_material']}，"
            f"内里是{construction['lining_material']}，"
            f"鞋底是{construction['sole_material']}"
        )
    if _BREATH_TERMS.search(text):
        return _feature_answer(product, "breathability", "透气")
    if _WATER_TERMS.search(text):
        return _feature_answer(product, "water_resistance", "雨天穿着")
    if _SLIP_TERMS.search(text):
        return _feature_answer(product, "slip_resistance", "防滑")
    if _WEAR_TERMS.search(text):
        return _feature_answer(product, "wear_resistance", "耐磨")
    if _SHIPPING_TERMS.search(text):
        from outputs import rag_answer_demo as shipping_policy

        prospective_answer = shipping_policy.answer_for_prospective_shipping_policy(text, business_now=business_now)
        if prospective_answer is None:
            return None
        if sale["sale_type"] == "preorder":
            return _render_product_service_reply(
                "这款是预售款",
                sale["preorder_note"],
            )
        return prospective_answer
    if _PREORDER_TERMS.search(text):
        if sale["sale_type"] == "preorder":
            return _render_product_service_reply(
                "这款是预售款",
                sale["preorder_note"],
            )
        return _render_product_service_reply(
            "这款目前显示为现货",
            "具体发货时间仍以订单页显示为准",
        )
    if _PRODUCT_REFERENCE_TERMS.search(text) and not _POLICY_TERMS.search(text):
        return _render_product_service_reply(
            f"“{identity['name']}”是{identity['short_description']}",
            f"版型方面，{sizing['fit_note']}",
        )
    return None
