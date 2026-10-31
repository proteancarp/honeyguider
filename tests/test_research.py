import asyncio
import socket
import ssl
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from pathf1ndar import research as module
from pathf1ndar.cli import app

URL = "https://docs.example.com/start"
IP = "93.184.216.34"


def html(body="<title>Setup</title><main><h1>Python setup</h1><p>Install Python for this example.</p></main>", status=200, headers=None):
    return httpx.Response(status, headers={"content-type": "text/html", **(headers or {})}, stream=httpx.ByteStream(body.encode()))


def run(handler, url=URL, goal="python setup"):
    with patch.object(module, "resolve", AsyncMock(return_value=[IP])):
        return asyncio.run(module.research(url, goal, transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("url", ["http://docs.example.com", "file:///etc/passwd", "ftp://example.com", "https://user:pass@example.com", "https://example.com:8443", "https://localhost", "https://foo.local", "https://foo.localhost", "https://127.0.0.1", "https://10.1.2.3", "https://169.254.169.254", "https://[::1]", "https://[fc00::1]", "https://[fe80::1]", "https://[::ffff:127.0.0.1]", "https://[64:ff9b::7f00:1]", "https://224.0.0.1", "https://example.com./", "https://example.com\\@localhost", "https://example.com/\x1b"])
def test_blocked_url_never_requests(url):
    calls = []
    report = run(lambda request: calls.append(request) or html(), url)
    assert report.errors and not calls


def test_dns_mixed_private_rejected():
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in (IP, "127.0.0.1")]
    with patch.object(module.socket, "getaddrinfo", return_value=answers):
        with pytest.raises(module.ResearchError, match="non-public"):
            asyncio.run(module.resolve("docs.example.com"))


def test_dns_failure():
    with patch.object(module.socket, "getaddrinfo", side_effect=socket.gaierror("no DNS")):
        report = asyncio.run(module.research(URL, "python", transport=httpx.MockTransport(lambda r: pytest.fail("Must not connect"))))
    assert "DNS resolution failed" in report.errors[0]


def test_success_extraction_and_two_ranked_same_host_links():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == IP
        assert request.headers["host"] == "docs.example.com"
        assert request.extensions["sni_hostname"] == "docs.example.com"
        assert request.headers["accept-encoding"] == "identity"
        if request.url.path != "/start":
            return html("<title>Linked documentation</title><p>Python setup details.</p>")
        return html('''<title>Docs</title><nav>Noise</nav><main><h1>Setup</h1>
        <p>Python setup requires a project directory.</p><h2>Other</h2><p>Unrelated text.</p>
        <script>EXECUTE THIS</script><p hidden>SECRET</p>
        <a href="/python-b#fragment">Python setup B</a><a href="/python-a">Python setup A</a>
        <a href="/python-c">Python setup C</a><a href="https://other.example.com/python">Python</a>
        <a href="javascript:alert(1)">Python</a><a href="/unrelated">Other</a></main>''')
    report = run(handler)
    assert not report.errors
    assert len(calls) == len(report.pages) == 3
    assert [r.url.path for r in calls] == ["/start", "/python-a", "/python-b"]
    page = report.pages[0]
    assert page.url == URL and page.title == "Docs"
    assert page.headings == ["Setup"]
    assert page.sections[0]["matched_terms"] == ["setup"]
    assert "project directory" in page.sections[0]["text"]
    assert all("EXECUTE" not in s["text"] and "SECRET" not in s["text"] for s in page.sections)
    assert len(page.links) == 3


@pytest.mark.parametrize("location", ["https://evil.example.com/page", "http://docs.example.com/page", "https://127.0.0.1/", "https://docs.example.com:444/page", "https://user@docs.example.com/page"])
def test_redirect_destination_blocked(location):
    calls = []
    report = run(lambda r: calls.append(r) or html(status=302, headers={"location": location}))
    assert len(calls) == 1 and report.errors


def test_allowed_redirect_preserves_source():
    report = run(lambda r: html(status=302, headers={"location": "/final"}) if r.url.path == "/start" else html())
    assert not report.errors
    assert report.pages[0].url == "https://docs.example.com/final"
    assert report.requests == 2


def test_dns_rebinding_on_redirect_is_blocked():
    calls = []
    with patch.object(module, "resolve", AsyncMock(side_effect=[[IP], ["10.0.0.1"]])):
        report = asyncio.run(module.research(URL, "python", transport=httpx.MockTransport(lambda r: calls.append(r) or html(status=302, headers={"location": "/second"}))))
    assert len(calls) == 1
    assert "non-public" in report.errors[0]


@pytest.mark.parametrize("status,headers,message", [(404, {}, "HTTP 404"), (503, {}, "HTTP 503"), (200, {"content-type": "application/pdf"}, "Unsupported format"), (200, {"content-encoding": "gzip"}, "Compressed responses"), (200, {"content-length": str(module.PAGE_BYTES + 1)}, "byte budget"), (200, {"content-length": "invalid"}, "Content-Length"), (302, {}, "missing Location")])
def test_retrieval_failures(status, headers, message):
    report = run(lambda r: html(status=status, headers=headers))
    assert not report.pages
    assert message in report.errors[0]


@pytest.mark.parametrize("error", [httpx.ReadTimeout("timeout"), httpx.ConnectError("TLS failed"), httpx.RemoteProtocolError("bad response")])
def test_http_exceptions(error):
    def fail(request):
        raise error
    assert type(error).__name__ in run(fail).errors[0]


class Chunks(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(3):
            yield b"x" * (module.PAGE_BYTES // 2)


def test_stream_size_without_content_length():
    report = run(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, stream=Chunks()))
    assert "byte budget" in report.errors[0] and not report.pages


def test_total_byte_budget(monkeypatch):
    monkeypatch.setattr(module, "TOTAL_BYTES", 300)
    body = '<p>Python setup</p><a href="/python">Python setup</a>' + " " * 150
    report = run(lambda r: html(body))
    assert len(report.pages) == 1
    assert "byte budget" in report.errors[0]


def test_redirect_loop_and_hop_limit():
    assert "loop" in run(lambda r: html(status=302, headers={"location": "/start"})).errors[0]
    report = run(lambda r: html(status=302, headers={"location": r.url.path + "x"}))
    assert report.requests == 3 and "Redirect limit" in report.errors[0]


def test_total_request_budget(monkeypatch):
    monkeypatch.setattr(module, "MAX_REQUESTS", 2)
    report = run(lambda r: html('<p>Python setup</p><a href="/python-a">Python setup</a><a href="/python-b">Python setup</a>'))
    assert report.requests == 2 and len(report.pages) == 2
    assert "request budget" in report.errors[0]


def test_total_deadline(monkeypatch):
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.01)
    async def slow(request):
        await asyncio.sleep(1)
        return html()
    report = run(slow)
    assert not report.pages and "deadline" in report.errors[0]


def test_deadline_includes_dns(monkeypatch):
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.01)
    async def slow(host):
        await asyncio.sleep(1)
    with patch.object(module, "resolve", slow):
        report = asyncio.run(module.research(URL, "python"))
    assert report.requests == 0 and "deadline" in report.errors[0]


