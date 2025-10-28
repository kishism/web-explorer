from time import sleep
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from rich.console import Console, Group
from rich.text import Text
from rich.live import Live
from rich.panel import Panel
from urllib.parse import urlparse
from bs4 import BeautifulSoup

console = Console()

def browse_or_fail(page, url: str, timeout: int = 10000):
    try:
        response = page.goto(url, wait_until='load', timeout=timeout)
        if response is None:
            return {
                "ok": False,
                "status": None,
                "reason": "no_response",
                "details": "page.goto returned None."
            }
        status = response.status
        if status >= 100:
            return {
                "ok": False,
                "status": status,
                "reasons": "http_error",
                "details": f"HTTP status {status}."
            }
        return {
            "ok": True,
            "status": status,
            "reason": "ok",
            "details": "Navgiation successful."
        }
    except PlaywrightError as e:
        err_text = str(e)        
        if "net::ERR_CONNECTION_REFUSED" in err_text:
            code = 502  # Bad Gateway 
            reason = "connection_refused"
        elif "net::ERR_NAME_NOT_RESOLVED" in err_text:
            code = 502
            reason = "dns_failure"
        elif "Timeout" in err_text or "Navigation timeout" in err_text:
            code = 504  # Gateway Timeout
            reason = "timeout"
        else:
            code = 520  # Unknown error (non-standard, common to represent "unexpected")
            reason = "playwright_error"
        return {"ok": False, "status": code, "reason": reason, "details": err_text}
    
def tag_prefix(tag):
    if tag == 'h1':
        return 'H: '
    elif tag == 'h2':
        return 'Sub-H: '
    elif tag == 'h3':
        return 'Sub-Sub-H: '
    elif tag == 'p':
        return 'P: '
    elif tag == 'a':
        return ''  # handled separately
    else:
        return ''

def print_dom(node, indent=0):

    lines = []
    global link_counter
    if node is None:
        return

    spacer = " " * indent
    prefix = tag_prefix(node['tag'])

    if node['tag'] == 'a':
        href = node.get('href', '')
        text = node.get('text', href) or href or '(no-text)'
        link_text = Text(f"{link_counter}) Link: {text} -> {href}", style="bold blue underline")
        # console.print(spacer, link_text)
        lines.append(spacer + link_text.plain)
        link_map[link_counter] = href
        link_counter += 1
    else:
        if node.get("text"):
            if node['tag'].startswith('h1'):
                style = "bold magenta"
            elif node['tag'].startswith('h2'):
                style = "bold yellow"
            elif node['tag'].startswith('h3'):
                style = "bold green"
            elif node['tag'] == 'p':
                style = "white"
            elif node['tag'] == 'pre':
                style = "light_slate_blue"
            else:
                style = "dim"
            # console.print(spacer + prefix + node['text'], style=style)
            line = Text(spacer + prefix + node['text'], style=style)
            lines.append(line)

    for child in node.get("children", []):
        lines.extend(print_dom(child, indent + 1))
    
    return lines

def show_welcome_banner():
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    welcome_text = soup.pre.string if soup.pre else "Welcome to Web Explorer"
    sub_text = soup.p.string if soup.p else "Text-based browser environment"

    welcome_rich = Text(welcome_text, style="light_slate_blue", justify="center")
    sub_rich = Text(sub_text, style="white", justify="center")

    banner = Panel.fit(
        Text.assemble(welcome_rich, "\n", sub_rich),
        border_style="blue_violet",
        padding=(1, 4),
    )
    console.clear()
    console.print(banner)
    console.print("\nPress Enter to start browsing...", style="dim")
    input()

def url_validate(u: str) -> bool:
    if not u:
        return False
    u = u.strip()
    if u.startswith('#') or u.startswith('javascript:') or u.startswith('mailto:'):
        return False
    parsed  = urlparse(u)
    if parsed.scheme in ('http', 'https'):
        return True
    return False

show_welcome_banner()  

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    result = browse_or_fail(page, "http://127.0.0.1:5500/index.html", timeout=10000)

    link_counter = 1
    link_map = {}

    dom_tree = page.evaluate("""
        () => {                             
            const walk = (el) => {
                const tagName = el.tagName.toLowerCase() ? el.tagName.toLowerCase(): 'unknown';
                if (tagName === 'script' || tagName === 'style') return null;  
                const hasChildren = el.children && el.children.length > 0;
                let text = null;
                try {
                    const raw = el.textContent ? el.textContent.trim() : "";
                    if (!hasChildren && raw.length > 0) text = raw;
                } catch (e) {
                    text = null;
                }
                const obj = {
                    tag: tagName,
                    text: text,
                    href: tagName === 'a' ? (el.href || '') : undefined,
                    children: []
                };
                for (let i = 0; i < el.children.length; i++) {
                    const child = walk(el.children[i]);
                    if (child) obj.children.push(child);
                }
                return obj;
            };
            return walk(document.body);
        }
    """)

    console.clear()
    lines = print_dom(dom_tree)
    top_panel = Group(*lines)

    bottom_panel_text = "← ↑ ↓ →  |  Search: "
    bottom_panel = Panel(bottom_panel_text, style="bold blue")

    combined = Group(top_panel, bottom_panel)

    with Live(combined, console=console, refresh_per_second=10) as live:
        while True:
            live.update(combined)

        # choice = input("\nEnter link number to follow (or q to quit): ")
        # if choice.lower() == "q":
        #     break
        # if not (choice.isdigit() and int(choice) in link_map):
        #     console.print("Link is not reachable.", style="bold red")
        #     continue

        # url = link_map[int(choice)] or ""
        # if not url_validate(url):
        #     console.print(f"Skipped navigation to invalid or unsupported URL: {url!r}", style="bold yellow")
        #     continue

        # try:
        #     page.goto(url, wait_until='load')
        #     console.print(f"Navigated to: {url}", style="bold green")
        # except PlaywrightError as e:
        #     console.print(f"[red]Navigation failed:[/red] {e}", style="bold red")
        # except Exception as e:
        #     console.print(f"[red]Unexpected error during navigation:[/red] {e}", style="bold red")

    browser.close()