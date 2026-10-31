"""Bounded public documentation retrieval. Page content is data, never commands."""
import asyncio
from dataclasses import dataclass, field
import ipaddress
import re
import socket
import threading
import unicodedata
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, ParserRejectedMarkup
import httpx

PAGE_BYTES = 512 * 1024
TOTAL_BYTES = 1024 * 1024
MAX_REQUESTS = 6  # Includes redirects and failures.
TOTAL_SECONDS = 20
STOP_WORDS = {"the", "and", "for", "with", "how", "from", "that", "this", "into", "use",
              "using", "can", "you", "your", "want", "need", "please", "help", "about"}
GENERIC_TERMS = {"python", "celo", "docs", "documentation", "page", "pages", "example", "examples"}
MAX_EXCERPTS = 5
TEXT_CHARS = 600
CODE_CHARS = 1200
MAX_BLOCKS = 4
BOILERPLATE = (
    "script, style, noscript, template, nav, footer, header, aside, "
    "[hidden], [aria-hidden='true'], [role='navigation'], [role='banner'], "
    "[role='contentinfo'], [role='search'], .sphinxsidebar, .related, .toctree-wrapper, "
    ".sidebar, .breadcrumb, .breadcrumbs, .pagination, .prev-next-area, "
    ".headerlink, .toc, #table-of-contents, .table-of-contents, .edit-page, "
    ".theme-doc-toc-desktop, .theme-doc-toc-mobile, .theme-doc-breadcrumbs, "
    ".theme-doc-footer, .theme-doc-sidebar-container, .copybutton, .linenos"
)


class ResearchError(ValueError):
    """A safe, user-facing retrieval failure."""


def clean(text: str) -> str:
    """Remove terminal controls and bidi formatting from untrusted output."""
    return " ".join("".join(c for c in text if not unicodedata.category(c).startswith("C") or c in "\n\t").split())


def terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower())) - STOP_WORDS


def relevance(text: str, goal: str) -> list[str]:
    return sorted((terms(text) & terms(goal)) - GENERIC_TERMS)


def public_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ResearchError("Invalid DNS address") from exc
    if not ip.is_global or ip.is_multicast or (isinstance(ip, ipaddress.IPv6Address) and (ip not in ipaddress.ip_network("2000::/3") or ip in ipaddress.ip_network("2001::/23") or ip.ipv4_mapped or ip.sixtofour or ip.teredo)):
        raise ResearchError("Blocked non-public or transition IP destination")
    return str(ip)


def safe_url(value: str, hostname: str | None = None) -> httpx.URL:
    if len(value) > 4096 or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise ResearchError("Invalid URL characters or length")
    try:
        url = httpx.URL(value)
        host = url.host
        if url.scheme != "https" or not host or url.port not in (None, 443) or url.userinfo:
            raise ResearchError("Only HTTPS on port 443 without credentials is allowed")
        if "%" in host or host.endswith(".") or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home")):
            raise ResearchError("Blocked local or ambiguous hostname")
        if hostname is not None and host != hostname:
            raise ResearchError("Destination must remain on the original hostname")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host:
                raise ResearchError("Invalid public hostname")
        else:
            public_ip(host)
        return url.copy_with(fragment=None)
    except (httpx.InvalidURL, ValueError) as exc:
        if isinstance(exc, ResearchError):
            raise
        raise ResearchError("Invalid HTTPS URL") from exc


async def resolve(host: str) -> list[str]:
    # A daemon avoids asyncio.run waiting indefinitely for a stuck platform DNS
    # worker during default-executor shutdown. At most six lookups per run.
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def deliver(result, error):
        if not future.done():
            if error:
                future.set_exception(error)
            else:
                future.set_result(result)

    def lookup():
        try:
            result, error = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM), None
        except OSError as exc:
            result, error = None, exc
        try:
            loop.call_soon_threadsafe(deliver, result, error)
        except RuntimeError:
            pass  # The deadline expired and the event loop has already closed.

    threading.Thread(target=lookup, daemon=True).start()
    try:
        answers = await asyncio.wait_for(future, timeout=3)
    except (OSError, TimeoutError) as exc:
        raise ResearchError("DNS resolution failed or timed out") from exc
    if not answers:
        raise ResearchError("DNS returned no addresses")
    # Reject mixed public/private answers; never let the HTTP client resolve again.
    return sorted({public_ip(answer[4][0]) for answer in answers})


