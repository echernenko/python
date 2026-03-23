#!/usr/bin/env python3
"""
LinkedIn Job Application Assistant

Fetches the latest summary email, presents jobs one by one,
opens each in a browser, and excludes applied/skipped positions
from future summaries.
"""

import subprocess
import json
import re
import sys
import os
from datetime import datetime
from typing import List, Dict, Any


# Global variable to store the Gmail account
GOG_ACCOUNT = None


def run_gog_command(args: List[str]) -> Dict[str, Any]:
    """Run a gog command and return JSON output."""
    cmd = ['gog']
    if GOG_ACCOUNT:
        cmd.extend(['--account', GOG_ACCOUNT])
    cmd.extend(args)

    passphrase_file = os.path.expanduser('~/.config/gogcli/keyring_passphrase')
    env = os.environ.copy()
    if os.path.exists(passphrase_file):
        with open(passphrase_file) as f:
            env['GOG_KEYRING_PASSWORD'] = f.read().strip()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            print(f"Error running gog: {result.stderr}", file=sys.stderr)
            return {}
        stdout = result.stdout.strip()
        return json.loads(stdout) if stdout else {}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return {}


def fetch_summary_jobs() -> List[Dict[str, Any]]:
    """Fetch jobs from the most recent summary email."""
    result = run_gog_command([
        'gmail', 'search',
        'subject:"LinkedIn Job Opportunities"',
        '--max', '1',
        '--json'
    ])

    threads = result.get('threads', []) or []
    if not threads:
        print("No summary email found.")
        return []

    message_id = threads[0].get('id')
    if not message_id:
        return []

    details = run_gog_command(['gmail', 'get', message_id, '--json'])
    body_html = details.get('body', '')
    if not body_html:
        return []

    # Parse job blocks from summary HTML
    jobs = []
    job_blocks = re.findall(r'<div class="job">(.*?)</div>\s*</div>', body_html, re.DOTALL)

    for block in job_blocks:
        company_match = re.search(r'<div class="company">(?:\d+\.\s+)?([^<]+)</div>', block)
        title_match = re.search(r'<div class="title">([^<]+)</div>', block)
        pay_match = re.search(r'💰 Pay Range:\s*([^<]+)</div>', block)
        location_match = re.search(r'📍 Location:\s*([^<]+)</div>', block)
        link_match = re.search(r'<a href="([^"]+)">', block)

        if company_match and link_match:
            jobs.append({
                'company': company_match.group(1).strip(),
                'title': title_match.group(1).strip() if title_match else 'Unknown',
                'compensation': pay_match.group(1).strip() if pay_match else 'Not specified',
                'location': location_match.group(1).strip() if location_match else 'Not specified',
                'link': link_match.group(1).strip(),
            })

    # Also extract tier headers so we can display them
    tier_pattern = r'<div class="tier-header[^"]*">([^<]+)</div>'
    tiers = re.findall(tier_pattern, body_html)

    # Map jobs to their tier by position in the HTML
    tier_positions = []
    for tier_match in re.finditer(tier_pattern, body_html):
        tier_positions.append((tier_match.start(), tier_match.group(1)))

    for job in jobs:
        link_pos = body_html.find(job['link'])
        job['tier'] = ''
        for pos, tier_name in reversed(tier_positions):
            if link_pos > pos:
                job['tier'] = tier_name
                break

    return jobs


def open_url(url: str):
    """Print a URL for the user to Cmd+click."""
    print(f"  {url}")


def extract_job_id(url: str) -> str:
    """Extract job ID from a LinkedIn URL."""
    m = re.search(r'/jobs?/(?:view/|comm/jobs/view/)(\d+)', url)
    if m:
        return m.group(1)
    # Non-LinkedIn: trailing numeric ID
    path = url.rstrip('/')
    last_segment = path.rsplit('/', 1)[-1] if '/' in path else path
    m = re.search(r'-(\d{5,})$', last_segment)
    if m:
        return m.group(1)
    m = re.match(r'(\d{5,})-', last_segment)
    if m:
        return m.group(1)
    return last_segment if last_segment else None


def load_excluded_ids() -> set:
    """Load existing excluded job IDs."""
    script_dir = os.path.dirname(os.path.realpath(__file__))
    exclusion_file = os.path.join(script_dir, 'linkedin-jobs-exclusions.txt')
    ids = set()
    if os.path.exists(exclusion_file):
        with open(exclusion_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if parts:
                    ids.add(parts[0].strip())
    return ids


def exclude_job(job_id: str, company: str, title: str):
    """Append a job to the exclusion list."""
    script_dir = os.path.dirname(os.path.realpath(__file__))
    exclusion_file = os.path.join(script_dir, 'linkedin-jobs-exclusions.txt')
    entry = f"{job_id} | {company} | {title}\n"
    with open(exclusion_file, 'a') as f:
        f.write(entry)


def main():
    import argparse
    global GOG_ACCOUNT

    parser = argparse.ArgumentParser(description='LinkedIn job application assistant')
    parser.add_argument('--account', default='chernenko@gmail.com', help='Gmail account')
    args = parser.parse_args()
    GOG_ACCOUNT = args.account

    print("Fetching latest summary email...")
    jobs = fetch_summary_jobs()
    if not jobs:
        print("No jobs found in summary email.")
        return

    excluded_ids = load_excluded_ids()

    # Filter out already-excluded jobs
    jobs = [j for j in jobs if extract_job_id(j['link']) not in excluded_ids]

    if not jobs:
        print("All jobs in the summary are already excluded.")
        return

    print(f"\n{len(jobs)} positions to review.\n")
    current_tier = ''
    excluded_count = 0
    opened_count = 0

    for i, job in enumerate(jobs):
        # Print tier header when it changes
        if job['tier'] and job['tier'] != current_tier:
            current_tier = job['tier']
            print(f"\n{'=' * 60}")
            print(f"  {current_tier}")
            print(f"{'=' * 60}")

        job_id = extract_job_id(job['link'])
        print(f"\n[{i + 1}/{len(jobs)}] {job['company']} - {job['title']}")
        print(f"  Pay: {job['compensation']}  |  Location: {job['location']}")
        open_url(job['link'])
        opened_count += 1

        try:
            applied = input("  Did you apply? (y/n) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nQuitting.")
            break

        if applied == 'y' and job_id:
                exclude_job(job_id, job['company'], job['title'])
                excluded_count += 1
                print(f"  Excluded.")

    print(f"\nDone. Opened: {opened_count}, Excluded: {excluded_count}")


if __name__ == '__main__':
    main()
