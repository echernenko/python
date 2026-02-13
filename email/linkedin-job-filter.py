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
from datetime import datetime
from typing import List, Dict, Any, Set
from html.parser import HTMLParser
import urllib.parse
import time

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
    exclusion_file = os.path.expanduser('~/bin/linkedin-jobs-exclusions.txt')
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

def run_gog_command(args: List[str]) -> Dict[str, Any]:
    """Run a gog command and return JSON output."""
    try:
        result = subprocess.run(
            ['gog'] + args,
            capture_output=True,
            text=True,
            check=True
        )
        # Only try to parse JSON if there's actual output
        if result.stdout and result.stdout.strip():
            return json.loads(result.stdout)
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Error running gog command: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        print(f"stdout was: {result.stdout[:100]}", file=sys.stderr)
        return {}

def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML content."""
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()

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

def is_public_company(company_name: str, job_description: str) -> bool:
    """
    Heuristic check if a company is public.
    This is a simple implementation - could be enhanced with SEC API.
    """
    # List of known public tech companies (can be expanded)
    known_public = {
        'google', 'alphabet', 'meta', 'facebook', 'amazon', 'microsoft',
        'apple', 'netflix', 'tesla', 'nvidia', 'intel', 'amd', 'qualcomm',
        'salesforce', 'oracle', 'ibm', 'cisco', 'adobe', 'intuit', 'paypal',
        'uber', 'lyft', 'airbnb', 'doordash', 'coinbase', 'snowflake',
        'databricks', 'stripe', 'atlassian', 'shopify', 'square', 'block',
        'mongodb', 'elastic', 'twilio', 'okta', 'zoom', 'slack', 'dropbox',
        'pinterest', 'snap', 'twitter', 'reddit', 'roblox', 'unity',
        'servicenow', 'workday', 'splunk', 'crowdstrike', 'palo alto',
        'fortinet', 'cloudflare', 'datadog', 'gitlab', 'hashicorp',
        'affirm', 'cvs', 'zillow', 'anthropic', 'ford', 'walmart',
        'target', 'home depot', 'lowes', 'best buy', 'dell', 'hp',
        'booking', 'expedia', 'wayfair', 'ebay', 'etsy', 'chewy',
        'draft kings', 'mgm', 'caesars', 'disney', 'comcast', 'verizon',
        'att', 't-mobile', 'sprint', 'charter', 'dish', 'fox', 'viacom',
        'paramount', 'warner', 'discovery', 'spotify', 'roku', 'peloton',
        'figma', 'mixpanel', 'blue origin', 'sofi', 'databricks'
    }

    company_lower = company_name.lower()

    # Check if any known public company name is in the company name
    for public_co in known_public:
        if public_co in company_lower:
            return True

    # Check for indicators in job description
    public_indicators = ['nasdaq', 'nyse', 'publicly traded', 'stock options', 'equity']
    desc_lower = job_description.lower()

    return any(indicator in desc_lower for indicator in public_indicators)

def fetch_salary_from_job_page(job_url: str) -> str:
    """Fetch salary information from LinkedIn job page."""
    try:
        # Clean the URL: convert /comm/jobs/view/ to /jobs/view/ and remove tracking params
        # Extract job ID
        job_id_match = re.search(r'/jobs/view/(\d+)', job_url)
        if not job_id_match:
            return None

        job_id = job_id_match.group(1)
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

        for pattern in salary_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                # Extract the numbers
                low = match.group(1).replace(',', '')
                high = match.group(2).replace(',', '')
                # Convert to K format
                return f"${int(low)//1000}K-${int(high)//1000}K"

        return None
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

    threads = result.get('threads', [])

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

    threads = result.get('threads', [])
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
                jobs.append({
                    'company': company_match.group(1).strip(),
                    'title': title_match.group(1).strip() if title_match else 'Unknown Title',
                    'link': link_match.group(1).strip(),
                    'compensation': pay_match.group(1).strip() if pay_match else 'Not specified',
                    'location': location_match.group(1).strip() if location_match else 'Not specified'
                })

    print(f"Extracted {len(jobs)} jobs from previous summary emails.")
    return jobs

def get_unread_linkedin_emails() -> List[Dict[str, Any]]:
    """Fetch unread LinkedIn job emails."""
    print("Searching for LinkedIn emails...")

    # Search for unread emails from LinkedIn about jobs
    # Search for emails from any LinkedIn job-related sender (last 24 hours, read or unread)
    search_query = '(from:jobs-listings@linkedin.com OR from:jobs-noreply@linkedin.com OR from:jobalerts-noreply@linkedin.com OR from:messages-noreply@linkedin.com) newer_than:1d'

    result = run_gog_command([
        'gmail', 'search',
        search_query,
        '--max', '50',
        '--json'
    ])

    if not result or 'threads' not in result:
        return []

    return result.get('threads', [])

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

def get_company_tier(company_name: str) -> int:
    """Classify company into tiers (1 = best, 3 = good)."""
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
        'affirm', 'coinbase', 'square', 'block', 'spotify', 'roku', 'peloton',
        'blue origin', 'mixpanel', 'sofi'
    }

    # Check tier 1
    for t1_company in tier1:
        if t1_company in company_lower:
            return 1

    # Check tier 2
    for t2_company in tier2:
        if t2_company in company_lower:
            return 2

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

    for job in jobs:
        tier = get_company_tier(job['company'])
        if tier == 1:
            tier1_jobs.append(job)
        elif tier == 2:
            tier2_jobs.append(job)
        else:
            tier3_jobs.append(job)

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
    <p><strong>{len(jobs)} jobs</strong> from public companies | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
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

    email_body += """
