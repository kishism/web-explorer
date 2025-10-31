from time import sleep
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from rich.console import Console, Group
from rich.text import Text
from rich.live import Live
from rich.panel import Panel
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from rich.traceback import install
import readchar

console = Console()
install()

selected_link = 1
scroll_offset = 1
linked_line_map = {}
link_map = {}
global_line_index = 0
PAGE_SIZE = console.size.height - 4

def get_page_title(page) -> str:
    try:
        title = page.title()
        return title if title else "(No title)"
    except Exception:
        return "(Unknown Page Title)"

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
    global link_counter, selected_link, scroll_offset, global_line_index
    if node is None:
        return

    spacer = " " * indent
    prefix = tag_prefix(node['tag'])

    if node['tag'] == 'a':
        href = node.get('href', '')
        text = node.get('text', href) or href or '(no-text)'
        style= "bold blue underline"
        link_text = Text(f"{link_counter}) Link: {text} -> {href}", style=style)
        # console.print(spacer, link_text)
        spacer_obj = Text(spacer)
        lines.append(spacer_obj + link_text)

        linked_line_map[link_counter] = global_line_index
        global_line_index += 1
        # print("global_line_index", global_line_index)
        link_map[link_counter] = href
        link_counter += 1
        # print("link_counter", link_counter)

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
    # index.html is empty
    soup = BeautifulSoup(html, "html.parser")
    welcome_text = soup.pre.string if soup.pre else "Welcome to Web Explorer"
    sub_text = soup.p.string if soup.p else "Text-based browser environment"

    welcome_rich = Text(welcome_text, style="light_slate_blue", justify="center")
    sub_rich = Text(sub_text, style="white", justify="center")

    banner = Panel.fit(
        Text.assemble(welcome_rich, "\n", sub_rich),
        border_style="grey93",
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

def search_mode(page, live):
    live.stop()
    console.print("Search mode [Enter URL to visit]: ", style="bold cyan", end="")
    url_input = input().strip()

    if not url_validate(url_input):
        console.print(f"[yellow]Invalid URL: {url_input}[/yellow]")
        input("Press Enter to continue...")
        live.start()
        return None
    try:
        browse_or_fail(page, url_input)
        page.goto(url_input, wait_until='load')
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
        return dom_tree
    except Exception as e:
        console.print(f"[red]Navigation failed:[/red] {e}", style="bold red")
        return None

    finally:
        live.start()

show_welcome_banner()  

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    result = browse_or_fail(page, "http://127.0.0.1:5500/index.html", timeout=10000)

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
    
    with Live(console=console, refresh_per_second=20) as live:
        while True:
            link_counter = 1
            global_line_index = 0
            linked_line_map.clear()
            link_map.clear()
            lines = print_dom(dom_tree)

            selected_line_index = linked_line_map.get(selected_link, 0)

            page_title = get_page_title(page)
            title_line = Text(f"{page_title}", style="bold cyan", justify="center")
         
            if 0 <= selected_line_index < global_line_index:
                lines[selected_line_index].stylize("reverse medium_violet_red")

            if selected_line_index < scroll_offset:
                scroll_offset = selected_line_index
            elif selected_line_index >= scroll_offset + PAGE_SIZE:
                scroll_offset = selected_line_index - PAGE_SIZE + 1

            viewport_lines = lines[scroll_offset : scroll_offset + PAGE_SIZE]
            top_panel = Group(title_line, *viewport_lines)

            bottom_panel_text = "← ↑ ↓ →  |  Enter to follow | Q to quit | S (or) / to Search "
            bottom_panel = Panel(bottom_panel_text, style="bold white")

            combined = Group(top_panel, bottom_panel)
            live.update(combined)

            max_link = max(link_map.keys()) if link_map else 1
            selected_link = min(max_link, max(1, selected_link))

            link_clickable = {
                line_idx: link_num for link_num,
                line_idx in linked_line_map.items()
            }

            # print(f"repr: {repr(key)}")
            # if key == readchar.key.UP:
            #     print("You pressed UP")
            # elif key == readchar.key.DOWN:
            #     print("You pressed DOWN")
            # elif key == readchar.key.LEFT:
            #     print("You pressed LEFT")
            # elif key == readchar.key.RIGHT:
            #     print("You pressed RIGHT")
            # elif key == readchar.key.ENTER:
            #     break

            key = readchar.readkey()
            if key == '\x00':
                key2 = readchar.readkey()
                key = '\x00' + key2
            if key in ('\x00H', '\xe0H'):  # Up
                selected_link = max(1, selected_link - 1)
            elif key in ('\x00P', '\xe0P'):  # Down
                selected_link = min(max_link, selected_link + 1)
            elif key in ('\x00M', '\xe0M'):  # Right
                console.print("[yellow] Inactionable [/yellow]")
            elif key in ('\x00K', '\xe0K'):  # Left
                console.print("[yellow] Inactionable [/yellow]")
            elif key.lower() in ('s', '/'):
                new_dom = search_mode(page, live)
                if new_dom:
                    dom_tree = new_dom
                    selected_link = 1
                    scroll_offset = 0
                    linked_line_map.clear()
                    link_map.clear()
                    console.clear()
            elif key == '\r':
                url = link_map.get(selected_link)
                print(url)
                link_num = link_clickable.get(selected_line_index)
                print(link_num)
                if link_num:
                    url = link_map[link_num]
                    if url and url_validate(url):
                        try: 
                            browse_or_fail(page, url)
                            page.goto(url, wait_until='load')
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
                            selected_link = 1
                        except Exception as e:
                            console.print(f"[red]Navigation failed:[/red] {e}", style="bold red")
            elif key.lower() == 'q':
                print(key)
                break

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