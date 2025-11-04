"""Analyze communication patterns between contacts and email accounts."""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

from ratatoskr_mcp_server.utils.evolution_contacts import EvolutionContactsManager
from ratatoskr_mcp_server.utils.evolution_email import EvolutionEmailManager


class ContactCommunicationAnalyzer:
    """Analyze email communication patterns with contacts."""

    def __init__(self):
        """Initialize the analyzer with Evolution data sources."""
        try:
            self.contacts_manager = EvolutionContactsManager()
        except Exception:
            self.contacts_manager = None

        try:
            self.email_manager = EvolutionEmailManager()
        except Exception:
            self.email_manager = None

    def analyze_contact_emails(
        self,
        my_email_addresses: List[str],
        days_back: int = 365,
        recent_days: Optional[int] = None
    ) -> Dict:
        """Analyze email communications with contacts.

        Args:
            my_email_addresses: List of your email addresses to analyze
            days_back: How many days back to analyze (default: 365 for 1 year)
            recent_days: Optional: analyze most active contacts in recent period (e.g., 120 for 4 months)

        Returns:
            Dictionary with analysis results
        """
        if not self.contacts_manager or not self.email_manager:
            return {"error": "Evolution contacts or email not available"}

        # Get all contacts
        all_contacts = self.contacts_manager.get_all_contacts(limit=10000)

        # Build email→contact mapping
        email_to_contact = {}
        for contact in all_contacts:
            for email in contact['emails']:
                email_to_contact[email.lower()] = contact

        # Analyze emails for each account
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_cutoff = None
        if recent_days:
            recent_cutoff = datetime.now() - timedelta(days=recent_days)

        # Track communications per contact
        contact_emails = defaultdict(lambda: {
            'sent': 0,
            'received': 0,
            'total': 0,
            'recent_sent': 0,
            'recent_received': 0,
            'recent_total': 0,
            'last_sent': None,
            'last_received': None,
            'contact_info': None
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

                # Get all folders for this account
                folders = cursor.execute("SELECT name FROM folders").fetchall()

                for folder_row in folders:
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

                            # ONLY check if this is a sent email (from my account to someone in contacts)
                            # We're analyzing outbound communication only
                            if account_email in from_addr:
                                # Sent email - check recipients
                                for recipient_email in to_addrs.split(','):
                                    recipient_email = recipient_email.strip()
                                    if recipient_email in email_to_contact:
                                        contact = email_to_contact[recipient_email]
                                        key = contact['uid']

                                        contact_emails[key]['sent'] += 1
                                        contact_emails[key]['total'] += 1
                                        contact_emails[key]['contact_info'] = contact

                                        if is_recent:
                                            contact_emails[key]['recent_sent'] += 1
                                            contact_emails[key]['recent_total'] += 1

                                        if not contact_emails[key]['last_sent'] or sent_date > contact_emails[key]['last_sent']:
                                            contact_emails[key]['last_sent'] = sent_date

                            # Track received emails for reference (but don't include in "contacted" total)
                            elif account_email in to_addrs:
                                # Received email - only count if sender is in contacts
                                sender_email = from_addr.strip()
                                if sender_email in email_to_contact:
                                    contact = email_to_contact[sender_email]
                                    key = contact['uid']

                                    contact_emails[key]['received'] += 1
                                    # Don't add to total - only count SENT emails as "contacted"
                                    # This avoids counting mailing lists, GitHub notifications, etc.
                                    contact_emails[key]['contact_info'] = contact

                                    if is_recent:
                                        contact_emails[key]['recent_received'] += 1

                                    if not contact_emails[key]['last_received'] or sent_date > contact_emails[key]['last_received']:
                                        contact_emails[key]['last_received'] = sent_date

                        summary_conn.close()

                    except Exception:
                        continue

                conn.close()

            except Exception:
                continue

        # Build results
        contacted_contacts = []
        for uid, stats in contact_emails.items():
            if stats['sent'] > 0:  # Only contacts we've sent emails to
                contact_info = stats['contact_info']
                contacted_contacts.append({
                    'name': contact_info['name'],
                    'email': contact_info['primary_email'],
                    'sent': stats['sent'],
                    'received': stats['received'],
                    'total': stats['total'],
                    'recent_sent': stats['recent_sent'],
                    'recent_received': stats['recent_received'],
                    'recent_total': stats['recent_total'],
                    'last_sent': stats['last_sent'].isoformat() if stats['last_sent'] else None,
                    'last_received': stats['last_received'].isoformat() if stats['last_received'] else None,
                })

        # Sort by total emails
        contacted_contacts.sort(key=lambda x: x['total'], reverse=True)

        # Find most active in recent period
        most_active_recent = None
        if recent_days:
            recent_sorted = sorted(
                [c for c in contacted_contacts if c['recent_total'] > 0],
                key=lambda x: x['recent_total'],
                reverse=True
            )
            if recent_sorted:
                most_active_recent = recent_sorted[0]

        return {
            'analyzed_accounts': [e for e in my_email_addresses],
            'total_contacts': len(all_contacts),
            'contacted_in_period': len(contacted_contacts),
            'days_analyzed': days_back,
            'recent_days': recent_days,
            'most_active_recent': most_active_recent,
            'top_contacts': contacted_contacts[:20],  # Top 20
            'summary': {
                'total_contacts_in_addressbook': len(all_contacts),
                'contacts_emailed_in_period': len(contacted_contacts),
                'percentage_contacted': round(len(contacted_contacts) / len(all_contacts) * 100, 1) if all_contacts else 0
            }
        }
