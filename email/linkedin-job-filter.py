#!/usr/bin/env python3
"""
LinkedIn Job Email Filter
Processes unread LinkedIn job emails and sends a filtered summary.
"""

import subprocess
import json
import re
import sys
import os
from datetime import datetime, date
from typing import List, Dict, Any, Set
from html.parser import HTMLParser
import urllib.parse
import time
import base64

# Global variable to store the Gmail account
GOG_ACCOUNT = None

class HTMLTextExtractor(HTMLParser):
    """Extract text content from HTML."""
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return ''.join(self.text)

def load_exclusion_list() -> Set[str]:
    """Load job IDs from the exclusion list file."""
    # Use the exclusion file in the same directory as the script
    script_dir = os.path.dirname(os.path.realpath(__file__))
    exclusion_file = os.path.join(script_dir, 'linkedin-jobs-exclusions.txt')
    excluded_ids = set()

    if not os.path.exists(exclusion_file):
        return excluded_ids

    try:
        with open(exclusion_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Extract job ID (first part before |)
                parts = line.split('|')
                if parts:
                    job_id = parts[0].strip()
                    if job_id:
                        excluded_ids.add(job_id)
        print(f"Loaded {len(excluded_ids)} jobs from exclusion list.")
    except Exception as e:
        print(f"Warning: Could not load exclusion list: {e}", file=sys.stderr)

    return excluded_ids

def load_embargo_dates() -> Dict[str, date]:
    """Load company embargo dates from JSON config file.

    Returns a dict mapping lowercase company name to the embargo date.
    Jobs from a company are excluded on or before its embargo date.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    embargo_file = os.path.join(script_dir, 'linkedin-jobs-embargo.json')

    if not os.path.exists(embargo_file):
        return {}

    try:
        with open(embargo_file, 'r') as f:
            raw = json.load(f)
        embargo_dates = {}
        for company, date_str in raw.items():
            embargo_dates[company.lower()] = date.fromisoformat(date_str)
        if embargo_dates:
            print(f"Loaded {len(embargo_dates)} company embargo date(s).")
        return embargo_dates
    except Exception as e:
        print(f"Warning: Could not load embargo dates: {e}", file=sys.stderr)
        return {}


def get_embargo_date(company_name: str, embargo_dates: Dict[str, date]):
    """Return the embargo date for this company, or None if not embargoed.

    Matches both exact names and names that start with an embargoed company
    (e.g. "Microsoft AI" matches the "microsoft" embargo).
    """
    name_lower = company_name.lower()
    # Try exact match first
    embargo_date = embargo_dates.get(name_lower)
    # Fall back to prefix match (e.g. "microsoft ai" starts with "microsoft")
    if embargo_date is None:
        for embargoed_name, edate in embargo_dates.items():
            if name_lower.startswith(embargoed_name):
                embargo_date = edate
                break
    return embargo_date


def is_company_embargoed(company_name: str, embargo_dates: Dict[str, date]) -> bool:
    """Return True if today's date is on or before the embargo date for this company."""
    embargo_date = get_embargo_date(company_name, embargo_dates)
    if embargo_date is None:
        return False
    return date.today() <= embargo_date


def run_gog_command(args: List[str], account: str = None) -> Dict[str, Any]:
    """Run a gog command and return JSON output."""
    try:
        # Use global account if not provided
        if account is None:
            account = GOG_ACCOUNT

        # Build command with account if provided
        cmd = ['gog']
        if account:
            cmd.extend(['--account', account])
        cmd.extend(args)

        # Read keyring passphrase from file outside the git tree.
        passphrase_file = os.path.expanduser('~/.config/gogcli/keyring_passphrase')
        env = os.environ.copy()
        if os.path.exists(passphrase_file):
            with open(passphrase_file) as f:
                env['GOG_KEYRING_PASSWORD'] = f.read().strip()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)

        stdout = result.stdout.strip()
        if stdout:
            return json.loads(stdout)
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Error running gog command: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        return {}

def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML content."""
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()

def extract_job_id_from_url(url: str) -> str:
    """Extract a job ID from any job URL (LinkedIn or direct company career pages).

    Tries LinkedIn patterns first, then falls back to extracting a trailing
    numeric ID from the URL path (e.g. Netflix, Databricks career pages).
    """
    # LinkedIn: /jobs/view/4365006239 or /job/4365006239
    m = re.search(r'/jobs?/(?:view/)?(\d+)', url)
    if m:
        return m.group(1)
    # Non-LinkedIn career pages often have a numeric ID at the end of the path
    # e.g. .../sr-staff-software-engineer---data-platform-7823561002
    # or  .../790312856978-senior-engineering-manager-...
    path = urllib.parse.urlparse(url).path.rstrip('/')
    last_segment = path.rsplit('/', 1)[-1] if '/' in path else path
    # ID at the end after a hyphen: ...-7823561002
    m = re.search(r'-(\d{5,})$', last_segment)
    if m:
        return m.group(1)
    # ID at the start before a hyphen: 790312856978-...
    m = re.match(r'(\d{5,})-', last_segment)
    if m:
        return m.group(1)
    # Fallback: use the last path segment as identifier (e.g. Workday URLs
    # like .../job/Senior-Software-Engineer-AI-Infrastructure)
    if last_segment:
        return last_segment
    return None


def extract_linkedin_job_links(email_body: str) -> List[str]:
    """Extract LinkedIn job posting URLs from email body."""
    # Pattern for LinkedIn job links
    patterns = [
        r'https://www\.linkedin\.com/jobs/view/\d+',
        r'https://www\.linkedin\.com/comm/jobs/view/\d+',
        r'https://[a-z]+\.linkedin\.com/jobs/view/\d+',
    ]

    links = set()
    for pattern in patterns:
        matches = re.findall(pattern, email_body)
        links.update(matches)

    return list(links)

# Cache for Yahoo Finance public/private lookups (persisted to disk)
_company_public_cache: Dict[str, bool] = None
_company_cache_file: str = None

# Companies known to be private that Yahoo Finance may falsely match
_KNOWN_PRIVATE_COMPANIES = {
    'modular',
}

# Brand names that differ from their legal/trading name on Yahoo Finance
_COMPANY_ALIASES = {
    'instacart': 'Maplebear',
    'google': 'Alphabet',
    'facebook': 'Meta Platforms',
    'github': 'Microsoft',
    'amazon web services (aws)': 'Amazon',
    'aws': 'Amazon',
    'twitch': 'Amazon',
    'linkedin': 'Microsoft',
}

def _get_company_cache() -> Dict[str, bool]:
    global _company_public_cache, _company_cache_file
    if _company_public_cache is not None:
        return _company_public_cache
    script_dir = os.path.dirname(os.path.realpath(__file__))
    _company_cache_file = os.path.join(script_dir, 'linkedin-company-cache.json')
    try:
        if os.path.exists(_company_cache_file):
            with open(_company_cache_file) as f:
                _company_public_cache = json.load(f)
        else:
            _company_public_cache = {}
    except Exception:
        _company_public_cache = {}
    return _company_public_cache

def _save_company_cache():
    global _company_public_cache, _company_cache_file
    if _company_public_cache is None or _company_cache_file is None:
        return
    try:
        with open(_company_cache_file, 'w') as f:
            json.dump(_company_public_cache, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Warning: Could not save company cache: {e}", file=sys.stderr)

def _normalize_company_name(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation for fuzzy matching."""
    name = name.lower()
    name = re.sub(r'\b(inc\.?|llc\.?|corp\.?|ltd\.?|co\.?|group|holdings?|platforms?|technologies|technology|systems|solutions|international|services)\b\.?', ' ', name)
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    return ' '.join(name.split())