def test_sparse_page_no_matches_and_control_sanitizing():
    report = run(lambda r: html('<title>\x1b[31mTitle</title><div>Enable JavaScript</div>'))
    assert not report.pages[0].sections
    assert "JavaScript" in report.pages[0].warning
    assert "\x1b" not in report.pages[0].title


def test_partial_failure_retains_seed():
    report = run(lambda r: html('<p>Python setup</p><a href="/python">Python setup</a>') if r.url.path == "/start" else html(status=403))
    assert len(report.pages) == 1 and "HTTP 403" in report.errors[0]


def test_malformed_links_and_redirects():
    report = run(lambda r: html('<p>Python setup</p><a href="https://[invalid">Python</a>'))
    assert not report.errors and not report.pages[0].links
    report = run(lambda r: html(status=302, headers={"location": "https://[invalid"}))
    assert "Invalid" in report.errors[0]


def test_malformed_html_is_reported():
    report = run(lambda r: html('<![invalid]>'))
    assert not report.errors and report.pages[0].warning
    with patch.object(module, "BeautifulSoup", side_effect=module.ParserRejectedMarkup("rejected")):
        report = run(lambda r: html())
    assert "parse HTML" in report.errors[0]


def test_research_does_not_create_state(tmp_path):
    state = tmp_path / "absent.json"
    with patch("pathf1ndar.cli.research_pages", AsyncMock(return_value=module.Report())):
        CliRunner().invoke(app, ["--state-file", str(state), "research", URL, "--goal", "python"])
    assert not state.exists()


@pytest.mark.parametrize("goal", ["", "the and", "a" * 1001])
def test_invalid_goal(goal):
    report = run(lambda r: pytest.fail("No HTTP expected"), goal=goal)
    assert "Goal" in report.errors[0]


def test_cli_does_not_touch_plan(tmp_path):
    state = tmp_path / "state.json"
    state.write_text('existing progress, even if invalid')
    before = state.read_bytes()
    report = run(lambda r: html())
    with patch("pathf1ndar.cli.research_pages", AsyncMock(return_value=report)):
        result = CliRunner().invoke(app, ["--state-file", str(state), "research", URL, "--goal", "python setup"])
    assert result.exit_code == 0, result.output
    assert "untrusted source text" in result.output
    assert "Inferred relevance" in result.output
    assert state.read_bytes() == before
    with patch("pathf1ndar.cli.research_pages", AsyncMock(return_value=module.Report(errors=["HTTP 403"]))):
        result = CliRunner().invoke(app, ["research", URL, "--goal", "python"])
    assert result.exit_code == 1 and "HTTP 403" in result.output


