import requests
import sys
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md

# --- Interactive Configuration ---
start_url = input("Enter the URL to convert (e.g., https://docs.example.com): ").strip()
if not start_url.startswith("http"):
    start_url = "https://" + start_url

print("\n(Optional) Enter a path to restrict crawling (e.g., /docs/)")
path_scope = input("Leave empty to scan the whole domain: ").strip()

output_filename = "llms.txt"

# Auto-extract domain
parsed_start = urlparse(start_url)
target_domain = parsed_start.netloc

print(f"\n🎯 Target Domain: {target_domain}")
if path_scope:
    print(f"🔒 Scope Restricted to: {path_scope}")

# --- Helper Functions ---

def clean_url(url):
    """Normalize URL by removing fragments."""
    parsed = urlparse(url)
    return parsed.scheme + "://" + parsed.netloc + parsed.path

def is_in_scope(url):
    """Checks if the URL matches the domain and optional path scope."""
    parsed = urlparse(url)
    
    # 1. Check Domain
    if parsed.netloc != target_domain:
        return False
    
    # 2. Check Protocol
    if parsed.scheme and parsed.scheme not in ['http', 'https']:
        return False
        
    # 3. Check Path Scope
    if path_scope and not parsed.path.startswith(path_scope):
        return False
        
    return True

def fetch_and_convert(url):
    """Fetches HTML and converts it to clean Markdown."""
    try:
        response = requests.get(url, timeout=10)
        if 'text/html' not in response.headers.get('Content-Type', ''):
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Remove noise (Navs, Footers, Sidebars)
        # Adjust these selectors based on the specific website structure if needed
        for tag in soup(['nav', 'footer', 'script', 'style', 'noscript', 'iframe', 'svg']):
            tag.decompose()

        # 2. Try to find the main content to avoid wrapping clutter
        content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
        
        if not content:
            return None

        # 3. Convert to Markdown
        # heading_style="ATX" ensures # Header format instead of underlines
        markdown_text = md(str(content), heading_style="ATX", strip=['a', 'img']) 
        
        # 4. Clean up excessive newlines
        clean_text = "\n".join([line.strip() for line in markdown_text.splitlines() if line.strip()])
        
        return clean_text, soup.title.string if soup.title else url

    except Exception as e:
        print(f"⚠️  Error processing {url}: {e}")
        return None, None

# --- Main Crawler & Generator ---

def generate_llms_txt():
    visited = set()
    to_visit = [start_url]
    
    # Open file immediately to write as we go (saves memory on large sites)
    with open(output_filename, "w", encoding="utf-8") as f:
        
        # Write Header
        f.write(f"# Documentation for {target_domain}\n")
        f.write(f"Source: {start_url}\n")
        f.write(f"Generated via custom script\n\n")
        f.write("---\n\n")

        print(f"\n🕷️  Starting crawl and generation...")

        while to_visit:
            current_url = to_visit.pop(0)
            clean_current = clean_url(current_url)
            
            if clean_current in visited:
                continue

            # Scope Check
            if not is_in_scope(clean_current):
                continue
            
            visited.add(clean_current)
            print(f"   Processing: {clean_current}")
            
            # Fetch & Convert
            markdown_content, page_title = fetch_and_convert(clean_current)
            
            if markdown_content:
                # Write to file
                f.write(f"# {page_title}\n")
                f.write(f"Original URL: {clean_current}\n\n")
                f.write(markdown_content)
                f.write("\n\n---\n\n") # Page Separator

                # Find new links
                try:
                    response = requests.get(clean_current, timeout=5)
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    for link in soup.find_all('a', href=True):
                        full_url = urljoin(clean_current, link['href'])
                        final_url = clean_url(full_url)
                        
                        if final_url not in visited and final_url not in to_visit:
                            if is_in_scope(final_url):
                                to_visit.append(final_url)
                except:
                    pass # Ignore link finding errors, we already got the content

    print(f"\n✅ Done! Saved to {os.path.abspath(output_filename)}")
    print(f"📊 Total pages processed: {len(visited)}")

if __name__ == "__main__":
    generate_llms_txt()