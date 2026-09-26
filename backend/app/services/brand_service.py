import ipaddress
import re
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

from ..config import settings
from ..schemas import BrandIdentitySpec
from .llm_service import qwen_structured
from .object_storage import persist_file


KNOWN_DOMAINS = {
    "mercedes": ("Mercedes-Benz", "mercedes-benz.com", "#111111", "#00ADEF"),
    "奔驰": ("Mercedes-Benz", "mercedes-benz.com", "#111111", "#00ADEF"),
    "bmw": ("BMW", "bmw.com", "#0066B1", "#111111"),
    "tesla": ("Tesla", "tesla.com", "#E82127", "#111111"),
    "apple": ("Apple", "apple.com", "#111111", "#8E8E93"),
    "microsoft": ("Microsoft", "microsoft.com", "#737373", "#00A4EF"),
    "google": ("Google", "google.com", "#4285F4", "#34A853"),
    "toyota": ("Toyota", "toyota.com", "#EB0A1E", "#111111"),
}


def _explicit_company(request: str) -> str | None:
    patterns = (
        r"(?:company|organization|brand)\s*[:：]\s*([^\n,;]+)",
        r"(?:公司|企业|品牌)\s*[:：]\s*([^\n，；]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, request, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def infer_brand_identity(request: str) -> BrandIdentitySpec | None:
    explicit = _explicit_company(request)
    lowered = (explicit or request).lower()
    for token, (name, domain, primary, accent) in KNOWN_DOMAINS.items():
        if token in lowered:
            return BrandIdentitySpec(
                company_name=name,
                website_domain=domain,
                primary_color=primary,
                accent_color=accent,
                initials="".join(part[0] for part in re.findall(r"[A-Za-z]+", name))[:3],
                confidence=1,
            )
    if not explicit:
        return None
    inferred = qwen_structured(
        "bi_design",
        (
            "Identify the company explicitly named in the request. If none is named, "
            "return company_name and website_domain as null. Use only a likely official "
            "root domain and conservative brand colors."
        ),
        {"request": request, "explicit_company": explicit},
        BrandIdentitySpec,
    )
    if not inferred or not inferred.company_name:
        return None
    return inferred


def _is_public_domain(domain: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or "." not in domain:
        return False
    try:
        addresses = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return True


def _download_official_icon(domain: str) -> tuple[bytes, str] | None:
    if not _is_public_domain(domain):
        return None
    homepage = f"https://{domain}/"
    request = Request(homepage, headers={"User-Agent": "Text2BI/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            page = response.read(750_000).decode("utf-8", errors="ignore")
        candidates = re.findall(
            r"<link[^>]+rel=[\"'][^\"']*(?:icon|apple-touch-icon)[^\"']*[\"'][^>]+href=[\"']([^\"']+)",
            page,
            flags=re.IGNORECASE,
        )
        candidates += re.findall(
            r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]+rel=[\"'][^\"']*(?:icon|apple-touch-icon)[^\"']*[\"']",
            page,
            flags=re.IGNORECASE,
        )
        candidates.append("/favicon.ico")
        for candidate in candidates[:5]:
            icon_url = urljoin(homepage, candidate)
            parsed = urlparse(icon_url)
            if parsed.scheme != "https" or parsed.hostname != domain:
                continue
            icon_request = Request(icon_url, headers={"User-Agent": "Text2BI/1.0"})
            try:
                with urlopen(icon_request, timeout=5) as response:
                    content_type = response.headers.get_content_type()
                    content = response.read(1_500_000)
                if content and content_type.startswith("image/"):
                    return content, content_type
            except Exception:
                continue
    except Exception:
        return None
    return None


def _custom_mark(identity: BrandIdentitySpec) -> tuple[bytes, str]:
    image = Image.new("RGBA", (256, 256), identity.primary_color)
    draw = ImageDraw.Draw(image)
    initials = (identity.initials or identity.company_name or "BI")[:3].upper()
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 92)
    except OSError:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), initials, font=font)
    draw.text(
        ((256 - (box[2] - box[0])) / 2, (256 - (box[3] - box[1])) / 2 - box[1]),
        initials,
        fill="white",
        font=font,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), "image/png"


def resolve_brand_assets(request: str) -> tuple[str | None, dict | None, str | None]:
    identity = infer_brand_identity(request)
    if not identity:
        return None, None, None
    downloaded = (
        _download_official_icon(identity.website_domain)
        if identity.website_domain and identity.confidence >= 0.7
        else None
    )
    content, content_type = downloaded or _custom_mark(identity)
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
    }.get(content_type, ".img")
    target = settings.upload_dir / f"brand-{uuid4().hex}{extension}"
    target.write_bytes(content)
    persist_file(target, prefix="logos")
    logo_url = f"{settings.backend_public_url.rstrip('/')}/uploads/{target.name}"
    source = "official_site" if downloaded else "custom_mark"
    return logo_url, identity.model_dump(mode="json"), source
