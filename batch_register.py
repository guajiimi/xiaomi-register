#!/usr/bin/env python3
"""
Batch Xiaomi Account Registration
Registers N accounts using Gmail + alias addressing.
"""

import os
import sys
import json
import time
import uuid
import random
import argparse
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from register_v3 import register_xiaomi_account

# ─── CONFIG ──────────────────────────────────────────────────────────────────

ACCOUNTS_FILE = "accounts.jsonl"
FAILED_FILE = "failed.jsonl"
DEFAULT_COUNT = 100
SLEEP_BETWEEN = 10  # seconds


def load_existing_emails(filepath: str) -> set:
    """Load already-registered emails from JSONL file for resume support."""
    emails = set()
    if os.path.exists(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        emails.add(data.get("email", "").lower())
                    except json.JSONDecodeError:
                        continue
    return emails


def load_failed_emails(filepath: str) -> set:
    """Load failed emails from JSONL file."""
    emails = set()
    if os.path.exists(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        emails.add(data.get("email", "").lower())
                    except json.JSONDecodeError:
                        continue
    return emails


def generate_email(prefix: str, batch_id: str, seq: int) -> str:
    """Generate email using Gmail + alias: {prefix}+mi{batch_id}_{seq}@gmail.com"""
    return f"{prefix}+mi{batch_id}_{seq}@gmail.com"


def main():
    parser = argparse.ArgumentParser(description="Batch Xiaomi Account Registration")
    parser.add_argument("-n", "--count", type=int, default=DEFAULT_COUNT,
                        help=f"Number of accounts to register (default: {DEFAULT_COUNT})")
    parser.add_argument("--batch-id", type=str, default=None,
                        help="Batch identifier (default: random 8-char hex)")
    parser.add_argument("--password", type=str, default=None,
                        help="Password for all accounts (default: auto-generated)")
    parser.add_argument("--sleep", type=int, default=SLEEP_BETWEEN,
                        help=f"Seconds between registrations (default: {SLEEP_BETWEEN})")
    args = parser.parse_args()

    # Validate environment
    email_prefix = os.environ.get("EMAIL_PREFIX")
    if not email_prefix:
        print("ERROR: EMAIL_PREFIX not set in .env file")
        sys.exit(1)

    imap_user = os.environ.get("IMAP_USER")
    imap_pass = os.environ.get("IMAP_PASS")
    captcha_key = os.environ.get("TWOCAPTCHA_API_KEY")

    missing = []
    if not imap_user:
        missing.append("IMAP_USER")
    if not imap_pass:
        missing.append("IMAP_PASS")
    if not captcha_key:
        missing.append("TWOCAPTCHA_API_KEY")
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Please fill in your .env file (cp .env.example .env)")
        sys.exit(1)

    batch_id = args.batch_id or uuid.uuid4().hex[:8]
    password = args.password or f"Xiaomi_{uuid.uuid4().hex[:8]}!"

    # Load existing accounts for resume support
    existing_emails = load_existing_emails(ACCOUNTS_FILE)
    failed_emails = load_failed_emails(FAILED_FILE)
    skip_emails = existing_emails | failed_emails

    if existing_emails:
        print(f"📋 Found {len(existing_emails)} existing accounts — will skip those")

    print("=" * 60)
    print(f"🚀 Batch Registration — {args.count} accounts")
    print(f"📧 Email pattern: {email_prefix}+mi{batch_id}_{{SEQ}}@gmail.com")
    print(f"🔑 Password: {password}")
    print(f"⏱  Sleep between: {args.sleep}s")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    skip_count = 0
    start_time = time.time()

    for seq in range(1, args.count + 1):
        email = generate_email(email_prefix, batch_id, seq)

        # Resume support: skip already processed emails
        if email.lower() in skip_emails:
            print(f"[{seq}/{args.count}] ⏭  SKIP {email} (already processed)")
            skip_count += 1
            continue

        print(f"\n{'='*60}")
        print(f"[{seq}/{args.count}] 🔵 Registering: {email}")
        print(f"{'='*60}")

        try:
            account = register_xiaomi_account(email, password)

            # Save success
            with open(ACCOUNTS_FILE, "a") as f:
                f.write(json.dumps(account) + "\n")

            success_count += 1
            print(f"[{seq}/{args.count}] ✅ SUCCESS — {email}")

        except Exception as e:
            fail_count += 1
            error_msg = str(e)

            # Save failure
            with open(FAILED_FILE, "a") as f:
                f.write(json.dumps({
                    "email": email,
                    "password": password,
                    "error": error_msg,
                    "failed_at": datetime.utcnow().isoformat() + "Z",
                }) + "\n")

            print(f"[{seq}/{args.count}] ❌ FAILED — {email}: {error_msg}")

        # Sleep between registrations (except for the last one)
        if seq < args.count:
            print(f"\n⏳ Sleeping {args.sleep}s before next registration...")
            time.sleep(args.sleep)

    # Summary
    elapsed = time.time() - start_time
    elapsed_min = elapsed / 60

    print("\n" + "=" * 60)
    print("📊 BATCH REGISTRATION SUMMARY")
    print("=" * 60)
    print(f"  Batch ID:   {batch_id}")
    print(f"  Total:      {args.count}")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed:  {fail_count}")
    print(f"  ⏭  Skipped: {skip_count}")
    print(f"  ⏱  Time:    {elapsed_min:.1f} minutes")
    print(f"  📁 Accounts: {ACCOUNTS_FILE}")
    print(f"  📁 Failures: {FAILED_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
