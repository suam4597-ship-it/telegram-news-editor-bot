from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "spm",
}


def normalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, url) if base_url else url
    parts = urlsplit(absolute.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("m."):
        netloc = netloc[2:]
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    if path.startswith("/amp/"):
        path = path[4:] or "/"
    if path.endswith("/amp"):
        path = path[:-4] or "/"

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        lower_key = key.lower()
        if lower_key.startswith("utm_") or lower_key in TRACKING_PARAMS:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_or_original(canonical_url: str | None, original_url: str, base_url: str | None = None) -> str:
    return normalize_url(canonical_url or original_url, base_url=base_url)

