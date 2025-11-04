"""Analyze sent email patterns by scanning Sent folders directly."""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

from ratatoskr_mcp_server.utils.evolution_email import EvolutionEmailManager


class SentEmailAnalyzer:
    """Analyze email communication patterns from Sent folders."""

    def __init__(self):
        """Initialize the analyzer with Evolution email manager."""
        try:
            self.email_manager = EvolutionEmailManager()
        except Exception:
            self.email_manager = None

    def analyze_sent_emails(
        self,
        my_email_addresses: List[str],
        days_back: int = 365,
        recent_days: Optional[int] = None
    ) -> Dict:
        """Analyze sent email patterns directly from Sent folders.

        Args:
            my_email_addresses: List of your email addresses to analyze
            days_back: How many days back to analyze (default: 365 for 1 year)
            recent_days: Optional: analyze most active contacts in recent period (e.g., 120 for 4 months)

        Returns:
            Dictionary with analysis results
        """
        if not self.email_manager:
            return {"error": "Evolution email not available"}

        # Analyze emails for each account
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_cutoff = None
        if recent_days:
            recent_cutoff = datetime.now() - timedelta(days=recent_days)

        # Track emails per recipient
        recipient_stats = defaultdict(lambda: {
            'sent_count': 0,
            'recent_sent_count': 0,
            'last_sent': None,
            'first_sent': None
        })

        accounts = self.email_manager.get_accounts()

        for account in accounts:
            account_id = account['account_id']
            account_email = account['email_address'].lower()

            # Only analyze requested email addresses
            if account_email not in [e.lower() for e in my_email_addresses]:
                continue

            # Get account DB path
            db_path = account['db_path'].replace('/folders.db', '')
            folders_db = Path(db_path) / 'folders.db'

            if not folders_db.exists():
                continue

            try:
                conn = sqlite3.connect(str(folders_db))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Get Sent folder(s) for this account
                sent_folders = cursor.execute(
                    "SELECT name FROM folders WHERE name LIKE '%ent%'"
                ).fetchall()

                for folder_row in sent_folders:
                    folder_name = folder_row['name']
                    summary_db = Path(db_path) / f"{folder_name}.ev-summary.db"

                    if not summary_db.exists():
                        continue

                    try:
                        summary_conn = sqlite3.connect(str(summary_db))
                        summary_conn.row_factory = sqlite3.Row

                        # Query emails within date range
                        cutoff_timestamp = int(cutoff_date.timestamp())
                        recent_timestamp = int(recent_cutoff.timestamp()) if recent_cutoff else None

                        query = """
                            SELECT dsent, frm, rcpt
                            FROM folder
                            WHERE dsent >= ?
                            ORDER BY dsent DESC
                        """

                        rows = summary_conn.execute(query, (cutoff_timestamp,)).fetchall()

                        for row in rows:
                            sent_date = datetime.fromtimestamp(row['dsent'])
                            from_addr = row['frm'].lower() if row['frm'] else ''
                            to_addrs = row['rcpt'].lower() if row['rcpt'] else ''

                            is_recent = recent_timestamp and row['dsent'] >= recent_timestamp

                            # Verify this is actually a sent email (from my account)
                            if account_email in from_addr:
                                # Parse recipient addresses
                                for recipient_email in to_addrs.split(','):
                                    recipient_email = recipient_email.strip()

                                    # Skip empty addresses
                                    if not recipient_email:
                                        continue

                                    # Skip if it's my own address (sent to myself)
                                    if recipient_email in [e.lower() for e in my_email_addresses]:
                                        continue

                                    # Track this recipient
                                    recipient_stats[recipient_email]['sent_count'] += 1

                                    if is_recent:
                                        recipient_stats[recipient_email]['recent_sent_count'] += 1

                                    # Update last sent
                                    if not recipient_stats[recipient_email]['last_sent'] or sent_date > recipient_stats[recipient_email]['last_sent']:
                                        recipient_stats[recipient_email]['last_sent'] = sent_date

                                    # Update first sent
                                    if not recipient_stats[recipient_email]['first_sent'] or sent_date < recipient_stats[recipient_email]['first_sent']:
                                        recipient_stats[recipient_email]['first_sent'] = sent_date

                        summary_conn.close()

                    except Exception:
                        continue

                conn.close()

            except Exception:
                continue

        # Build results
        all_recipients = []
        for email, stats in recipient_stats.items():
            all_recipients.append({
                'email': email,
                'sent_count': stats['sent_count'],
                'recent_sent_count': stats['recent_sent_count'],
                'last_sent': stats['last_sent'].isoformat() if stats['last_sent'] else None,
                'first_sent': stats['first_sent'].isoformat() if stats['first_sent'] else None,
            })

        # Sort by total emails sent
        all_recipients.sort(key=lambda x: x['sent_count'], reverse=True)

        # Find most active in recent period
        most_active_recent = None
        if recent_days:
            recent_sorted = sorted(
                [r for r in all_recipients if r['recent_sent_count'] > 0],
                key=lambda x: x['recent_sent_count'],
                reverse=True
            )
            if recent_sorted:
                most_active_recent = recent_sorted[0]

        return {
            'analyzed_accounts': [e for e in my_email_addresses],
            'total_unique_recipients': len(all_recipients),
            'days_analyzed': days_back,
            'recent_days': recent_days,
            'most_active_recent': most_active_recent,
            'top_recipients': all_recipients[:50],  # Top 50
            'summary': {
                'unique_recipients_in_period': len(all_recipients),
                'recipients_in_recent_period': len([r for r in all_recipients if r['recent_sent_count'] > 0]) if recent_days else None,
                'total_emails_sent': sum(r['sent_count'] for r in all_recipients),
                'recent_emails_sent': sum(r['recent_sent_count'] for r in all_recipients) if recent_days else None,
            }
        }
