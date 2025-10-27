from playwright.sync_api import sync_playwright, Error as PlaywrightError
from rich.console import Console
from rich.text import Text
from urllib.parse import urlparse

console = Console()
    
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
    global link_counter
    if node is None:
        return

    spacer = " " * indent
    prefix = tag_prefix(node['tag'])

    if node['tag'] == 'a':
        href = node.get('href', '')
        text = node.get('text', href) or href or '(no-text)'
        link_text = Text(f"{link_counter}) Link: {text} -> {href}", style="bold blue underline")
        console.print(spacer, link_text)
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
            else:
                style = "dim"
            console.print(spacer + prefix + node['text'], style=style)

    for child in node.get("children", []):
        print_dom(child, indent + 1)

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://github.com/topics/ecommerce-website")

    while True:
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
        print_dom(dom_tree)

        choice = input("\nEnter link number to follow (or q to quit): ")
        if choice.lower() == "q":
            break
        if not (choice.isdigit() and int(choice) in link_map):
            console.print("Link is not reachable.", style="bold red")
            continue

        url = link_map[int(choice)] or ""
        if not url_validate(url):
            console.print(f"Skipped navigation to invalid or unsupported URL: {url!r}", style="bold yellow")
            continue

        try:
            page.goto(url, wait_until='load')
            console.print(f"Navigated to: {url}", style="bold green")
        except PlaywrightError as e:
            console.print(f"[red]Navigation failed:[/red] {e}", style="bold red")
        except Exception as e:
            console.print(f"[red]Unexpected error during navigation:[/red] {e}", style="bold red")

    browser.close()