def _yahoo_finance_is_public(company_name: str) -> bool:
    """Query Yahoo Finance to check if the company is a publicly traded equity."""
    try:
        encoded = urllib.parse.quote(company_name)
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={encoded}&quotesCount=5&newsCount=0"
        result = subprocess.run(
            ['curl', '-s', '--max-time', '5', '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return True  # Fail open on network error

        data = json.loads(result.stdout)
        quotes = data.get('quotes', [])

        norm_search = _normalize_company_name(company_name)
        search_words = {w for w in norm_search.split() if len(w) > 2}

        for quote in quotes:
            if quote.get('quoteType') != 'EQUITY':
                continue
            long_name = quote.get('longname') or quote.get('shortname') or ''
            norm_result = _normalize_company_name(long_name)
            result_words = {w for w in norm_result.split() if len(w) > 2}
            if not search_words or not result_words:
                continue
            overlap = search_words & result_words
            # Match if at least 60% of search words appear in the result name
            if len(overlap) >= max(1, len(search_words) * 0.6):
                return True

        return False
    except Exception as e:
        print(f"    Warning: Yahoo Finance check failed for {company_name}: {e}", file=sys.stderr)
        return True  # Fail open on unexpected error
    finally:
        time.sleep(0.3)  # Avoid rate-limiting

def is_public_company(company_name: str, job_description: str) -> bool:
    """Check if a company is publicly traded using Yahoo Finance API with local caching."""
    cache = _get_company_cache()

    if company_name in cache:
        return cache[company_name]

    # Known private companies should never be treated as public
    if company_name.lower() in _KNOWN_PRIVATE_COMPANIES:
        cache[company_name] = False
        _save_company_cache()
        return False

    # Check for a brand-name alias before querying
    alias = _COMPANY_ALIASES.get(company_name.lower())
    search_name = alias if alias else company_name
    result = _yahoo_finance_is_public(search_name)

    # Fall back to job description indicators if Yahoo Finance drew a blank
    if not result:
        public_indicators = ['nasdaq:', 'nyse:', 'publicly traded', 'publicly-traded']
        if any(ind in job_description.lower() for ind in public_indicators):
            result = True

    cache[company_name] = result
    _save_company_cache()
    return result

# Cache for job data (persisted to disk)
_job_cache: Dict[str, dict] = None
_job_cache_file: str = None

def _get_job_cache() -> Dict[str, dict]:
    global _job_cache, _job_cache_file
    if _job_cache is not None:
        return _job_cache
    script_dir = os.path.dirname(os.path.realpath(__file__))
    _job_cache_file = os.path.join(script_dir, 'linkedin-job-cache.json')
    try:
        if os.path.exists(_job_cache_file):
            with open(_job_cache_file) as f:
                _job_cache = json.load(f)
        else:
            _job_cache = {}
    except Exception:
        _job_cache = {}
    return _job_cache

def _save_job_cache():
    global _job_cache, _job_cache_file
    if _job_cache is None or _job_cache_file is None:
        return
    try:
        with open(_job_cache_file, 'w') as f:
            json.dump(_job_cache, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Warning: Could not save job cache: {e}", file=sys.stderr)

def fetch_salary_from_job_page(job_url: str) -> str:
    """Fetch salary information from LinkedIn job page."""
    try:
        # Clean the URL: convert /comm/jobs/view/ to /jobs/view/ and remove tracking params
        # Extract job ID
        job_id_match = re.search(r'/jobs/view/(\d+)', job_url)
        if not job_id_match:
            return None

        job_id = job_id_match.group(1)

        # Check job cache for previously fetched salary
        cache = _get_job_cache()
        if job_id in cache:
            cached = cache[job_id]
            salary = cached.get('salary')
            if salary is not None or 'salary' in cached:
                return salary

        # Construct clean URL
        clean_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

        # Use curl with browser headers to fetch the job page
        result = subprocess.run([
            'curl', '-s', '-L',
            '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            clean_url
        ],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode != 0:
            return None

        html_content = result.stdout

        # Look for salary patterns in the HTML (in priority order)
        salary_patterns = [
            # Format: $272,000.00/yr - $431,250.00/yr
            r'\$([\d,]+)\.00/yr - \$([\d,]+)\.00/yr',
            # Format: base salary range is 272,000 USD - 431,250 USD
            r'base salary range is ([\d,]+) USD - ([\d,]+) USD',
            # Format: $272,000 - $431,250
            r'\$([\d,]+) - \$([\d,]+)',
        ]

        salary = None
        for pattern in salary_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                # Extract the numbers
                low = match.group(1).replace(',', '')
                high = match.group(2).replace(',', '')
                # Convert to K format
                salary = f"${int(low)//1000}K-${int(high)//1000}K"
                break

        # Cache the result (including None to avoid re-fetching)
        cache.setdefault(job_id, {})['salary'] = salary
        _save_job_cache()
        return salary
    except Exception as e:
        print(f"    Warning: Could not fetch salary from {job_url}: {e}", file=sys.stderr)
        return None

def extract_compensation(text: str) -> str:


    """Extract pay range information from text."""
    # Patterns for compensation/pay ranges (prioritized order)
    comp_patterns = [
        # Format: "The base salary range is 272,000 USD - 431,250 USD"
        r'(?:base salary range|salary range|pay range)\s+is\s+[\d,]+\s+USD\s*-\s*[\d,]+\s+USD',
        # LinkedIn format: $198K-$343K / year or $200K/yr+
        r'\$[\d,]+K?\s*-\s*\$[\d,]+K?\s*/\s*ye?a?r?',
        r'\$[\d,]+K?\s*/\s*ye?a?r?\+',
        # Standard ranges
        r'\$[\d,]+[Kk]?\s*-\s*\$[\d,]+[Kk]?',
        r'\$[\d,]+[Kk]?\+',
        r'[\d,]+[Kk]\s*-\s*[\d,]+[Kk]',
        # Explicit labels
        r'(?:base salary|salary range|compensation|pay range):?\s*\$?[\d,]+[Kk]?\s*-\s*\$?[\d,]+[Kk]?',
        r'(?:base salary|compensation):?\s*\$?[\d,]+[Kk]?\+',
    ]

    for pattern in comp_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            comp = match.group(0)
            # Clean up and standardize
            comp = re.sub(r'\s+', ' ', comp)
            comp = re.sub(r'yr', 'year', comp, flags=re.IGNORECASE)
            # Convert "272,000 USD - 431,250 USD" to "$272K-$431K"
            if 'USD' in comp:
                numbers = re.findall(r'[\d,]+', comp)
                if len(numbers) >= 2:
                    low = int(numbers[0].replace(',', ''))
                    high = int(numbers[1].replace(',', ''))
                    comp = f"${low//1000}K-${high//1000}K"
            return comp

    return "Not specified"

def extract_location(text: str) -> str:
    """Extract location information from text."""
    # Common location patterns
    location_patterns = [
        r'(?:location|based in|office in):?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s*[A-Z]{2})',
        r'([A-Z][a-z]+,\s*[A-Z]{2})',
        r'(Remote|Hybrid|On-site)',
        r'(San Francisco|New York|Seattle|Austin|Boston|Los Angeles|Chicago|Denver|Portland|Miami)',
    ]

    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)

    return "Not specified"

def get_manual_job_emails() -> List[Dict[str, Any]]:
    """Fetch emails with subject 'linkedin-jobs' containing manually shared job links.

    Returns a list of dicts with 'thread_id' and 'message_ids' keys,
    since gog search returns thread IDs which may differ from message IDs.
    """
    print("Searching for manually shared job emails...")

    search_query = 'subject:linkedin-jobs'

    result = run_gog_command([
        'gmail', 'search',
        search_query,
        '--max', '10',
        '--json'
    ])

    if not result or 'threads' not in result:
        return []

    threads = result.get('threads', []) or []
    entries = []

    for thread in threads:
        thread_id = thread.get('id')
        if not thread_id:
            continue

        # Resolve actual message IDs via thread get
        thread_data = run_gog_command([
            'gmail', 'thread', 'get', thread_id, '--json'
        ])

        message_ids = []
        thread_info = thread_data.get('thread', {})
        for msg in thread_info.get('messages', []):
            msg_id = msg.get('id')
            if msg_id:
                message_ids.append(msg_id)

        entries.append({
            'thread_id': thread_id,
            'message_ids': message_ids or [thread_id],
        })

    return entries


def delete_manual_job_emails(message_ids: List[str]):
    """Delete processed manual job emails."""
    if not message_ids:
        return
    print(f"Deleting {len(message_ids)} manual job email(s)...")
    for msg_id in message_ids:
        run_gog_command(['gmail', 'thread', 'modify', msg_id, '--add', 'TRASH', '--json'])
    print(f"Deleted {len(message_ids)} manual job email(s).")


def extract_urls_from_text(text: str) -> List[str]:
    """Extract URLs from plain text."""
    url_pattern = r'https?://[^\s<>"\']+'
    urls = re.findall(url_pattern, text)
    return [url.rstrip('.,;)') for url in urls]


def _extract_company_from_url(url: str) -> str:
    """Extract company name from a career page URL."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ''
    path = parsed.path or ''

    # Job board platforms where company is in the path
    job_board_patterns = [
        (r'greenhouse\.io', r'/([^/]+)'),
        (r'ashbyhq\.com', r'/([^/]+)'),
        (r'lever\.co', r'/([^/]+)'),
        (r'workable\.com', r'/([^/]+)'),
    ]

    for domain_pattern, path_pattern in job_board_patterns:
        if re.search(domain_pattern, hostname):
            match = re.match(path_pattern, path)
            if match:
                company = match.group(1)
                # Try to split concatenated names (e.g., "andurilindustries" → "anduril industries")
                # Insert space before common suffixes
                company = re.sub(r'(industries|technologies|labs|systems|sciences|robotics|security|analytics)$',
                                 r' \1', company, flags=re.IGNORECASE)
                return company.replace('-', ' ').replace('_', ' ').title().strip()

    # Extract from domain name
    parts = hostname.split('.')
    subdomains_to_remove = {'www', 'careers', 'jobs', 'job', 'boards', 'job-boards', 'apply'}
    domain_parts = [p for p in parts if p not in subdomains_to_remove and len(p) > 2]

    if domain_parts:
        company = domain_parts[0]
        return company.replace('-', ' ').replace('_', ' ').title()

    return "Unknown"


def _title_from_url_path(url: str) -> str:
    """Extract a readable job title from a URL path as a fallback."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip('/')
    # Get last meaningful path segment
    segments = [s for s in path.split('/') if s and not re.match(r'^[\da-f-]{8,}$', s)]
    if segments:
        slug = segments[-1]
        # Convert slug to readable title
        title = slug.replace('-', ' ').replace('_', ' ')
        # Title case, but preserve known acronyms
        title = ' '.join(w.upper() if len(w) <= 3 and w.isalpha() else w.capitalize()
                         for w in title.split())
        return title
    return ''


def _is_garbage_title(title: str) -> bool:
    """Check if a title is garbage (Cloudflare challenge, HTML content, etc.)."""
    if not title:
        return True
    garbage_markers = ['just a moment', 'checking your browser', 'please wait',
                       'access denied', 'data-next-head', '<meta', '<link',
                       'viewport', 'initial-scale']
    title_lower = title.lower()
    return any(marker in title_lower for marker in garbage_markers) or len(title) > 200


def fetch_job_from_career_page(url: str) -> Dict[str, str]:
    """Fetch job details from a career/jobs page URL."""
    try:
        result = subprocess.run([
            'curl', '-s', '-L',
            '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            url
        ],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode != 0:
            return None

        html = result.stdout

        # Extract title tag
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        page_title = title_match.group(1).strip() if title_match else ''

        # Extract og:title (property before content)
        og_title = ''
        og_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if og_match:
            og_title = og_match.group(1).strip()

        # Extract og:site_name (property before content)
        site_name = ''
        site_match = re.search(r'<meta\s+property=["\']og:site_name["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if site_match:
            site_name = site_match.group(1).strip()

        # Determine job title - og:title is usually cleaner
        job_title = og_title or page_title

        # Clean up title - remove company name suffixes/prefixes
        # Only use ' | ' and ' at ' for company extraction (reliable separators)
        # ' - ' is ambiguous (could be location, team, level)
        for sep in [' | ', ' at ']:
            if sep in job_title:
                parts = job_title.split(sep)
                job_title = parts[0].strip()
                if not site_name and len(parts) > 1:
                    site_name = parts[-1].strip()
                break
        else:
            # For ' - ' separators, only extract the title (first part), not company
            for sep in [' - ', ' — ', ' – ']:
                if sep in job_title:
                    parts = job_title.split(sep)
                    job_title = parts[0].strip()
                    break

        # Detect garbage titles and fall back to URL-based extraction
        if _is_garbage_title(job_title):
            job_title = _title_from_url_path(url)

        # Determine company name
        company = site_name or _extract_company_from_url(url)

        # Clean up company name
        company = re.sub(r'^(Careers?|Jobs?|Hiring)\s+(at|@)\s+', '', company, flags=re.IGNORECASE)
        company = re.sub(r'\s*(Careers?|Jobs?|Hiring)\s*$', '', company, flags=re.IGNORECASE).strip()

        # Decode HTML entities
        company = company.replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')
        job_title = job_title.replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')

        # Extract salary and location from the page
        salary = extract_compensation(html)
        location = extract_location(html)

        return {
            'title': job_title or 'Unknown Position',
            'company': company,
            'location': location,
            'salary': salary,
            'link': url,
        }
    except Exception as e:
        print(f"    Warning: Could not fetch {url}: {e}", file=sys.stderr)
        return None


def delete_old_summary_emails():
    """Delete all previous summary emails except the most recent one."""
    print("Cleaning up old summary emails...")

    # Search for all summary emails (read or unread)
    search_query = 'subject:"LinkedIn Job Opportunities"'

    result = run_gog_command([
        'gmail', 'search',
        search_query,
        '--max', '20',
        '--json'
    ])

    if not result or 'threads' not in result:
        return

    threads = result.get('threads', []) or []

    if threads and len(threads) > 0:
        print(f"Deleting {len(threads)} old summary email(s)...")
        for thread in threads:
            thread_id = thread.get('id')
            if thread_id:
                # Move to trash by adding TRASH label
                run_gog_command(['gmail', 'thread', 'modify', thread_id, '--add', 'TRASH', '--json'])
        print(f"Deleted {len(threads)} old summary email(s).")

def parse_previous_summary_emails() -> List[Dict[str, Any]]:
    """Parse jobs from previously sent summary emails."""
    print("Searching for previous summary emails...")

    # Search for our own summary emails from the last 24 hours
    search_query = 'subject:"LinkedIn Job Opportunities" newer_than:1d'

    result = run_gog_command([
        'gmail', 'search',
        search_query,
        '--max', '10',
        '--json'
    ])

    if not result or 'threads' not in result:
        return []

    threads = result.get('threads', []) or []
    print(f"Found {len(threads)} previous summary emails.")

    jobs = []
    for thread in threads:
        message_id = thread.get('id')
        if not message_id:
            continue

        details = get_email_details(message_id)
        body_html = details.get('body', '')

        if not body_html:
            continue

        # Parse job listings from HTML
        # Format: <div class="company">N. Company Name</div>
        #         <div class="title">Job Title</div>
        #         <div class="info">💰 Pay Range: $XK-$YK</div>
        #         <div class="info">📍 Location: ...</div>
        #         <a href="job_url">View Job Posting →</a>

        # Extract job blocks
        job_blocks = re.findall(r'<div class="job">(.*?)</div>\s*</div>', body_html, re.DOTALL)

        for block in job_blocks:
            # Extract company (format: "1. Company Name")
            company_match = re.search(r'<div class="company">(?:\d+\.\s+)?([^<]+)</div>', block)
            title_match = re.search(r'<div class="title">([^<]+)</div>', block)
            pay_match = re.search(r'💰 Pay Range:\s*([^<]+)</div>', block)
            location_match = re.search(r'📍 Location:\s*([^<]+)</div>', block)
            link_match = re.search(r'<a href="([^"]+)">', block)

            if company_match and link_match:
                company = company_match.group(1).strip()
                # Clean up company name - strip "Careers at" / "Jobs at" prefixes
                company = re.sub(r'^(Careers?|Jobs?|Hiring)\s+(at|@)\s+', '', company, flags=re.IGNORECASE)
                company = re.sub(r'\s*(Careers?|Jobs?|Hiring)\s*$', '', company, flags=re.IGNORECASE).strip()
                title = title_match.group(1).strip() if title_match else 'Unknown Title'
                # Skip entries where LinkedIn navigation text leaked into parsed title
                bad_titles = {'linkedin login, sign in', 'sign in', 'login', 'view on linkedin'}
                if title.lower() in bad_titles or 'linkedin login' in title.lower():
                    continue
                location = location_match.group(1).strip() if location_match else 'Not specified'
                # Skip entries where CSS leaked into location
                garbled_keywords = ['width', 'margin', 'padding', 'font-', 'color:']
                if any(kw in location.lower() for kw in garbled_keywords):
                    continue
                jobs.append({
                    'company': company,
                    'title': title,
                    'link': link_match.group(1).strip(),
                    'compensation': pay_match.group(1).strip() if pay_match else 'Not specified',
                    'location': location
                })

    print(f"Extracted {len(jobs)} jobs from previous summary emails.")
    return jobs

def get_unread_linkedin_emails() -> List[Dict[str, Any]]:
    """Fetch unread LinkedIn job emails."""
    print("Searching for LinkedIn emails...")

    # Search for unread emails from LinkedIn about jobs
    search_query = '(from:jobs-listings@linkedin.com OR from:jobs-noreply@linkedin.com OR from:jobalerts-noreply@linkedin.com OR from:messages-noreply@linkedin.com) newer_than:2d'

    result = run_gog_command([
        'gmail', 'search',
        search_query,
        '--max', '50',
        '--json'
    ])

    if not result or 'threads' not in result:
        return []

    return result.get('threads', []) or []

def get_email_details(message_id: str) -> Dict[str, Any]:
    """Get detailed information for a specific email."""
    result = run_gog_command([
        'gmail', 'get',
        message_id,
        '--json'
    ])

    return result

def mark_email_as_read(message_id: str):
    """Mark an email as read."""
    run_gog_command([
        'gmail', 'thread', 'modify',
        message_id,
        '--remove', 'UNREAD',
        '--json'
    ])

def get_company_tier(company_name: str, is_public: bool = True) -> int:
    """Classify company into tiers (1 = best, 4 = private companies)."""
    company_lower = company_name.lower()

    # Tier 1: FAANG + top tier tech companies
    tier1 = {
        'google', 'alphabet', 'meta', 'facebook', 'apple', 'amazon', 'netflix',
        'microsoft', 'nvidia', 'openai', 'anthropic', 'tesla', 'spacex',
        'stripe', 'databricks'
    }

    # Tier 2: Well-known large tech companies
    tier2 = {
        'salesforce', 'adobe', 'uber', 'lyft', 'airbnb', 'doordash', 'snowflake',
        'oracle', 'ibm', 'cisco', 'intel', 'amd', 'qualcomm', 'shopify',
        'atlassian', 'mongodb', 'elastic', 'twilio', 'okta', 'zoom', 'slack',
        'dropbox', 'pinterest', 'snap', 'twitter', 'reddit', 'roblox', 'unity',
        'servicenow', 'workday', 'splunk', 'crowdstrike', 'palo alto',
        'fortinet', 'cloudflare', 'datadog', 'gitlab', 'hashicorp', 'figma',
        'affirm', 'akamai', 'amgen', 'coinbase', 'hubspot', 'instacart',
        'mastercard', 'nutanix', 'sony', 'square', 'block', 'spotify',
        'roku', 'peloton', 'blue origin', 'mixpanel', 'sofi', 'visa',
        'backblaze', 'compass', 'upstart', 'vertex', 'workiva'
    }

    # Check tier 1 (regardless of public/private status)
    for t1_company in tier1:
        if re.search(r'\b' + re.escape(t1_company) + r'\b', company_lower):
            return 1

    # Check tier 2 (regardless of public/private status)
    for t2_company in tier2:
        if re.search(r'\b' + re.escape(t2_company) + r'\b', company_lower):
            return 2

    # Tier 4: Private companies not in tier 1/2
    if not is_public:
        return 4

    # Tier 3: Other public companies
    return 3

def send_summary_email(jobs: List[Dict[str, Any]], recipient: str):
    """Send a summary email with filtered job listings grouped by tier."""
    if not jobs:
        print("No jobs to send - all filtered out or none found.")
        return

    # Group jobs by tier
    tier1_jobs = []
    tier2_jobs = []
    tier3_jobs = []
    tier4_jobs = []

    for job in jobs:
        tier = get_company_tier(job['company'], job.get('is_public', True))
        if tier == 1:
            tier1_jobs.append(job)
        elif tier == 2:
            tier2_jobs.append(job)
        elif tier == 3:
            tier3_jobs.append(job)
        else:
            tier4_jobs.append(job)

    # Build email body
    email_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .tier {{ margin: 30px 0; }}
        .tier-header {{ font-size: 24px; font-weight: bold; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #ddd; }}
        .tier1 {{ color: #d4af37; }} /* Gold */
        .tier2 {{ color: #0066cc; }} /* Blue */
        .tier3 {{ color: #666; }} /* Gray */
        .tier4 {{ color: #996633; }} /* Brown */
        .job {{ margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background: #f9f9f9; }}
        .company {{ font-weight: bold; font-size: 18px; color: #0066cc; }}
        .title {{ font-size: 16px; margin: 5px 0; }}
        .info {{ color: #666; margin: 3px 0; }}
        .link {{ margin-top: 10px; }}
        a {{ color: #0066cc; text-decoration: none; }}
    </style>
</head>
<body>
    <h1>🎯 LinkedIn Job Opportunities</h1>
    <p><strong>{len(jobs)} jobs</strong> | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
"""

    # Tier 1: Top Companies
    if tier1_jobs:
        email_body += f"""
    <div class="tier">
        <div class="tier-header tier1">⭐ Tier 1: Top Companies ({len(tier1_jobs)} jobs)</div>
"""
        for i, job in enumerate(tier1_jobs, 1):
            email_body += f"""
        <div class="job">
            <div class="company">{i}. {job['company']}</div>
            <div class="title">{job.get('title', 'Job Opportunity')}</div>
            <div class="info">💰 Pay Range: {job['compensation']}</div>
            <div class="info">📍 Location: {job['location']}</div>
            <div class="link">
                <a href="{job['link']}">View Job Posting →</a>
            </div>
        </div>
"""
        email_body += "    </div>\n"

    # Tier 2: Great Companies
    if tier2_jobs:
        email_body += f"""
    <div class="tier">
        <div class="tier-header tier2">🌟 Tier 2: Great Companies ({len(tier2_jobs)} jobs)</div>
"""
        for i, job in enumerate(tier2_jobs, 1):
            email_body += f"""
        <div class="job">
            <div class="company">{i}. {job['company']}</div>
            <div class="title">{job.get('title', 'Job Opportunity')}</div>
            <div class="info">💰 Pay Range: {job['compensation']}</div>
            <div class="info">📍 Location: {job['location']}</div>
            <div class="link">
                <a href="{job['link']}">View Job Posting →</a>
            </div>
        </div>
"""
        email_body += "    </div>\n"

    # Tier 3: Good Companies
    if tier3_jobs:
        email_body += f"""
    <div class="tier">
        <div class="tier-header tier3">✨ Tier 3: Good Companies ({len(tier3_jobs)} jobs)</div>
"""
        for i, job in enumerate(tier3_jobs, 1):
            email_body += f"""
        <div class="job">
            <div class="company">{i}. {job['company']}</div>
            <div class="title">{job.get('title', 'Job Opportunity')}</div>
            <div class="info">💰 Pay Range: {job['compensation']}</div>
            <div class="info">📍 Location: {job['location']}</div>
            <div class="link">
                <a href="{job['link']}">View Job Posting →</a>
            </div>
        </div>
"""
        email_body += "    </div>\n"

    # Tier 4: Private Companies
    if tier4_jobs:
        email_body += f"""
    <div class="tier">
        <div class="tier-header tier4">🏢 Tier 4: Private Companies ({len(tier4_jobs)} jobs)</div>
"""
        for i, job in enumerate(tier4_jobs, 1):
            email_body += f"""
        <div class="job">
            <div class="company">{i}. {job['company']}</div>
            <div class="title">{job.get('title', 'Job Opportunity')}</div>
            <div class="info">💰 Pay Range: {job['compensation']}</div>
            <div class="info">📍 Location: {job['location']}</div>
            <div class="link">
                <a href="{job['link']}">View Job Posting →</a>
            </div>
        </div>
"""
        email_body += "    </div>\n"

    email_body += """
</body>
</html>
"""

    # Send email using gog with HTML body
    try:
        passphrase_file = os.path.expanduser('~/.config/gogcli/keyring_passphrase')
        env = os.environ.copy()
        if os.path.exists(passphrase_file):
            with open(passphrase_file) as f:
                env['GOG_KEYRING_PASSWORD'] = f.read().strip()

        subprocess.run([
            'gog', 'gmail', 'send',
            '--to', recipient,
            '--subject', f'LinkedIn Job Opportunities - {len(jobs)} Jobs',
            '--body-html', email_body
        ], check=True, env=env)

        print(f"Summary email sent to {recipient}")
    except subprocess.CalledProcessError as e:
        print(f"Error sending email: {e}", file=sys.stderr)

def parse_job_listings_from_body(body: str) -> List[Dict[str, str]]:
    """Parse individual job listings from LinkedIn email body."""
    jobs = []

    # Location patterns to filter out
    location_patterns = [
        r'^[A-Z][a-z]+,\s*[A-Z]{2}$',  # City, ST (e.g., "Seattle, WA")
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*,\s*[A-Z]{2}$',  # Multi-word city, ST (e.g., "San Francisco, CA", "New York, NY")
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*,\s*United States$',  # City, United States
        r'^United States$',
        r'^Remote$',
        r'^Hybrid$',
        r'^\d{5}$',  # ZIP code only
        # Common city names (to catch "Seattle" without state)
        r'^(Seattle|San Francisco|New York|Los Angeles|Boston|Austin|Denver|Portland|Chicago|Miami|Atlanta|Dallas|Phoenix|San Diego|San Jose|Washington)$',
        # Area descriptions
        r'^Greater\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+Area$',  # e.g., "Greater Seattle Area"
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+Area$',  # e.g., "Bay Area"
    ]

    # Try both "View job:" and "View" as delimiters (different email formats)
    for delimiter in ['View job:', 'View']:
        if delimiter in body:
            listings = body.split(delimiter)
            break
    else:
        return jobs

    for i, listing in enumerate(listings[:-1]):  # Last split is footer
        # Get the URL from the next section
        if i + 1 < len(listings):
            url_match = re.search(r'(https://www\.linkedin\.com/comm/jobs/view/\d+[^\s]*)', listings[i + 1])
        else:
            continue

        if not url_match:
            continue

        # Extract lines before delimiter
        lines = [line.strip() for line in listing.split('\n') if line.strip() and line.strip() != '-' * 50]
        lines = [l for l in lines if len(l) > 1 and not l.startswith('http')]  # Remove single char lines and URLs
        # Remove connection count lines like "3 connections", "Be first of 13 to apply"
        lines = [l for l in lines if not re.match(r'^\d+\s+(?:connections?|company alumni)$', l) and not re.match(r'^Be first of \d+ to apply$', l)]
        # Remove LinkedIn UI action lines
        lines = [l for l in lines if l.lower() not in (
            'apply with resume & profile', 'apply', 'easy apply',
            'promoted', 'actively recruiting',
            'this company is actively hiring',
            'top applicant', 'fast growing',
        )]

        if not lines:
            continue

        # Check for format: "Company · Location" or "Company · Location (Remote)"
        company_location_match = None
        salary_line = None

        for idx, line in enumerate(lines):
            if ' · ' in line:  # LinkedIn uses middle dot separator
                company_location_match = line
                # Check if next line is salary
                if idx + 1 < len(lines) and '$' in lines[idx + 1]:
                    salary_line = lines[idx + 1]
                break

        if company_location_match:
            # Format: Title\nCompany · Location\n$X-$Y / year
            # But sometimes it's Location · Company, so we need to detect which is which
            parts = company_location_match.split(' · ')
            first_part = parts[0].strip()
            second_part = parts[1].strip() if len(parts) > 1 else "Not specified"

            # Check if first part looks like a location
            first_is_location = any(re.match(pattern, first_part) for pattern in location_patterns)
            second_is_location = any(re.match(pattern, second_part) for pattern in location_patterns)

            # Determine company and location
            if first_is_location and not second_is_location:
                # First part is location, second is company: swap them
                company = second_part
                location = first_part
            elif second_is_location and not first_is_location:
                # Normal order: company first, location second
                company = first_part
                location = second_part
            else:
                # Can't determine clearly, assume normal order (company, location)
                company = first_part
                location = second_part

            # Clean up company name - strip "Careers at" / "Jobs at" prefixes
            company = re.sub(r'^(Careers?|Jobs?|Hiring)\s+(at|@)\s+', '', company, flags=re.IGNORECASE)
            company = re.sub(r'\s*(Careers?|Jobs?|Hiring)\s*$', '', company, flags=re.IGNORECASE).strip()

            # Title is the line before company_location
            title_idx = lines.index(company_location_match) - 1
            title = lines[title_idx] if title_idx >= 0 else "Unknown Title"

            jobs.append({
                'title': title,
                'company': company,
                'location': location,
                'link': url_match.group(1).split()[0],
                'salary': salary_line if salary_line else None
            })
        else:
            # Old format: Title, Company, Location on separate lines
            if len(lines) >= 3:
                title = lines[-3]
                company = lines[-2]
                location = lines[-1]
            elif len(lines) == 2:
                title = "Unknown Title"
                company = lines[-2]
                location = lines[-1]
            else:
                continue

            # Clean up company name
            company = re.sub(r'\s*-\s*\d+\s+connections?', '', company)
            company = re.sub(r'^(Careers?|Jobs?|Hiring)\s+(at|@)\s+', '', company, flags=re.IGNORECASE)
            company = re.sub(r'\s*(Careers?|Jobs?|Hiring)\s*$', '', company, flags=re.IGNORECASE).strip()

            # Filter out if company looks like a location
            is_location = any(re.match(pattern, company) for pattern in location_patterns)
            if is_location:
                continue

            jobs.append({
                'title': title,
                'company': company,
                'location': location,
                'link': url_match.group(1).split()[0],
                'salary': None
            })

    return jobs


def extract_html_body(details: Dict[str, Any]) -> str:
    """Extract HTML body from email message MIME parts."""
    message = details.get('message', {})
    payload = message.get('payload', {})
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('mimeType') == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data + '==').decode('utf-8')
    return ''


def parse_job_listings_from_html(html: str) -> List[Dict[str, str]]:
    """Parse job listings from HTML email body (for saved-jobs format)."""
    jobs = []
    # Find job cards by data-test-id="job-card"
    for card_match in re.finditer(r'data-test-id="job-card"', html):
        card_start = card_match.start()
        # Get a chunk of HTML after the card marker
        card_html = html[card_start:card_start + 8000]

        # Find the LinkedIn job URL in this card
        url_match = re.search(
            r'href="(https://www\.linkedin\.com/comm/jobs/view/\d+[^"]*)"',
            card_html
        )
        if not url_match:
            continue
        raw_url = url_match.group(1).replace('&amp;', '&')

        # Extract text nodes from the card
        text = re.sub(r'<style[^>]*>.*?</style>', '', card_html, flags=re.DOTALL)
        # Also strip inline style attributes to prevent CSS leaking into text
        text = re.sub(r'\s+style="[^"]*"', '', text)
        text = re.sub(r'<[^>]+>', '|', text)
        text_parts = [p.strip() for p in text.split('|') if p.strip() and len(p.strip()) > 1]

        # Known LinkedIn UI/navigation text to skip
        linkedin_ui_skip = {
            'linkedin', 'linkedin login, sign in', 'sign in', 'login',
            'view on linkedin', 'unsubscribe', 'manage preferences',
            'view in browser', 'skip to main content', 'accessibility',
        }

        # Look for title and company·location pattern
        title = None
        company = None
        location = None
        for i, part in enumerate(text_parts):
            # Skip the data-test-id attribute text
            if 'data-test-id' in part:
                continue
            # Skip known LinkedIn UI/navigation text
            if part.lower() in linkedin_ui_skip:
                continue
            # First meaningful text is the title
            if title is None:
                title = part
                continue
            # Next text with middle dot is company · location
            if ' \u00b7 ' in part or ' &middot; ' in part:
                sep = ' \u00b7 ' if ' \u00b7 ' in part else ' &middot; '
                parts_split = part.split(sep, 1)
                company = parts_split[0].strip()
                location = parts_split[1].strip() if len(parts_split) > 1 else 'Not specified'
                # Validate location doesn't contain garbled HTML/CSS content
                garbled_keywords = ['width', 'margin', 'padding', 'font-', 'color:', 'regenerate', 'email']
                if any(kw in location.lower() for kw in garbled_keywords):
                    location = 'Not specified'
                break

        if title and company:
            # Skip if title looks like LinkedIn UI text (not a real job title)
            if title.lower() in linkedin_ui_skip or 'login' in title.lower() or 'sign in' in title.lower():
                continue

            # Clean up company name
            company = re.sub(r'^(Careers?|Jobs?|Hiring)\s+(at|@)\s+', '', company, flags=re.IGNORECASE)
            company = re.sub(r'\s*(Careers?|Jobs?|Hiring)\s*$', '', company, flags=re.IGNORECASE).strip()

            jobs.append({
                'title': title,
                'company': company,
                'location': location or 'Not specified',
                'link': raw_url.split()[0],
                'salary': None
            })

    return jobs


def process_linkedin_emails(recipient_email: str, dry_run: bool = False):
    """Main processing function."""
    # Load exclusion list
    excluded_job_ids = load_exclusion_list()

    # Load embargo dates
    embargo_dates = load_embargo_dates()

    # First, get jobs from previous summary emails
    previous_jobs = parse_previous_summary_emails()

    emails = get_unread_linkedin_emails()

    # Also fetch manually shared job emails
    manual_emails = get_manual_job_emails()
    manual_message_ids = []

    if not emails and not manual_emails:
        if previous_jobs:
            print("No new emails found, but found jobs from previous summaries.")
        else:
            print("No new emails found.")
            return

    if emails:
        print(f"Found {len(emails)} LinkedIn emails.")
    if manual_emails:
        print(f"Found {len(manual_emails)} manually shared job emails.")

    filtered_jobs = []
    processed_message_ids = []

    for email in emails:
        message_id = email.get('id')
        if not message_id:
            continue

        print(f"Processing email {message_id}...")

        # Get full email details
        details = get_email_details(message_id)

        # Extract body
        body = details.get('body', '')

        # Parse individual job listings from the email
        job_listings = parse_job_listings_from_body(body)

        # Fall back to HTML parsing if text body yielded no results
        if not job_listings:
            html_body = extract_html_body(details)
            if html_body:
                job_listings = parse_job_listings_from_html(html_body)

        if not job_listings:
            print(f"  No job listings found in email")
            processed_message_ids.append(message_id)
            continue

        print(f"  Found {len(job_listings)} job listings")

        # Process each job listing
        for job in job_listings:
            company_name = job['company']

            # Check if public company (used for tier assignment)
            company_is_public = is_public_company(company_name, body)

            # Check if company is embargoed
            embargo_date = get_embargo_date(company_name, embargo_dates)
            if embargo_date and date.today() <= embargo_date:
                print(f"    Skipping {company_name} - embargoed until {embargo_date}")
                continue

            # Check if job is in exclusion list
            job_id = extract_job_id_from_url(job['link'])
            if (job_id and job_id in excluded_job_ids) or job['link'] in excluded_job_ids:
                print(f"    Skipping {company_name} - {job['title']} - in exclusion list")
                continue

            # Check job cache for previously stored compensation
            job_cache = _get_job_cache()
            cached_job = job_cache.get(job_id) if job_id else None
            cached_comp = cached_job.get('salary') if cached_job else None

            if cached_comp and cached_comp != "Not specified":
                compensation = cached_comp
            else:
                # Try to get salary in this order:
                # 1. From job listing (if embedded in email)
                # 2. From email body
                # 3. From job page itself
                compensation = None
                if job.get('salary'):
                    compensation = job['salary']
                else:
                    compensation = extract_compensation(body)

                # If still no salary, try fetching from job page
                if compensation == "Not specified" or not compensation:
                    page_salary = fetch_salary_from_job_page(job['link'])
                    if page_salary:
                        compensation = page_salary
                    time.sleep(0.5)  # Be nice to LinkedIn servers

            final_compensation = compensation if compensation else "Not specified"

            # Cache the job info (only store salary when we actually have one)
            if job_id:
                entry = {
                    'title': job['title'],
                    'company': company_name,
                    'location': job['location'],
                }
                if final_compensation != "Not specified":
                    entry['salary'] = final_compensation
                job_cache.setdefault(job_id, {}).update(entry)
                _save_job_cache()

            # Add this job to filtered list
            filtered_jobs.append({
                'company': company_name,
                'title': job['title'],
                'link': job['link'],
                'compensation': final_compensation,
                'location': job['location'],
                'is_public': company_is_public
            })

            print(f"    ✓ Added {company_name} - {job['title']}")

        processed_message_ids.append(message_id)

    # Process manually shared job emails (subject: "linkedin-jobs")
    for entry in manual_emails:
        thread_id = entry['thread_id']
        message_ids = entry['message_ids']

        print(f"Processing manual job email {thread_id}...")

        # Collect URLs from all messages in the thread
        all_urls = []
        for msg_id in message_ids:
            details = get_email_details(msg_id)
            body = details.get('body', '')
            all_urls.extend(extract_urls_from_text(body))

        if not all_urls:
            print(f"  No URLs found in email")
            continue

        # Deduplicate URLs preserving order
        seen_urls = set()
        urls = []
        for url in all_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                urls.append(url)

        print(f"  Found {len(urls)} URLs")

        for url in urls:
            print(f"    Fetching {url}...")
            job = fetch_job_from_career_page(url)
            if not job:
                print(f"    ✗ Could not fetch job details")
                continue

            company_name = job['company']

            # Check if company is embargoed
            embargo_date = get_embargo_date(company_name, embargo_dates)
            if embargo_date and date.today() <= embargo_date:
                print(f"    Skipping {company_name} - embargoed until {embargo_date}")
                continue

            company_is_public = is_public_company(company_name, '')

            filtered_jobs.append({
                'company': company_name,
                'title': job['title'],
                'link': job['link'],
                'compensation': job['salary'],
                'location': job['location'],
                'is_public': company_is_public
            })

            print(f"    ✓ Added {company_name} - {job['title']}")
            time.sleep(0.5)  # Be nice to servers

        manual_message_ids.append(thread_id)

    # Filter previous jobs against embargo dates and add is_public field
    previous_jobs = [j for j in previous_jobs
                     if not is_company_embargoed(j['company'], embargo_dates)]
    for j in previous_jobs:
        if 'is_public' not in j:
            j['is_public'] = is_public_company(j['company'], '')

    # Merge with previous jobs and deduplicate
    # Put filtered_jobs first so freshly-parsed data (with correct compensation/
    # location from cache or email) takes precedence over stale data parsed from
    # previous summary emails (which may show "Not specified").
    all_jobs = filtered_jobs + previous_jobs

    # Deduplicate by job ID (extracted from link) and filter out excluded jobs
    # LinkedIn URLs have format: /jobs/view/4365006239/ where 4365006239 is the job ID
    seen_job_ids = set()
    unique_jobs = []
    for job in all_jobs:
        # Extract job ID from URL
        job_id = extract_job_id_from_url(job['link'])
        if job_id:
            # Skip if in exclusion list (by extracted ID or full URL)
            if job_id in excluded_job_ids or job['link'] in excluded_job_ids:
                continue
            if job_id not in seen_job_ids:
                seen_job_ids.add(job_id)
                unique_jobs.append(job)
        else:
            # Fallback to full link if we can't extract ID
            if job['link'] in excluded_job_ids:
                continue
            if job['link'] not in seen_job_ids:
                seen_job_ids.add(job['link'])
                unique_jobs.append(job)

    if previous_jobs:
        print(f"\nMerged {len(filtered_jobs)} new jobs with {len(previous_jobs)} from previous summaries.")
        print(f"Total unique jobs: {len(unique_jobs)} (removed {len(all_jobs) - len(unique_jobs)} duplicates)")
    else:
        print(f"\nFiltered down to {len(unique_jobs)} jobs from public companies.")

    if unique_jobs:
        # Delete ALL old summary emails BEFORE sending the new one
        # This ensures we start with a clean slate
        if not dry_run:
            delete_old_summary_emails()
            time.sleep(1)  # Brief pause

        send_summary_email(unique_jobs, recipient_email)

    # Mark LinkedIn emails as read and trash them
    if not dry_run and processed_message_ids:
        print(f"\nDeleting {len(processed_message_ids)} processed LinkedIn emails...")
        for msg_id in processed_message_ids:
            mark_email_as_read(msg_id)
            run_gog_command(['gmail', 'thread', 'modify', msg_id, '--add', 'TRASH', '--json'])
        print("Done!")

    # Delete processed manual job emails
    if not dry_run:
        delete_manual_job_emails(manual_message_ids)
    elif dry_run:
        print("\nDry run - LinkedIn emails NOT deleted, manual emails NOT deleted.")

def main():
    import argparse
    global GOG_ACCOUNT

    parser = argparse.ArgumentParser(description='Filter LinkedIn job emails')
    parser.add_argument('--email', default='chernenko@gmail.com', help='Your email address to send summary to')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t mark emails as read')
    parser.add_argument('--account', help='Gmail account to use with gog (defaults to --email value)')

    args = parser.parse_args()

    # Set the global account (default to email if not specified)
    GOG_ACCOUNT = args.account if args.account else args.email

    process_linkedin_emails(args.email, args.dry_run)

if __name__ == '__main__':
    main()
