#!/usr/bin/env python3
"""
Batch Xiaomi Account Registration
Registers N accounts using Gmail + alias addressing.
Includes optional referral code binding after each registration.
"""

import os
import sys
import json
import time
import uuid
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from xiaomi import register_xiaomi_account
from mimo_bind import bind_referral_after_registration

__all__ = ["main"]

# ─── PATHS ────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent
ACCOUNTS_FILE = _SCRIPT_DIR / "accounts.jsonl"
FAILED_FILE = _SCRIPT_DIR / "failed.jsonl"

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
DEFAULT_COUNT = 100
SLEEP_BETWEEN = 10  # seconds

# ─── ANSI HELPERS ─────────────────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BLUE = "\033[34m"

_SEP = "━" * 60


def _padded_seq(seq: int, total: int) -> str:
    width = len(str(total))
    return str(seq).zfill(width)


def _load_existing_emails(filepath: Path) -> set:
    """Load already-registered emails from JSONL file for resume support."""
    emails = set()
    if filepath.exists():
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


def _load_failed_emails(filepath: Path) -> set:
    """Load failed emails from JSONL file."""
    emails = set()
    if filepath.exists():
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


def _generate_email(prefix: str, batch_id: str, seq: int) -> str:
    """Generate email using Gmail + alias: {prefix}+mi{batch_id}_{seq}@gmail.com"""
    return f"{prefix}+mi{batch_id}_{seq}@gmail.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch Xiaomi Account Registration")
    parser.add_argument("-n", "--count", type=int, default=DEFAULT_COUNT,
                        help=f"Number of accounts to register (default: {DEFAULT_COUNT})")
    parser.add_argument("--batch-id", type=str, default=None,
                        help="Batch identifier (default: random 8-char hex)")
    parser.add_argument("--password", type=str, default=None,
                        help="Password for all accounts (default: auto-generated)")
    parser.add_argument("--sleep", type=int, default=SLEEP_BETWEEN,
                        help=f"Seconds between registrations (default: {SLEEP_BETWEEN})")
    parser.add_argument("--referral-code", type=str, default=None,
                        help="Referral code to bind (default: from REFERRAL_CODE env)")
    parser.add_argument("--skip-bind", action="store_true",
                        help="Skip referral binding after registration")
    args = parser.parse_args()

    # Validate environment
    email_prefix = os.environ.get("EMAIL_PREFIX")
    if not email_prefix:
        print(f"\n {_RED}ERROR: EMAIL_PREFIX not set in .env file{_RESET}")
        sys.exit(1)

    missing = []
    if not os.environ.get("IMAP_USER"):
        missing.append("IMAP_USER")
    if not os.environ.get("IMAP_PASS"):
        missing.append("IMAP_PASS")
    # Need at least one captcha solver key
    if not os.environ.get("CAPSOLVER_API_KEY") and not os.environ.get("TWOCAPTCHA_API_KEY"):
        missing.append("CAPSOLVER_API_KEY or TWOCAPTCHA_API_KEY")
    if missing:
        print(f"\n {_RED}ERROR: Missing environment variables: {', '.join(missing)}{_RESET}")
        print(f" {_DIM}Please fill in your .env file (cp .env.example .env){_RESET}")
        sys.exit(1)

    batch_id = args.batch_id or uuid.uuid4().hex[:8]
    password = args.password or os.environ.get("DEFAULT_PASSWORD", f"Xiaomi_{uuid.uuid4().hex[:8]}!")
    referral_code = args.referral_code or os.environ.get("REFERRAL_CODE", "")

    # Load existing accounts for resume support
    existing_emails = _load_existing_emails(ACCOUNTS_FILE)
    failed_emails = _load_failed_emails(FAILED_FILE)
    skip_emails = existing_emails | failed_emails

    # ─── Banner ────────────────────────────────────────────────────────────
    print(f"\n{_BOLD}{_CYAN}{_SEP}{_RESET}")
    print(f" 🚀 {_BOLD}Batch Registration — {args.count} accounts{_RESET}")
    print(f"{_BOLD}{_CYAN}{_SEP}{_RESET}")
    print(f"    {_DIM}Email pattern:{_RESET} {email_prefix}+mi{batch_id}_{{SEQ}}@gmail.com")
    print(f"    {_DIM}Password:{_RESET}      {password}")
    print(f"    {_DIM}Sleep:{_RESET}         {args.sleep}s between registrations")
    if referral_code and not args.skip_bind:
        print(f"    {_DIM}Referral:{_RESET}      {referral_code}")
    else:
        print(f"    {_DIM}Referral:{_RESET}      {_YELLOW}disabled{_RESET}")
    if existing_emails:
        print(f"    {_DIM}Resume:{_RESET}        {len(existing_emails)} existing accounts will be skipped")
    print(f"{_BOLD}{_CYAN}{_SEP}{_RESET}\n")

    success_count = 0
    fail_count = 0
    skip_count = 0
    bind_count = 0
    start_time = time.time()

    for seq in range(1, args.count + 1):
        email = _generate_email(email_prefix, batch_id, seq)
        seq_str = _padded_seq(seq, args.count)

        # Resume support: skip already processed emails
        if email.lower() in skip_emails:
            print(f" [{seq_str}/{args.count}] ⏭  {_DIM}{email} — skipped (already processed){_RESET}")
            skip_count += 1
            continue

        print(f" [{seq_str}/{args.count}] 🔵 {_BOLD}{email}{_RESET} — registering...")

        reg_start = time.time()
        try:
            account = register_xiaomi_account(email, password)

            with open(ACCOUNTS_FILE, "a") as f:
                f.write(json.dumps(account) + "\n")

            elapsed = time.time() - reg_start
            success_count += 1
            print(f" [{seq_str}/{args.count}] {_GREEN}✅ {_BOLD}{email}{_RESET}{_GREEN} — registered ({elapsed:.1f}s){_RESET}")

            # ─── Referral Bind ──────────────────────────────────────────────
            if referral_code and not args.skip_bind:
                try:
                    bind_result = bind_referral_after_registration(
                        email=email,
                        password=password,
                        pass_token=account.get("passToken", ""),
                        c_user_id=account.get("cUserId", ""),
                        invite_code=referral_code,
                    )
                    if bind_result.get("bound"):
                        bind_count += 1
                        print(f" [{seq_str}/{args.count}] {_GREEN}🎁 {_BOLD}{email}{_RESET}{_GREEN} — referral bound{_RESET}")
                    else:
                        print(f" [{seq_str}/{args.count}] {_YELLOW}⚠️  {_BOLD}{email}{_RESET}{_YELLOW} — referral bind failed{_RESET}")
                except Exception as e:
                    print(f" [{seq_str}/{args.count}] {_YELLOW}⚠️  {_BOLD}{email}{_RESET}{_YELLOW} — bind error: {str(e)[:50]}{_RESET}")

        except Exception as e:
            fail_count += 1
            error_msg = str(e)

            with open(FAILED_FILE, "a") as f:
                f.write(json.dumps({
                    "email": email,
                    "password": password,
                    "error": error_msg,
                    "failed_at": datetime.utcnow().isoformat() + "Z",
                }) + "\n")

            # Short error for batch display
            short_err = error_msg[:60] + "..." if len(error_msg) > 60 else error_msg
            print(f" [{seq_str}/{args.count}] {_RED}❌ {_BOLD}{email}{_RESET}{_RED} — {short_err}{_RESET}")

        # Sleep between registrations (except for the last one)
        if seq < args.count:
            time.sleep(args.sleep)

    # ─── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    elapsed_min = elapsed / 60

    print(f"\n{_BOLD}{_CYAN}{_SEP}{_RESET}")
    print(f" 📊 {_BOLD}Batch Registration Summary{_RESET}")
    print(f"{_BOLD}{_CYAN}{_SEP}{_RESET}")
    print(f"    {_DIM}Batch ID:{_RESET}   {batch_id}")
    print(f"    {_DIM}Total:{_RESET}      {args.count}")
    print(f"    {_GREEN}✅ Success:{_RESET} {success_count}")
    print(f"    {_RED}❌ Failed:{_RESET}  {fail_count}")
    print(f"    {_YELLOW}⏭  Skipped:{_RESET} {skip_count}")
    if referral_code and not args.skip_bind:
        print(f"    {_GREEN}🎁 Bound:{_RESET}   {bind_count}")
    print(f"    {_DIM}⏱  Time:{_RESET}    {elapsed_min:.1f} minutes")
    print(f"    {_DIM}📁 Accounts:{_RESET} {ACCOUNTS_FILE}")
    print(f"    {_DIM}📁 Failures:{_RESET} {FAILED_FILE}")
    print(f"{_BOLD}{_CYAN}{_SEP}{_RESET}\n")


if __name__ == "__main__":
    main()
