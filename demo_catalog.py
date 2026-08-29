"""Validated, offline-only service for the synthetic public demo catalog."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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
_AUTHENTICITY_TERMS = re.compile(r"正品|假货|真假|验真|保真")
_AUTHENTICITY_INSURANCE_TERMS = re.compile(
    r"正品险|正品保险|保险|承保|PICC|中国人保",
    re.IGNORECASE,
)

AUTHENTICITY_POLICY_ANSWER = (
    "亲，本店所售商品均为正品，您可以放心选购哦。"
    "具体商品信息和售后保障以商品详情页及订单页展示为准。"
)

_UPPER_HEIGHT_LABELS = {"low": "低帮", "mid": "中帮", "high": "高帮"}
_CLOSURE_LABELS = {
    "lace_up": "系带",
    "slip_on": "套脚",
    "buckle": "搭扣",
    "hook_and_loop": "魔术贴",
}
_GENDER_LABELS = {"unisex": "男女均可", "men": "男式", "women": "女式"}

PRODUCT_QUESTION_CLARIFICATION = (
    "亲，您主要想了解尺码、舒适度、透气性，还是适合什么场景呢？"
)


class ProductFacet(str, Enum):
    SIZE_RECOMMENDATION = "size_recommendation"
    FIT = "fit"
    WIDTH_AND_INSTEP = "width_and_instep"
    GENERAL_COMFORT = "general_comfort"
    LONG_WEAR_COMFORT = "long_wear_comfort"
    RUBBING_OR_PRESSURE = "rubbing_or_pressure"
    SOLE_SOFTNESS = "sole_softness"
    CUSHIONING = "cushioning"
    WEIGHT = "weight"
    BREATHABILITY = "breathability"
    WARMTH = "warmth"
    RAIN_USE = "rain_use"
    SLIP_RESISTANCE = "slip_resistance"
    WEAR_RESISTANCE = "wear_resistance"
    DURABILITY_OR_QUALITY = "durability_or_quality"
    UPPER_MATERIAL = "upper_material"
    LINING_MATERIAL = "lining_material"
    SOLE_MATERIAL = "sole_material"
    CLOSURE = "closure"
    HEEL_OR_SOLE_HEIGHT = "heel_or_sole_height"
    SHAFT_HEIGHT = "shaft_height"
    COLOR = "color"
    STYLE = "style"
    SEASON = "season"
    TARGET_GENDER_OR_GROUP = "target_gender_or_group"
    USE_SCENARIO = "use_scenario"
    PRICE = "price"
    STOCK = "stock"
    PRESALE = "presale"
    SHIPPING = "shipping"
    AUTHENTICITY = "authenticity"
    PRODUCT_OVERVIEW = "product_overview"


class ProductQuestionMode(str, Enum):
    FACTUAL_LOOKUP = "factual_lookup"
    SUBJECTIVE_ASSESSMENT = "subjective_assessment"
    SUITABILITY_ASSESSMENT = "suitability_assessment"
    RISK_OR_LIMITATION = "risk_or_limitation"
    SIZE_RECOMMENDATION = "size_recommendation"
    AVAILABILITY_OR_TRANSACTIONAL = "availability_or_transactional"
    COMPARISON_OR_MULTI_FACET = "comparison_or_multi_facet"
    AMBIGUOUS_CLARIFICATION = "ambiguous_clarification"


class ProductClaimStatus(str, Enum):
    SUPPORTED = "supported"
    CONDITIONALLY_SUPPORTED = "conditionally_supported"
    UNSUPPORTED = "unsupported"


class ProductMeasurementKind(str, Enum):
    WEIGHT = "weight"
    TEMPERATURE = "temperature"
    DISTANCE = "distance"
    DURATION = "duration"
    LEVEL = "level"


@dataclass(frozen=True)
class ProductNumericClaim:
    kind: ProductMeasurementKind
    value: float
    unit: str


@dataclass(frozen=True)
class ProductFacetRule:
    facet: ProductFacet
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class ProductQuestionAnalysis:
    original_text: str
    normalized_text: str
    facets: tuple[ProductFacet, ...]
    mode: ProductQuestionMode
    scenarios: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    question_numeric_claims: tuple[ProductNumericClaim, ...] = ()


@dataclass(frozen=True)
class ProductEvidence:
    facet: ProductFacet
    status: ProductClaimStatus
    facts: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    source_fields: tuple[str, ...] = ()
    numeric_claims: tuple[ProductNumericClaim, ...] = ()


@dataclass(frozen=True)
class ProductAnswerPlan:
    analysis: ProductQuestionAnalysis
    evidence: tuple[ProductEvidence, ...]
    facts: tuple[str, ...]
    limitations: tuple[str, ...]
    clarification: str | None = None


def _patterns(*expressions: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(expression, re.IGNORECASE) for expression in expressions)


_FACET_RULES = (
    ProductFacetRule(ProductFacet.SIZE_RECOMMENDATION, (_SIZE_RECOMMENDATION_PATTERN,)),
    ProductFacetRule(ProductFacet.FIT, _patterns(r"偏大|偏小|标准码|标准版型|版型|合脚")),
    ProductFacetRule(ProductFacet.WIDTH_AND_INSTEP, _patterns(r"宽脚|脚宽|宽楦|脚背|高脚背|鞋头.{0,3}(?:挤|窄)|前掌空间")),
    ProductFacetRule(ProductFacet.GENERAL_COMFORT, _patterns(r"舒适|舒服|好不好穿|穿着感觉|脚感")),
    ProductFacetRule(ProductFacet.LONG_WEAR_COMFORT, _patterns(r"穿久|走一天|久站|长时间穿|站一天|上班站|累不累|会不会累")),
    ProductFacetRule(ProductFacet.RUBBING_OR_PRESSURE, _patterns(r"磨不磨脚|磨脚|卡不卡脚|卡脚|挤不挤|挤脚|压不压|压脚背|顶脚|会不会(?:磨|卡|挤|压|顶)")),
    ProductFacetRule(ProductFacet.SOLE_SOFTNESS, _patterns(r"鞋底.{0,4}(?:软|硬)|踩着.{0,4}(?:软|硬)|软不软|硬不硬")),
    ProductFacetRule(ProductFacet.CUSHIONING, _patterns(r"缓震|减震|回弹")),
    ProductFacetRule(ProductFacet.WEIGHT, _patterns(r"轻不轻|重不重|沉不沉|会不会很沉|单只.{0,3}多重|单鞋重量|鞋重|重量")),
    ProductFacetRule(ProductFacet.BREATHABILITY, _patterns(r"透气|闷不闷|闷脚|捂不捂脚|捂脚|夏天.{0,5}(?:热|闷)")),
    ProductFacetRule(ProductFacet.WARMTH, _patterns(r"暖不暖|保不保暖|保暖|冬天.{0,5}(?:冷|暖)|里面有绒|内里有绒|加绒", r"(?:零下|负|-)?\d+(?:\.\d+)?(?:\s*[-~～至到]\s*(?:零下|负|-)?\d+(?:\.\d+)?)?(?:℃|摄氏度|度).{0,6}(?:穿|保暖|暖)")),
    ProductFacetRule(ProductFacet.RAIN_USE, (_WATER_TERMS, re.compile(r"进不进水|会不会进水"))),
    ProductFacetRule(ProductFacet.SLIP_RESISTANCE, _patterns(r"防滑|滑不滑|会不会滑|打滑|抓地")),
    ProductFacetRule(ProductFacet.WEAR_RESISTANCE, (_WEAR_TERMS,)),
    ProductFacetRule(ProductFacet.DURABILITY_OR_QUALITY, _patterns(r"耐不耐穿|耐穿|容易坏|会不会坏|会不会开胶|质量.{0,3}(?:怎么样|好吗)")),
    ProductFacetRule(ProductFacet.UPPER_MATERIAL, (_UPPER_TERMS,)),
    ProductFacetRule(ProductFacet.LINING_MATERIAL, (_LINING_TERMS, re.compile(r"里面有绒|内里有绒"))),
    ProductFacetRule(ProductFacet.SOLE_MATERIAL, (_SOLE_TERMS,)),
    ProductFacetRule(ProductFacet.CLOSURE, (_CLOSURE_TERMS,)),
    ProductFacetRule(ProductFacet.HEEL_OR_SOLE_HEIGHT, (_SOLE_THICKNESS_TERMS, _HEEL_HEIGHT_TERMS)),
    ProductFacetRule(ProductFacet.SHAFT_HEIGHT, (_UPPER_HEIGHT_TERMS,)),
    ProductFacetRule(ProductFacet.COLOR, (_COLOR_TERMS,)),
    ProductFacetRule(ProductFacet.STYLE, _patterns(r"什么款式|什么风格|款式怎么样|风格怎么样")),
    ProductFacetRule(ProductFacet.SEASON, (_SEASON_TERMS,)),
    ProductFacetRule(ProductFacet.TARGET_GENDER_OR_GROUP, (_GENDER_TERMS, re.compile(r"老人|老年|儿童|孩子|孕妇|怀孕|受伤|康复|扁平足|足弓|骨科"))),
    ProductFacetRule(ProductFacet.USE_SCENARIO, _patterns(r"适合.{0,8}(?:通勤|走路|步行|跑步|爬山|登山|徒步|户外|久站|雨天|夏天|冬天|工作)|通勤|走路|步行|跑步|爬山|登山|徒步|山路|户外|久站|雨天|夏天|冬天|工作穿")),
    ProductFacetRule(ProductFacet.PRICE, (_PRICE_TERMS,)),
    ProductFacetRule(ProductFacet.STOCK, (_AVAILABLE_SIZE_TERMS, re.compile(r"有货|库存|缺货|断码"))),
    ProductFacetRule(ProductFacet.PRESALE, (_PREORDER_TERMS,)),
    ProductFacetRule(ProductFacet.SHIPPING, (_SHIPPING_TERMS,)),
    ProductFacetRule(ProductFacet.AUTHENTICITY, (_AUTHENTICITY_TERMS,)),
    ProductFacetRule(ProductFacet.PRODUCT_OVERVIEW, _patterns(r"介绍(?:一下)?(?:这款|这个|这双)|(?:这款|这个|这双).{0,3}(?:介绍|特点|卖点)")),
)

_SCENARIO_RULES = (
    ("通勤", re.compile(r"通勤")),
    ("日常步行", re.compile(r"走路|步行")),
    ("专业跑步", re.compile(r"专业跑步|跑马|马拉松")),
    ("跑步", re.compile(r"(?<!专业)跑步|跑鞋")),
    ("登山徒步", re.compile(r"爬山|登山|徒步")),
    ("山路", re.compile(r"山路")),
    ("户外", re.compile(r"户外")),
    ("长时间站立", re.compile(r"久站|站一天|长时间站")),
    ("雨天", re.compile(r"下雨|雨天")),
    ("夏季", re.compile(r"夏天|夏季")),
    ("冬季", re.compile(r"冬天|冬季")),
    ("工作", re.compile(r"上班|工作")),
)
_PERSONAL_CONSTRAINT_RULES = (
    ("老年人", re.compile(r"老人|老年")),
    ("儿童", re.compile(r"儿童|孩子")),
    ("孕期", re.compile(r"孕妇|怀孕")),
    ("受伤或康复", re.compile(r"受伤|康复")),
    ("足部或骨科状况", re.compile(r"扁平足|足弓|骨科")),
)

_AMBIGUOUS_PRODUCT_PATTERNS = _patterns(
    r"(?:这款|这个|这双|它)?穿着怎么样",
    r"(?:这款|这个|这双|它)?怎么样",
    r"(?:这款|这个|这双|它)?好吗",
    r"(?:这款|这个|这双|它)?适合我吗",
)
_AFTER_SALES_DAMAGE_PATTERN = re.compile(
    r"(?:鞋子|鞋|这双)?.{0,3}(?:已经|刚)?(?:开胶|脱胶|破损|断底)了(?:怎么办|怎么处理|怎么弄)?"
)
_NON_PRODUCT_SERVICE_PATTERN = re.compile(r"物流|快递|订单状态|客服")
_NORMALIZE_PUNCTUATION = re.compile(r"[\s，。！？!?、；;：:“”‘’\"'（）()【】\[\]]+")
_LEADING_POLITE_PARTICLES = re.compile(r"^(?:你好|您好|亲|麻烦|请问)+")
_TRAILING_POLITE_PARTICLES = re.compile(r"(?:啊|呀|呢|哦|哈|吧|嘛|啦|呐|诶|唉)+$")
_TEMPERATURE_MENTION_PATTERN = re.compile(
    r"(?P<first_sign>零下|负|-)?(?P<first>\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|~|～|至|到)\s*(?P<second_sign>零下|负|-)?(?P<second>\d+(?:\.\d+)?))?"
    r"\s*(?:℃|°c|摄氏度|度)",
    re.IGNORECASE,
)
_WEIGHT_MENTION_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>千克|公斤|kg|克|g)(?![a-z])", re.IGNORECASE)
_DISTANCE_MENTION_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>毫米|厘米|公里|mm|cm|km|米|m)(?![a-z])", re.IGNORECASE)
_DURATION_MENTION_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>秒|分钟|小时|天|周|个月|月|年)")
_LEVEL_MENTION_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*级")


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


def normalize_product_question(question: str) -> str:
    """Normalize presentation noise without erasing business-bearing words."""
    normalized = _NORMALIZE_PUNCTUATION.sub("", str(question or "").casefold())
    normalized = _LEADING_POLITE_PARTICLES.sub("", normalized)
    return _TRAILING_POLITE_PARTICLES.sub("", normalized)


@dataclass(frozen=True)
class _NumericMention:
    claim: ProductNumericClaim
    start: int
    end: int


def _signed_temperature(sign: str | None, value: str) -> float:
    numeric = float(value)
    return -numeric if sign in {"零下", "负", "-"} else numeric


def _extract_numeric_mentions(text: str) -> tuple[_NumericMention, ...]:
    mentions: list[_NumericMention] = []
    for match in _TEMPERATURE_MENTION_PATTERN.finditer(text):
        first_sign = match.group("first_sign")
        values = [
            _signed_temperature(first_sign, match.group("first")),
        ]
        if match.group("second") is not None:
            second_sign = match.group("second_sign") or first_sign
            values.append(_signed_temperature(second_sign, match.group("second")))
        for value in values:
            mentions.append(
                _NumericMention(
                    ProductNumericClaim(ProductMeasurementKind.TEMPERATURE, value, "celsius"),
                    match.start(),
                    match.end(),
                )
            )
    for pattern, kind, factors, canonical_unit in (
        (
            _WEIGHT_MENTION_PATTERN,
            ProductMeasurementKind.WEIGHT,
            {"千克": 1000.0, "公斤": 1000.0, "kg": 1000.0, "克": 1.0, "g": 1.0},
            "g",
        ),
        (
            _DISTANCE_MENTION_PATTERN,
            ProductMeasurementKind.DISTANCE,
            {"毫米": 0.1, "mm": 0.1, "厘米": 1.0, "cm": 1.0, "米": 100.0, "m": 100.0, "公里": 100000.0, "km": 100000.0},
            "cm",
        ),
        (
            _DURATION_MENTION_PATTERN,
            ProductMeasurementKind.DURATION,
            {"秒": 1.0, "分钟": 60.0, "小时": 3600.0, "天": 86400.0, "周": 604800.0, "个月": 2592000.0, "月": 2592000.0, "年": 31536000.0},
            "seconds",
        ),
    ):
        for match in pattern.finditer(text):
            unit = match.group("unit").casefold()
            mentions.append(
                _NumericMention(
                    ProductNumericClaim(
                        kind,
                        float(match.group("value")) * factors[unit],
                        canonical_unit,
                    ),
                    match.start(),
                    match.end(),
                )
            )
    for match in _LEVEL_MENTION_PATTERN.finditer(text):
        mentions.append(
            _NumericMention(
                ProductNumericClaim(
                    ProductMeasurementKind.LEVEL,
                    float(match.group("value")),
                    "level",
                ),
                match.start(),
                match.end(),
            )
        )
    return tuple(sorted(mentions, key=lambda item: (item.start, item.end, item.claim.kind.value)))


def _question_mode(
    normalized: str,
    facets: tuple[ProductFacet, ...],
) -> ProductQuestionMode:
    facet_set = set(facets)
    if not facets and any(pattern.fullmatch(normalized) for pattern in _AMBIGUOUS_PRODUCT_PATTERNS):
        return ProductQuestionMode.AMBIGUOUS_CLARIFICATION
    if ProductFacet.SIZE_RECOMMENDATION in facet_set:
        return ProductQuestionMode.SIZE_RECOMMENDATION
    if facet_set & {
        ProductFacet.PRICE,
        ProductFacet.STOCK,
        ProductFacet.PRESALE,
        ProductFacet.SHIPPING,
    }:
        return ProductQuestionMode.AVAILABILITY_OR_TRANSACTIONAL
    if ProductFacet.TARGET_GENDER_OR_GROUP in facet_set and re.search(
        r"适合|能不能穿|能穿吗",
        normalized,
    ):
        return ProductQuestionMode.SUITABILITY_ASSESSMENT
    if ProductFacet.RUBBING_OR_PRESSURE in facet_set or ProductFacet.DURABILITY_OR_QUALITY in facet_set:
        if facet_set.issubset(
            {
                ProductFacet.RUBBING_OR_PRESSURE,
                ProductFacet.WIDTH_AND_INSTEP,
                ProductFacet.FIT,
                ProductFacet.DURABILITY_OR_QUALITY,
            }
        ):
            return ProductQuestionMode.RISK_OR_LIMITATION
    if len(facets) > 1:
        return ProductQuestionMode.COMPARISON_OR_MULTI_FACET
    if ProductFacet.USE_SCENARIO in facet_set:
        return ProductQuestionMode.SUITABILITY_ASSESSMENT
    if facet_set & {
        ProductFacet.RUBBING_OR_PRESSURE,
        ProductFacet.DURABILITY_OR_QUALITY,
        ProductFacet.RAIN_USE,
        ProductFacet.SLIP_RESISTANCE,
    } and re.search(r"会不会|能不能|容不容易|不不|是否", normalized):
        return ProductQuestionMode.RISK_OR_LIMITATION
    if facet_set and facet_set.issubset(
        {
            ProductFacet.UPPER_MATERIAL,
            ProductFacet.LINING_MATERIAL,
            ProductFacet.SOLE_MATERIAL,
            ProductFacet.CLOSURE,
            ProductFacet.HEEL_OR_SOLE_HEIGHT,
            ProductFacet.SHAFT_HEIGHT,
            ProductFacet.COLOR,
            ProductFacet.STYLE,
            ProductFacet.SEASON,
            ProductFacet.TARGET_GENDER_OR_GROUP,
            ProductFacet.PRICE,
            ProductFacet.STOCK,
            ProductFacet.PRESALE,
            ProductFacet.PRODUCT_OVERVIEW,
        }
    ):
        return ProductQuestionMode.FACTUAL_LOOKUP
    return ProductQuestionMode.SUBJECTIVE_ASSESSMENT


def analyze_product_question(question: str) -> ProductQuestionAnalysis:
    """Collect every applicable product facet before choosing an answer mode."""
    original = str(question or "")
    normalized = normalize_product_question(original)
    facets: list[ProductFacet] = []
    for rule in _FACET_RULES:
        if any(pattern.search(normalized) for pattern in rule.patterns):
            facets.append(rule.facet)
    if _MATERIAL_TERMS.search(normalized) and not set(facets) & {
        ProductFacet.UPPER_MATERIAL,
        ProductFacet.LINING_MATERIAL,
        ProductFacet.SOLE_MATERIAL,
    }:
        facets.extend(
            (
                ProductFacet.UPPER_MATERIAL,
                ProductFacet.LINING_MATERIAL,
                ProductFacet.SOLE_MATERIAL,
            )
        )
    scenarios = tuple(
        label for label, pattern in _SCENARIO_RULES if pattern.search(normalized)
    )
    constraints = tuple(
        label for label, pattern in _PERSONAL_CONSTRAINT_RULES if pattern.search(normalized)
    )
    question_numeric_claims = tuple(
        dict.fromkeys(mention.claim for mention in _extract_numeric_mentions(original))
    )
    unique_facets = tuple(dict.fromkeys(facets))
    return ProductQuestionAnalysis(
        original_text=original,
        normalized_text=normalized,
        facets=unique_facets,
        mode=_question_mode(normalized, unique_facets),
        scenarios=scenarios,
        constraints=constraints,
        question_numeric_claims=question_numeric_claims,
    )


def _is_product_service_collision(question: str) -> bool:
    normalized = normalize_product_question(question)
    return bool(
        _POLICY_TERMS.search(normalized)
        or _AUTHENTICITY_INSURANCE_TERMS.search(normalized)
        or _NON_PRODUCT_SERVICE_PATTERN.search(normalized)
        or _AFTER_SALES_DAMAGE_PATTERN.search(normalized)
    )


def is_product_specific_query(question: str) -> bool:
    if _is_product_service_collision(question):
        return False
    analysis = analyze_product_question(question)
    return bool(analysis.facets) or analysis.mode == ProductQuestionMode.AMBIGUOUS_CLARIFICATION


def _exact_size_for_length(product: Mapping[str, Any], foot_length_cm: float) -> int | None:
    for row in product["sizing"]["size_chart"]:
        if abs(float(row["foot_length_cm"]) - foot_length_cm) < 0.001:
            return int(row["recommended_size"])
    return None


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


def _render_product_answer_plan(plan: ProductAnswerPlan) -> str:
    if plan.clarification:
        return plan.clarification
    clean_facts = list(plan.facts) or ["当前商品资料没有说明这项内容"]
    answer = f"亲，{'；'.join(clean_facts)}哦。"
    if plan.limitations:
        answer += f"{'；'.join(plan.limitations)}。"
    return answer


def _render_product_service_reply(
    fact: str | list[str] | ProductAnswerPlan,
    guidance: str | None = None,
) -> str:
    """Render catalog-grounded facts through one deterministic service voice."""
    if isinstance(fact, ProductAnswerPlan):
        return validate_product_answer_claims(_render_product_answer_plan(fact), fact)
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


def _evidence(
    facet: ProductFacet,
    status: ProductClaimStatus,
    *facts: str,
    limitations: tuple[str, ...] = (),
    source_fields: tuple[str, ...] = (),
    numeric_claims: tuple[ProductNumericClaim, ...] = (),
) -> ProductEvidence:
    return ProductEvidence(
        facet=facet,
        status=status,
        facts=tuple(item for item in facts if item),
        limitations=limitations,
        source_fields=source_fields,
        numeric_claims=numeric_claims,
    )


def _fit_summary(product: Mapping[str, Any]) -> str:
    return {
        "standard": "标准版型",
        "runs_small": "版型偏小",
        "wide_friendly": "宽楦友好版型，前掌空间相对充足",
    }[product["sizing"]["fit"]]


def _format_temperature_celsius(value: float) -> str:
    absolute = f"{abs(value):g}"
    return f"零下{absolute}℃" if value < 0 else f"{absolute}℃"


def _scenario_evidence(
    product: Mapping[str, Any],
    analysis: ProductQuestionAnalysis,
) -> ProductEvidence:
    declared = tuple(str(item) for item in product["identity"]["scenarios"])
    declared_text = _list_text(list(declared))
    limitations: list[str] = []
    for scenario in analysis.scenarios:
        supported = False
        if scenario == "通勤":
            supported = any("通勤" in item for item in declared)
        elif scenario == "日常步行":
            supported = any("步行" in item for item in declared)
        elif scenario == "长时间站立":
            supported = any("站立" in item for item in declared)
        elif scenario == "雨天":
            supported = any("雨" in item for item in declared)
        elif scenario == "夏季":
            supported = "夏季" in product["identity"]["seasons"]
        elif scenario == "冬季":
            supported = any("冬季" in item or "保暖" in item for item in declared)
        elif scenario == "工作":
            supported = any("工作" in item for item in declared)
        if supported:
            continue
        if scenario == "专业跑步":
            limitations.append("这款没有标注专业跑步用途，不建议当作专业跑鞋使用")
        elif scenario == "跑步":
            limitations.append("这款没有明确标注跑步用途，不建议仅凭透气或轻便信息把它当作跑鞋")
        elif scenario == "登山徒步":
            limitations.append("这款没有标注登山或徒步用途，不建议把它当作登山鞋使用")
        elif scenario == "山路":
            limitations.append("这款没有标注山路用途，复杂路面需要选择对应功能鞋款")
        elif scenario == "户外":
            limitations.append("这款没有标注专业户外用途")
        else:
            limitations.append(f"这款没有明确标注{scenario}用途")
    scenario_fact = f"这款标注的使用场景包括{declared_text}"
    if set(analysis.scenarios).issubset({"夏季", "冬季"}):
        scenario_fact = f"这款标注适合{_list_text(product['identity']['seasons'])}穿着"
    return _evidence(
        ProductFacet.USE_SCENARIO,
        ProductClaimStatus.CONDITIONALLY_SUPPORTED,
        scenario_fact,
        limitations=tuple(limitations),
        source_fields=("identity.scenarios",),
    )


def _general_comfort_evidence(
    product: Mapping[str, Any],
    analysis: ProductQuestionAnalysis,
) -> ProductEvidence:
    construction = product["construction"]
    functions = product["functions"]
    lightweight = functions["lightweight"]
    breathability = functions["breathability"]
    if lightweight["level"] == "light" and breathability["level"] in {"moderate", "high"}:
        if construction["upper_material"] == construction["lining_material"] == "织物":
            fact = "这款主打轻量透气，织物鞋面和内里日常穿着会比较轻便"
        else:
            fact = f"这款{lightweight['description']}，{breathability['description']}"
    else:
        fact = f"这款{lightweight['description']}，{breathability['description']}"
    fit_summary = _fit_summary(product)
    if ProductFacet.FIT in analysis.facets:
        limitation = "舒适感会受脚型和尺码影响，建议量好脚长后按本款尺码表选择"
    else:
        limitation = f"舒适感会受脚型和尺码影响，这款{fit_summary}，建议量好脚长后按本款尺码表选择"
    return _evidence(
        ProductFacet.GENERAL_COMFORT,
        ProductClaimStatus.CONDITIONALLY_SUPPORTED,
        fact,
        limitations=(limitation,),
        source_fields=(
            "functions.lightweight",
            "functions.breathability",
            "construction.upper_material",
            "construction.lining_material",
            "sizing.fit_note",
        ),
    )


def _experience_evidence(
    facet: ProductFacet,
    product: Mapping[str, Any],
) -> ProductEvidence:
    sizing = product["sizing"]
    construction = product["construction"]
    if facet == ProductFacet.LONG_WEAR_COMFORT:
        supporting = product["functions"]["lightweight"]["description"]
        return _evidence(
            facet,
            ProductClaimStatus.UNSUPPORTED,
            "当前商品资料没有长期穿着测试结果",
            f"已知信息是{supporting}",
            limitations=("实际感受会受脚型、尺码、穿着时长和使用场景影响",),
            source_fields=("functions.lightweight",),
        )
    if facet == ProductFacet.RUBBING_OR_PRESSURE:
        closure = _CLOSURE_LABELS[construction["closure_type"]]
        return _evidence(
            facet,
            ProductClaimStatus.CONDITIONALLY_SUPPORTED,
            "当前商品资料没有磨脚或局部压力测试结果",
            f"这款{_fit_summary(product)}，采用{closure}设计",
            limitations=("是否磨脚、挤脚或压脚背会受脚型影响，建议量好脚长并按本款尺码表选择",),
            source_fields=("sizing.fit_note", "construction.closure_type"),
        )
    if facet == ProductFacet.SOLE_SOFTNESS:
        return _evidence(
            facet,
            ProductClaimStatus.UNSUPPORTED,
            "当前商品资料没有提供鞋底软硬度测量",
            limitations=("仅凭鞋底材质不能判断踩着软不软",),
        )
    return _evidence(
        facet,
        ProductClaimStatus.UNSUPPORTED,
        "当前商品资料没有提供缓震测试或缓震性能数据",
        limitations=("仅凭鞋底材质不能判断缓震表现",),
    )


def _extract_product_evidence(
    facet: ProductFacet,
    product: Mapping[str, Any],
    analysis: ProductQuestionAnalysis,
) -> ProductEvidence:
    identity = product["identity"]
    construction = product["construction"]
    functions = product["functions"]
    sizing = product["sizing"]
    sale = product["sale"]

    if facet == ProductFacet.FIT:
        fit_fact = f"这款{_fit_summary(product)}"
        return _evidence(
            facet,
            ProductClaimStatus.SUPPORTED,
            fit_fact,
            limitations=("建议量好脚长后按本款尺码表选择",),
            source_fields=("sizing.fit", "sizing.fit_note"),
        )
    if facet == ProductFacet.WIDTH_AND_INSTEP:
        if sizing["fit"] == "wide_friendly":
            return _evidence(facet, ProductClaimStatus.SUPPORTED, "这款是宽楦友好版型，前掌空间相对充足", source_fields=("sizing.fit", "sizing.fit_note"))
        return _evidence(facet, ProductClaimStatus.UNSUPPORTED, "当前商品资料没有单独提供脚背高度或前掌宽度数据", limitations=(str(sizing["fit_note"]).rstrip("。"),), source_fields=("sizing.fit_note",))
    if facet == ProductFacet.GENERAL_COMFORT:
        return _general_comfort_evidence(product, analysis)
    if facet in {ProductFacet.LONG_WEAR_COMFORT, ProductFacet.RUBBING_OR_PRESSURE, ProductFacet.SOLE_SOFTNESS, ProductFacet.CUSHIONING}:
        return _experience_evidence(facet, product)
    if facet == ProductFacet.WEIGHT:
        weight = construction["single_shoe_weight_g"]
        if weight is not None:
            return _evidence(
                facet,
                ProductClaimStatus.SUPPORTED,
                f"这款单只鞋约重{float(weight):g}克",
                source_fields=("construction.single_shoe_weight_g",),
                numeric_claims=(
                    ProductNumericClaim(ProductMeasurementKind.WEIGHT, float(weight), "g"),
                ),
            )
        description = functions["lightweight"].get("description")
        if description:
            return _evidence(facet, ProductClaimStatus.CONDITIONALLY_SUPPORTED, f"这款没有标注具体克重，{description}", source_fields=("functions.lightweight",))
        return _evidence(facet, ProductClaimStatus.UNSUPPORTED, "当前商品资料没有标注重量")
    if facet == ProductFacet.BREATHABILITY:
        description = functions["breathability"].get("description")
        if not description:
            return _evidence(facet, ProductClaimStatus.UNSUPPORTED, "当前商品资料没有标注透气性")
        return _evidence(
            facet,
            ProductClaimStatus.SUPPORTED,
            f"这款{str(description).rstrip('。')}，鞋面为{construction['upper_material']}、内里为{construction['lining_material']}",
            limitations=("透气表现不等于任何环境下都不会闷热，实际体感还会受气温和穿着时长影响",),
            source_fields=("functions.breathability", "construction.upper_material", "construction.lining_material"),
        )
    if facet == ProductFacet.WARMTH:
        asked_temperatures = tuple(
            claim
            for claim in analysis.question_numeric_claims
            if claim.kind == ProductMeasurementKind.TEMPERATURE
        )
        if construction["lining_material"] == "保暖织物":
            if asked_temperatures:
                temperature_text = "至".join(
                    _format_temperature_celsius(claim.value)
                    for claim in asked_temperatures
                )
                if len(asked_temperatures) == 1 and asked_temperatures[0].value <= -20:
                    context = f"{temperature_text}属于严寒环境"
                else:
                    context = f"您提到的{temperature_text}属于低温穿着条件"
                return _evidence(
                    facet,
                    ProductClaimStatus.CONDITIONALLY_SUPPORTED,
                    "这款是加绒冬季款，保暖织物能提供一定保暖",
                    "目前没有标注具体适用温度",
                    limitations=(f"{context}，实际感受还会受袜子厚度、活动时间和个人耐寒程度影响，不建议只凭商品参数判断",),
                    source_fields=("identity.name", "construction.lining_material", "identity.seasons"),
                )
            return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款内里是保暖织物，标注适合{_list_text(identity['seasons'])}穿着", limitations=("保暖体感仍会受当地气温和个人体感影响",), source_fields=("construction.lining_material", "identity.seasons"))
        missing_temperature = "，也没有标注具体适用温度" if asked_temperatures else ""
        return _evidence(facet, ProductClaimStatus.UNSUPPORTED, f"这款内里是{construction['lining_material']}，当前没有标注加绒或保暖功能{missing_temperature}", limitations=("不能因为是闭口鞋就判断为保暖款",), source_fields=("construction.lining_material",))
    if facet == ProductFacet.RAIN_USE:
        fact = _feature_fact(product, "water_resistance", "雨天穿着")
        return _evidence(facet, ProductClaimStatus.CONDITIONALLY_SUPPORTED if fact else ProductClaimStatus.UNSUPPORTED, fact or "当前商品资料没有标注雨天穿着能力", source_fields=("functions.water_resistance",))
    if facet == ProductFacet.SLIP_RESISTANCE:
        fact = _feature_fact(product, "slip_resistance", "防滑")
        return _evidence(facet, ProductClaimStatus.CONDITIONALLY_SUPPORTED if fact else ProductClaimStatus.UNSUPPORTED, fact or "当前商品资料没有标注防滑表现", limitations=("遇到湿滑路面时，还是建议您多注意脚下",) if fact else (), source_fields=("functions.slip_resistance",))
    if facet == ProductFacet.WEAR_RESISTANCE:
        fact = _feature_fact(product, "wear_resistance", "耐磨")
        return _evidence(facet, ProductClaimStatus.SUPPORTED if fact else ProductClaimStatus.UNSUPPORTED, fact or "当前商品资料没有标注耐磨表现", source_fields=("functions.wear_resistance",))
    if facet == ProductFacet.DURABILITY_OR_QUALITY:
        fact = _feature_fact(product, "wear_resistance", "耐磨")
        facts = tuple(item for item in (fact, "当前商品资料没有长期耐用或开胶测试结果") if item)
        return _evidence(facet, ProductClaimStatus.CONDITIONALLY_SUPPORTED, *facts, limitations=("日常耐磨信息不能保证使用寿命，也不能据此判断开胶风险",), source_fields=("functions.wear_resistance",))
    if facet == ProductFacet.UPPER_MATERIAL:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款鞋面用的是{construction['upper_material']}", source_fields=("construction.upper_material",))
    if facet == ProductFacet.LINING_MATERIAL:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款内里用的是{construction['lining_material']}", source_fields=("construction.lining_material",))
    if facet == ProductFacet.SOLE_MATERIAL:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款鞋底用的是{construction['sole_material']}", source_fields=("construction.sole_material",))
    if facet == ProductFacet.CLOSURE:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款采用{_CLOSURE_LABELS[construction['closure_type']]}设计", source_fields=("construction.closure_type",))
    if facet == ProductFacet.HEEL_OR_SOLE_HEIGHT:
        if _SOLE_THICKNESS_TERMS.search(analysis.normalized_text):
            value = construction["platform_height_cm"]
            label = "鞋底前掌厚度"
            source = "construction.platform_height_cm"
        else:
            value = construction["heel_height_cm"]
            label = "跟高"
            source = "construction.heel_height_cm"
        if value is None:
            return _evidence(facet, ProductClaimStatus.UNSUPPORTED, f"当前商品资料没有标注{label}")
        return _evidence(
            facet,
            ProductClaimStatus.SUPPORTED,
            f"这款{label}约为{float(value):g}厘米",
            source_fields=(source,),
            numeric_claims=(
                ProductNumericClaim(ProductMeasurementKind.DISTANCE, float(value), "cm"),
            ),
        )
    if facet == ProductFacet.SHAFT_HEIGHT:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款是{_UPPER_HEIGHT_LABELS[construction['upper_height']]}设计", source_fields=("construction.upper_height",))
    if facet == ProductFacet.COLOR:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款有{_list_text(_available_colors(product))}这些颜色可选", source_fields=("variants.color_name",))
    if facet == ProductFacet.STYLE:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款属于{identity['category']}，{str(identity['short_description']).rstrip('。')}", source_fields=("identity.category", "identity.short_description"))
    if facet == ProductFacet.SEASON:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款比较适合{_list_text(identity['seasons'])}穿着", source_fields=("identity.seasons",))
    if facet == ProductFacet.TARGET_GENDER_OR_GROUP:
        if analysis.constraints:
            labels = _list_text(list(analysis.constraints))
            return _evidence(
                facet,
                ProductClaimStatus.UNSUPPORTED,
                f"当前商品资料没有提供针对{labels}的适用性说明",
                limitations=("这类情况不能仅凭普通商品参数判断，建议结合个人状况向专业人士确认",),
                source_fields=("identity.target_audience",),
            )
        gender = identity["target_gender"]
        gender_fact = "男女都可以穿" if gender == "unisex" else f"是{_GENDER_LABELS[gender]}设计"
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款{gender_fact}，比较适合{identity['target_audience']}", source_fields=("identity.target_gender", "identity.target_audience"))
    if facet == ProductFacet.USE_SCENARIO:
        return _scenario_evidence(product, analysis)
    if facet == ProductFacet.PRICE:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款展示价格是¥{product['pricing']['display_price']:.2f}", limitations=("这里只作为功能演示参考",), source_fields=("pricing.display_price",))
    if facet == ProductFacet.STOCK:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"这款可选尺码有{_list_text(_available_sizes(product), '码')}", limitations=("具体颜色和尺码是否可选，以当前商品页显示为准",), source_fields=("variants.available_sizes",))
    if facet == ProductFacet.PRESALE:
        if sale["sale_type"] == "preorder":
            return _evidence(facet, ProductClaimStatus.SUPPORTED, "这款是预售款", limitations=(str(sale["preorder_note"]),), source_fields=("sale.sale_type", "sale.preorder_note"))
        return _evidence(facet, ProductClaimStatus.SUPPORTED, "这款目前显示为现货", limitations=("具体发货时间仍以订单页显示为准",), source_fields=("sale.sale_type",))
    if facet == ProductFacet.AUTHENTICITY:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, AUTHENTICITY_POLICY_ANSWER, source_fields=("store_policy.authenticity",))
    if facet == ProductFacet.PRODUCT_OVERVIEW:
        return _evidence(facet, ProductClaimStatus.SUPPORTED, f"“{identity['name']}”是{identity['short_description']}", f"版型方面，{sizing['fit_note']}", source_fields=("identity.name", "identity.short_description", "sizing.fit_note"))
    return _evidence(facet, ProductClaimStatus.UNSUPPORTED, "当前商品资料没有说明这项内容")


def _append_plan_text(items: list[str], candidate: str) -> None:
    clean = re.sub(r"\s+", "", str(candidate)).strip().rstrip("。！？；")
    if not clean or clean in items:
        return
    if "尺码表" in clean and any("尺码表" in item for item in items):
        return
    if clean.startswith("实际") and any(item.startswith("实际") for item in items):
        return
    items.append(clean)


def build_product_answer_plan(
    analysis: ProductQuestionAnalysis,
    product: Mapping[str, Any],
) -> ProductAnswerPlan:
    """Extract bounded evidence first, then compose one concise answer plan."""
    if analysis.mode == ProductQuestionMode.AMBIGUOUS_CLARIFICATION:
        return ProductAnswerPlan(
            analysis=analysis,
            evidence=(),
            facts=(),
            limitations=(),
            clarification=PRODUCT_QUESTION_CLARIFICATION,
        )
    evidence: list[ProductEvidence] = []
    facts: list[str] = []
    limitations: list[str] = []
    priority = {
        ProductFacet.GENERAL_COMFORT: 10,
        ProductFacet.LONG_WEAR_COMFORT: 20,
        ProductFacet.RUBBING_OR_PRESSURE: 30,
        ProductFacet.SOLE_SOFTNESS: 40,
        ProductFacet.CUSHIONING: 50,
        ProductFacet.WEIGHT: 60,
        ProductFacet.BREATHABILITY: 70,
        ProductFacet.WARMTH: 80,
        ProductFacet.RAIN_USE: 90,
        ProductFacet.SLIP_RESISTANCE: 100,
        ProductFacet.DURABILITY_OR_QUALITY: 110,
        ProductFacet.WEAR_RESISTANCE: 120,
        ProductFacet.USE_SCENARIO: 130,
        ProductFacet.WIDTH_AND_INSTEP: 140,
        ProductFacet.FIT: 150,
    }
    ordered_facets = sorted(
        analysis.facets,
        key=lambda item: priority.get(item, 75),
    )
    for facet in ordered_facets:
        if facet in {ProductFacet.SIZE_RECOMMENDATION, ProductFacet.SHIPPING, ProductFacet.AUTHENTICITY}:
            continue
        if facet == ProductFacet.LINING_MATERIAL and ProductFacet.WARMTH in analysis.facets:
            continue
        item = _extract_product_evidence(facet, product, analysis)
        evidence.append(item)
        if facet == ProductFacet.GENERAL_COMFORT and ProductFacet.LONG_WEAR_COMFORT in analysis.facets:
            continue
        if facet == ProductFacet.WIDTH_AND_INSTEP and ProductFacet.RUBBING_OR_PRESSURE in analysis.facets:
            continue
        if facet == ProductFacet.USE_SCENARIO:
            scenario_set = set(analysis.scenarios)
            if scenario_set == {"夏季"} and ProductFacet.BREATHABILITY in analysis.facets:
                continue
            if scenario_set == {"冬季"} and ProductFacet.WARMTH in analysis.facets:
                continue
        for fact in item.facts:
            _append_plan_text(facts, fact)
        for limitation in item.limitations:
            if "尺码表" in limitation and any("尺码表" in fact for fact in facts):
                continue
            _append_plan_text(limitations, limitation)
    return ProductAnswerPlan(
        analysis=analysis,
        evidence=tuple(evidence),
        facts=tuple(facts),
        limitations=tuple(limitations),
    )


_UNSAFE_PRODUCT_CLAIM_REPLACEMENTS = (
    (re.compile(r"绝对防滑|保证防滑"), "仅提供资料标注范围内的日常防滑表现"),
    (re.compile(r"完全防水|绝对防水"), "仅可按资料标注的防泼水范围使用"),
    (re.compile(r"保证舒适|一定舒服"), "舒适感会因脚型和使用场景而异"),
    (re.compile(r"不会磨脚"), "磨脚情况需要结合脚型和尺码判断"),
    (re.compile(r"不会开胶"), "当前没有长期开胶测试结果"),
    (re.compile(r"久站不累|全天不累"), "长期穿着感受会因人而异"),
)
_SAFE_CLAIM_NEGATION_MARKERS = ("不能保证", "无法保证", "无法确认", "不能确认", "没有证据", "未提供证据")
_BOUNDED_NUMERIC_CONTEXT_MARKERS = (
    "您提到",
    "您说的",
    "没有标注",
    "未标注",
    "无法确认",
    "不能判断",
    "不建议",
    "严寒环境",
    "低温穿着条件",
)


def _replace_unqualified_claim(
    text: str,
    pattern: re.Pattern[str],
    replacement: str,
) -> str:
    matches = list(pattern.finditer(text))
    for match in reversed(matches):
        prefix = text[max(0, match.start() - 12):match.start()]
        if any(marker in prefix for marker in _SAFE_CLAIM_NEGATION_MARKERS):
            continue
        text = text[:match.start()] + replacement + text[match.end():]
    return text


def _numeric_claim_matches(first: ProductNumericClaim, second: ProductNumericClaim) -> bool:
    return (
        first.kind == second.kind
        and first.unit == second.unit
        and abs(first.value - second.value) < 0.001
    )


def _numeric_mention_is_supported(
    mention: _NumericMention,
    answer: str,
    plan: ProductAnswerPlan,
) -> bool:
    evidence_claims = tuple(
        claim
        for item in plan.evidence
        for claim in item.numeric_claims
    )
    if any(_numeric_claim_matches(mention.claim, claim) for claim in evidence_claims):
        return True
    if not any(
        _numeric_claim_matches(mention.claim, claim)
        for claim in plan.analysis.question_numeric_claims
    ):
        return False
    context = answer[max(0, mention.start - 24):min(len(answer), mention.end + 40)]
    return any(marker in context for marker in _BOUNDED_NUMERIC_CONTEXT_MARKERS)


def validate_product_answer_claims(answer: str, plan: ProductAnswerPlan) -> str:
    """Final deterministic boundary against unsupported absolute product claims."""
    validated = str(answer)
    for pattern, replacement in _UNSAFE_PRODUCT_CLAIM_REPLACEMENTS:
        validated = _replace_unqualified_claim(validated, pattern, replacement)
    unsupported = {item.facet for item in plan.evidence if item.status == ProductClaimStatus.UNSUPPORTED}
    if ProductFacet.CUSHIONING in unsupported:
        validated = re.sub(r"缓震(?:出色|很好|优秀)", "没有缓震测试数据", validated)
    if ProductFacet.SOLE_SOFTNESS in unsupported:
        validated = re.sub(r"鞋底(?:很|比较)?柔软", "没有鞋底软硬度测量", validated)
    if any(
        not _numeric_mention_is_supported(mention, validated, plan)
        for mention in _extract_numeric_mentions(validated)
    ):
        return _render_product_answer_plan(plan)
    return validated


def answer_product_question(
    question: str,
    product: Mapping[str, Any] | None,
    *,
    business_now: datetime | None = None,
) -> str | None:
    """Return an evidence-planned deterministic answer, or ``None`` for non-product flows."""
    text = question or ""
    if _AUTHENTICITY_INSURANCE_TERMS.search(text):
        return None
    if _AUTHENTICITY_TERMS.search(text):
        return AUTHENTICITY_POLICY_ANSWER
    if _is_product_service_collision(text):
        return None
    analysis = analyze_product_question(text)
    if product is None:
        return MISSING_PRODUCT_SELECTION_ANSWER if is_product_specific_query(question) else None

    sale = product["sale"]
    has_size_intent = ProductFacet.SIZE_RECOMMENDATION in analysis.facets
    foot_length_parse = _parse_selected_product_foot_length(text) if has_size_intent else None
    if foot_length_parse and foot_length_parse.status == "valid":
        foot_length = float(foot_length_parse.normalized_cm)
        size = _exact_size_for_length(product, foot_length)
        if size is None:
            return f"亲，这款尺码表暂时没有脚长{foot_length:g}厘米的精确码数，先不建议猜码哦。请在下单前对照商品详情页尺码表，或补充更准确的脚长。"
        return _natural_product_size_answer(product, foot_length, size, text)
    if has_size_intent:
        return _size_measurement_clarification(text)

    if ProductFacet.SHIPPING in analysis.facets:
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
    if not analysis.facets and analysis.mode != ProductQuestionMode.AMBIGUOUS_CLARIFICATION:
        return None
    plan = build_product_answer_plan(analysis, product)
    return _render_product_service_reply(plan)