def link_url(base: str, target: str, host: str) -> httpx.URL:
    try:
        return safe_url(urljoin(base, target), host)
    except ValueError as exc:
        raise ResearchError("Invalid or unapproved link/redirect destination") from exc


@dataclass
class Page:
    url: str
    title: str
    headings: list[str]
    sections: list[dict]
    links: list[dict]
    warning: str = ""


@dataclass
class Report:
    pages: list[Page] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requests: int = 0
    bytes_read: int = 0


def extract(body: bytes, url: str, goal: str) -> Page:
    try:
        soup = BeautifulSoup(body, "html.parser")
    except (ParserRejectedMarkup, UnicodeError) as exc:
        raise ResearchError("Unable to parse HTML response") from exc
    title = clean(soup.title.get_text(" "))[:300] if soup.title else "(untitled)"
    for tag in soup.select(BOILERPLATE):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    sections = []
    heading, blocks = "Page text", []
    seen_blocks = set()

    def flush():
        matched = relevance(heading + " " + " ".join(b["text"] for b in blocks), goal)
        if blocks and matched:
            # Prefer blocks matching the goal; retain adjacent code for context.
            selected = []
            for index, block in enumerate(blocks):
                if relevance(block["text"], goal) or block["kind"] in {"code", "notice"}:
                    selected.append(index)
            if not selected:
                selected = list(range(len(blocks)))
            selected = sorted(set(selected[:MAX_BLOCKS]))
            bounded = []
            prose_left, code_left = TEXT_CHARS, CODE_CHARS
            for i in selected:
                block = dict(blocks[i])
                if block["kind"] == "text":
                    if not prose_left:
                        continue
                    block["truncated"] |= len(block["text"]) > prose_left
                    block["text"] = block["text"][:prose_left]
                    prose_left -= len(block["text"])
                elif block["kind"] == "code":
                    if len(block["text"]) > code_left:
                        block = {"kind": "notice", "text": "[Code block omitted: excerpt size limit; consult source.]", "truncated": True}
                    else:
                        code_left -= len(block["text"])
                bounded.append(block)
            sections.append({"heading": heading, "source_url": url,
                             "text": "\n\n".join(b["text"] for b in bounded),
                             "blocks": bounded, "matched_terms": matched,
                             "truncated": len(bounded) < len(blocks) or any(b.get("truncated") for b in bounded)})

    for tag in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre"]):
        if tag.name.startswith("h"):
            flush()
            heading, blocks = clean(tag.get_text())[:300], []
        elif tag.name == "pre" or not tag.find_parent(["p", "li", "pre"]):
            is_code = tag.name == "pre"
            # Empty separator preserves adjacent syntax-highlight spans exactly.
            raw = tag.get_text() if is_code else "".join(node for node in tag.find_all(string=True) if not node.find_parent("pre"))
            text = raw if is_code else clean(raw)
            key = (is_code, text)
            if not text.strip() or key in seen_blocks:
                continue
            seen_blocks.add(key)
            if is_code:
                unsafe = any(unicodedata.category(c).startswith("C") and c not in "\n\t" for c in raw)
                if unsafe or len(raw) > CODE_CHARS:
                    reason = "unsafe control characters" if unsafe else "size limit"
                    blocks.append({"kind": "notice", "text": f"[Code block omitted: {reason}; consult source.]", "truncated": True})
                else:
                    blocks.append({"kind": "code", "text": raw, "truncated": False})
            else:
                blocks.append({"kind": "text", "text": text[:TEXT_CHARS], "truncated": len(text) > TEXT_CHARS})
    flush()
    sections.sort(key=lambda section: -len(section["matched_terms"]))
    sections = sections[:MAX_EXCERPTS]
    headings = list(dict.fromkeys(section["heading"] for section in sections))
    links = {}
    host = httpx.URL(url).host
    goal_terms = terms(goal) - GENERIC_TERMS
    # A one-term focused goal can match once; broader goals require two terms.
    minimum = min(2, len(goal_terms)) if goal_terms else 1
    for anchor in root.find_all("a", href=True):
        try:
            target = str(link_url(url, anchor["href"], host))
        except ResearchError:
            continue
        label = clean(anchor.get_text())[:200]
        # Hostnames and queries are not evidence of topical relevance.
        path = unquote(urlsplit(target).path)
        matched = relevance(label + " " + path, goal)
        if target != url and len(matched) >= minimum:
            links.setdefault(target, {"url": target, "label": label, "matched_terms": matched})
    ranked_links = sorted(links.values(), key=lambda link: (-len(link["matched_terms"]), link["url"]))[:5]
    readable = clean(root.get_text(" "))
    warning = ""
    if len(readable) < 100 or "enable javascript" in readable.lower():
        warning = "Sparse HTML or possible JavaScript-dependent page; scripts were not executed."
    return Page(url, title, headings, sections, ranked_links, warning)


