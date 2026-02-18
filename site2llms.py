import requests
import sys
import os
import hashlib
import re
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

# --- Intelligent Compression Engine ---

class ContextCompressor:
    def __init__(self, redundancy_threshold=3):
        # Maps text_hash -> count of how many times we've seen this block
        self.block_hashes = {} 
        self.redundancy_threshold = redundancy_threshold
        
        # Regex patterns for "low value" lines (navigation clutter, social buttons)
        self.noise_patterns = [
            re.compile(r'^(back to top|read more|next|previous|menu|close)$', re.I),
            re.compile(r'^© \d{4}', re.I), # Simple copyright lines
            re.compile(r'^\s*[\W_]+\s*$'), # Lines that are just symbols/separators
        ]

    def _hash_block(self, text):
        """Returns a simple hash for a text block."""
        return hashlib.md5(text.strip().encode('utf-8')).hexdigest()

    def is_noise(self, line):
        """Checks if a single line is likely navigation junk."""
        if len(line.strip()) < 3: # Skip very short lines/artifacts
            return True
        for pattern in self.noise_patterns:
            if pattern.search(line.strip()):
                return True
        return False

    def normalize_layout(self, text):
        """
        Detects and reformats unintentional empty lines.
        1. Trims trailing whitespace from every line (turns '   ' into '').
        2. Collapses 3+ consecutive newlines into 2 (standard paragraph break).
        """
        if not text:
            return ""
        
        # Step 1: Strip trailing whitespace from every individual line
        # This fixes lines that look empty but contain spaces/tabs
        lines = [line.rstrip() for line in text.splitlines()]
        text = "\n".join(lines)

        # Step 2: Collapse consecutive newlines
        # Replaces 3 or more newlines with exactly 2 (Standard Markdown spacing)
        # This removes the massive gaps often left by removed HTML elements
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def compress(self, markdown_text):
        """
        1. Normalizes whitespace (Fixes empty lines).
        2. Breaks text into blocks (paragraphs).
        3. Filters out globally repeating blocks (redundancy).
        4. Filters out heuristic noise.
        """
        if not markdown_text:
            return ""

        # --- NEW: Pre-process to fix empty lines before block analysis ---
        markdown_text = self.normalize_layout(markdown_text)

        # Split by double newline to identify paragraphs/blocks
        blocks = markdown_text.split('\n\n')
        clean_blocks = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # 1. Heuristic Check (Skip generic navigation words)
            if self.is_noise(block):
                continue

            # 2. Global Redundancy Check
            # We don't filter headers (#) or code blocks (```) to preserve structure
            if not block.startswith('#') and not block.startswith('`'):
                block_hash = self._hash_block(block)
                
                # Increment count
                current_count = self.block_hashes.get(block_hash, 0)
                self.block_hashes[block_hash] = current_count + 1

                # If we've seen this exact paragraph too many times, skip it
                if current_count >= self.redundancy_threshold:
                    continue

            clean_blocks.append(block)

        # Reassemble with clean spacing
        return '\n\n'.join(clean_blocks)

# Initialize the compressor
compressor = ContextCompressor(redundancy_threshold=3)

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
            return None, None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Remove noise (Navs, Footers, Sidebars)
        for tag in soup(['nav', 'footer', 'script', 'style', 'noscript', 'iframe', 'svg', 'header', 'aside']):
            tag.decompose()

        # 2. Try to find the main content
        content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
        
        if not content:
            return None, None

        # 3. Convert to Markdown
        markdown_text = md(str(content), heading_style="ATX", strip=['a', 'img']) 
        
        return markdown_text, soup.title.string if soup.title else url

    except Exception as e:
        print(f"⚠️  Error processing {url}: {e}")
        return None, None

# --- Main Crawler & Generator ---

def generate_llms_txt():
    visited = set()
    to_visit = [start_url]
    
    # Open file immediately to write as we go
    with open(output_filename, "w", encoding="utf-8") as f:
        
        # Write Header
        f.write(f"# Documentation for {target_domain}\n")
        f.write(f"Source: {start_url}\n")
        f.write(f"Generated via custom script with Context Compression\n\n")
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
            raw_markdown, page_title = fetch_and_convert(clean_current)
            
            if raw_markdown:
                # --- APPLY COMPRESSION HERE ---
                compressed_content = compressor.compress(raw_markdown)
                
                # Only write if there is meaningful content left
                if len(compressed_content.strip()) > 50:
                    f.write(f"# {page_title}\n")
                    f.write(f"Original URL: {clean_current}\n\n")
                    f.write(compressed_content)
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
                    pass 

    print(f"\n✅ Done! Saved to {os.path.abspath(output_filename)}")
    print(f"📊 Total pages processed: {len(visited)}")

if __name__ == "__main__":
    generate_llms_txt()