</body>
</html>
"""

    # Send email using gog with HTML body
    try:
        subprocess.run([
            'gog', 'gmail', 'send',
            '--to', recipient,
            '--subject', f'LinkedIn Job Opportunities - {len(jobs)} Public Companies',
            '--body-html', email_body
        ], check=True)

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
        lines = [l for l in lines if not re.match(r'^\d+\s+connections?$', l) and not re.match(r'^Be first of \d+ to apply$', l)]

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

def process_linkedin_emails(recipient_email: str, dry_run: bool = False):
    """Main processing function."""
    # Load exclusion list
    excluded_job_ids = load_exclusion_list()

    # First, get jobs from previous summary emails
    previous_jobs = parse_previous_summary_emails()

    emails = get_unread_linkedin_emails()

    if not emails:
        if previous_jobs:
            print("No new LinkedIn emails found, but found jobs from previous summaries.")
        else:
            print("No LinkedIn emails found.")
            return

    if emails:
        print(f"Found {len(emails)} LinkedIn emails.")

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

        if not job_listings:
            print(f"  No job listings found in email")
            continue

        print(f"  Found {len(job_listings)} job listings")

        # Process each job listing
        for job in job_listings:
            company_name = job['company']

            # Check if public company
            if not is_public_company(company_name, body):
                print(f"    Skipping {company_name} - not a public company")
                continue

            # Check if job is in exclusion list
            job_id_match = re.search(r'/jobs/view/(\d+)', job['link'])
            if job_id_match:
                job_id = job_id_match.group(1)
                if job_id in excluded_job_ids:
                    print(f"    Skipping {company_name} - {job['title']} - in exclusion list")
                    continue

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

            # Add this job to filtered list
            filtered_jobs.append({
                'company': company_name,
                'title': job['title'],
                'link': job['link'],
                'compensation': compensation if compensation else "Not specified",
                'location': job['location']
            })

            print(f"    ✓ Added {company_name} - {job['title']}")

        processed_message_ids.append(message_id)

    # Merge with previous jobs and deduplicate
    all_jobs = previous_jobs + filtered_jobs

    # Deduplicate by job ID (extracted from link) and filter out excluded jobs
    # LinkedIn URLs have format: /jobs/view/4365006239/ where 4365006239 is the job ID
    seen_job_ids = set()
    unique_jobs = []
    for job in all_jobs:
        # Extract job ID from URL
        job_id_match = re.search(r'/jobs/view/(\d+)', job['link'])
        if job_id_match:
            job_id = job_id_match.group(1)
            # Skip if in exclusion list
            if job_id in excluded_job_ids:
                continue
            if job_id not in seen_job_ids:
                seen_job_ids.add(job_id)
                unique_jobs.append(job)
        else:
            # Fallback to full link if we can't extract ID
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

    # Mark emails as read
    if not dry_run and processed_message_ids:
        print(f"\nMarking {len(processed_message_ids)} LinkedIn emails as read...")
        for msg_id in processed_message_ids:
            mark_email_as_read(msg_id)
        print("Done!")
    elif dry_run:
        print("\nDry run - emails NOT marked as read.")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Filter LinkedIn job emails')
    parser.add_argument('--email', required=True, help='Your email address to send summary to')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t mark emails as read')

    args = parser.parse_args()

    process_linkedin_emails(args.email, args.dry_run)

if __name__ == '__main__':
    main()