def test_real_transport_connects_to_pinned_ip_with_verified_hostname():
    """Exercise HTTPX/HTTPCore plumbing with a fake network, not just MockTransport."""
    events = []
    class Stream:
        async def start_tls(self, ssl_context, server_hostname, timeout):
            events.append(("tls", server_hostname, ssl_context.verify_mode, ssl_context.check_hostname))
            return self
        async def write(self, buffer, timeout):
            events.append(("write", buffer))
        async def read(self, max_bytes, timeout):
            return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 20\r\nConnection: close\r\n\r\n<p>Python setup.</p> "
        async def aclose(self):
            pass
        def get_extra_info(self, info):
            return None
    class Backend:
        async def connect_tcp(self, host, port, **kwargs):
            events.append(("tcp", host, port))
            return Stream()
    transport = httpx.AsyncHTTPTransport()
    transport._pool._network_backend = Backend()
    with patch.object(module, "resolve", AsyncMock(return_value=[IP])):
        report = asyncio.run(module.research(URL, "python", transport=transport))
    assert not report.errors, report.errors
    assert ("tcp", IP, 443) in events
    assert ("tls", "docs.example.com", ssl.CERT_REQUIRED, True) in events
    assert any(event[0] == "write" and b"Host: docs.example.com" in event[1] for event in events)


def test_virtual_environment_goal_ignores_generic_links_and_boilerplate():
    body = '''<title>Python docs</title><main>
    <div role="navigation"><a href="/virtual-environment-nav">Virtual environment</a></div>
    <div class="related"><p>Create a virtual environment navigation</p></div>
    <aside>Virtual environment sidebar</aside>
    <header><a href="/header">Virtual environment</a></header>
    <h1>Create virtual environment</h1><p>Use venv to create a virtual environment.</p>
    <a href="/glossary.html">Python glossary</a><a href="/bugs.html">Report Python bugs</a>
    <a href="/virtual-environment">Virtual environment guide</a>
    <a href="/create-ticket">Create ticket</a><footer>Virtual environment footer</footer>
    </main>'''
    calls = []
    report = run(lambda r: calls.append(r.url.path) or html(body if r.url.path == '/start' else '<p>Virtual environment guide</p>'), goal='how to create a python virtual environment')
    assert calls == ['/start', '/virtual-environment']
    assert len(report.pages[0].links) == 1
    assert 'sidebar' not in str(report.pages[0].sections)
    assert 'navigation' not in str(report.pages[0].sections)
    assert 'footer' not in str(report.pages[0].sections)


@pytest.mark.parametrize('goal', ['python', 'celo', 'python virtual environment'])
def test_weak_links_do_not_fill_crawl_allowance(goal):
    calls = []
    report = run(lambda r: calls.append(r) or html('<p>Python Celo virtual environment</p><a href="/glossary">Python glossary</a><a href="/bugs">Celo bug reports</a><a href="/virtual">Virtual overview</a>'), goal=goal)
    assert len(calls) == 1
    assert not report.pages[0].links


def test_excerpts_are_deduplicated_concise_and_source_linked():
    body = ''.join(f'<h2>Virtual environment {i}</h2><p>Virtual environment detail {i} ' + 'x' * 900 + '</p><p>Repeated virtual environment text.</p>' for i in range(10))
    page = module.extract(body.encode(), URL, 'python virtual environment')
    assert len(page.sections) == 5
    assert all(s['source_url'] == URL for s in page.sections)
    assert all(sum(len(b['text']) for b in s['blocks'] if b['kind'] == 'text') <= 600 for s in page.sections)
    assert all(s['truncated'] for s in page.sections)
    assert sum(s['text'].count('Repeated virtual environment text.') for s in page.sections) <= 1


def test_code_spans_indentation_tabs_blank_lines_and_continuations_preserved():
    source = 'python -m venv .venv\n\nif True:\n\tprint("two  spaces")\npython -m pip install \\\n    httpx\n'
    markup = '<h1>Virtual environment</h1><p>Create a virtual environment.</p><pre><span>python</span>' + source[len('python'):] + '</pre>'
    page = module.extract(markup.encode(), URL, 'virtual environment')
    code = next(b['text'] for b in page.sections[0]['blocks'] if b['kind'] == 'code')
    assert code == source
    report = module.Report(pages=[page])
    with patch('pathf1ndar.cli.research_pages', AsyncMock(return_value=report)):
        result = CliRunner().invoke(app, ['research', URL, '--goal', 'virtual environment'])
    assert result.exit_code == 0
    assert source in result.output


def test_code_nested_in_list_is_not_flattened_or_repeated():
    page = module.extract(b'<h2>Virtual environment</h2><ul><li>Create environment<pre>if True:\n    print(1)\n</pre></li></ul>', URL, 'virtual environment')
    blocks = page.sections[0]['blocks']
    assert [b['kind'] for b in blocks] == ['text', 'code']
    assert blocks[1]['text'] == 'if True:\n    print(1)\n'
    assert 'print' not in blocks[0]['text']


@pytest.mark.parametrize('code,reason', [('python ' + 'x' * 1300, 'size limit'), ('python\x1b[31m install', 'unsafe control characters')])
def test_unsafe_or_oversized_code_is_explicitly_omitted(code, reason):
    page = module.extract(('<h2>Virtual environment</h2><pre>' + code + '</pre>').encode(), URL, 'virtual environment')
    blocks = page.sections[0]['blocks']
    assert not any(b['kind'] == 'code' for b in blocks)
    assert reason in blocks[0]['text']
    assert page.sections[0]['truncated']