async def fetch(client: httpx.AsyncClient, url: httpx.URL, host: str, report: Report) -> tuple[bytes, str]:
    seen = set()
    for hop in range(3):
        url = safe_url(str(url), host)
        if str(url) in seen:
            raise ResearchError("Redirect loop")
        seen.add(str(url))
        if report.requests >= MAX_REQUESTS:
            raise ResearchError("Total request budget exhausted")
        addresses = await resolve(url.host)
        # Validate even injected resolver answers, and pin the connection to an IP.
        addresses = [public_ip(address) for address in addresses]
        if not addresses:
            raise ResearchError("DNS returned no addresses")
        pinned = url.copy_with(host=addresses[0])
        report.requests += 1
        # Host and SNI retain the approved hostname; TLS verification stays enabled.
        async with client.stream("GET", pinned, headers={"Host": url.netloc.decode("ascii"), "Accept": "text/html", "Accept-Encoding": "identity"}, extensions={"sni_hostname": url.host}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise ResearchError("Redirect missing Location")
                if hop == 2:
                    raise ResearchError("Redirect limit exceeded")
                url = link_url(str(url), location, host)
                continue
            if not 200 <= response.status_code < 300:
                raise ResearchError(f"HTTP {response.status_code}")
            if response.headers.get("content-type", "").split(";")[0].strip().lower() != "text/html":
                raise ResearchError("Unsupported format: expected text/html")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ResearchError("Compressed responses are unsupported (bounded retrieval uses identity encoding)")
            length = response.headers.get("content-length")
            if length:
                try:
                    declared = int(length)
                except ValueError as exc:
                    raise ResearchError("Invalid Content-Length") from exc
                if declared < 0 or declared > min(PAGE_BYTES, TOTAL_BYTES - report.bytes_read):
                    raise ResearchError("Response size exceeds byte budget")
            body = bytearray()
            async for chunk in response.aiter_raw():
                report.bytes_read += len(chunk)
                if len(body) + len(chunk) > PAGE_BYTES or report.bytes_read > TOTAL_BYTES:
                    raise ResearchError("Response size exceeds byte budget")
                body.extend(chunk)
            return bytes(body), str(url)
    raise ResearchError("Redirect limit exceeded")


async def research(url: str, goal: str, *, transport: httpx.AsyncBaseTransport | None = None) -> Report:
    report = Report()
    try:
        seed = safe_url(url)
        if not terms(goal) or len(goal) > 1000:
            raise ResearchError("Goal must contain a searchable word and be at most 1000 characters")
        async with asyncio.timeout(TOTAL_SECONDS):
            # No ambient proxies, credentials, or custom CA environment settings.
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, timeout=httpx.Timeout(5, connect=3), limits=httpx.Limits(max_connections=1, max_keepalive_connections=0), headers={"User-Agent": "pathf1ndar/0.1 documentation-research"}) as client:
                pending = [str(seed)]
                visited = set()
                while pending and len(visited) < 3:
                    target = pending.pop(0)
                    if target in visited:
                        continue
                    visited.add(target)
                    try:
                        body, final_url = await fetch(client, safe_url(target, seed.host), seed.host, report)
                        if any(page.url == final_url for page in report.pages):
                            continue
                        page = extract(body, final_url, goal)
                        report.pages.append(page)
                        if len(visited) == 1:
                            pending.extend(link["url"] for link in page.links[:2])
                    except (ResearchError, httpx.HTTPError) as exc:
                        detail = str(exc) if isinstance(exc, ResearchError) else type(exc).__name__
                        report.errors.append(f"{target}: {detail}")
    except (ResearchError, TimeoutError) as exc:
        report.errors.append(str(exc) or "Total retrieval deadline exceeded")
    return report
