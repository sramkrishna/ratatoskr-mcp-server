"""
Email provider for MCP server.
Provides access to Evolution emails via SQLite.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from ..utils.evolution_email import EvolutionEmailManager
from ..resource_manager import ResourceData
import json


class EmailProvider:
    """Provider for email-related resources and tools."""

    def __init__(self):
        """Initialize the email provider."""
        try:
            self.email_mgr = EvolutionEmailManager()
            self.available = True
        except (ValueError, Exception) as e:
            print(f"Evolution not available: {e}")
            self.email_mgr = None
            self.available = False

    def get_accounts(self) -> ResourceData:
        """Get list of email accounts."""
        if not self.available:
            return ResourceData(
                content={},
                error="Evolution is not available"
            )

        try:
            accounts = self.email_mgr.get_accounts()
            return ResourceData(
                content={
                    'accounts': accounts,
                    'total': len(accounts)
                }
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get email accounts: {str(e)}"
            )

    def get_folders(self, account_name: str) -> ResourceData:
        """Get list of folders for an account."""
        if not self.available:
            return ResourceData(
                content={},
                error="Evolution is not available"
            )

        try:
            folders = self.email_mgr.get_folders(account_name)
            # Convert Path objects to strings for JSON serialization
            folders_data = []
            for folder in folders:
                folders_data.append({
                    'name': folder['name'],
                    'mbox_path': str(folder['mbox_path']),
                    'msf_path': str(folder['msf_path'])
                })

            return ResourceData(
                content={
                    'account': account_name,
                    'folders': folders_data,
                    'total': len(folders_data)
                }
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get folders: {str(e)}"
            )

    async def query_emails(
        self,
        account_name: Optional[str] = None,
        folder_names: Optional[List[str]] = None,
        days_back: int = 7,
        has_attachments: bool = False,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        subject_contains: Optional[str] = None,
        limit: int = 100
    ) -> ResourceData:
        """
        Query emails from Thunderbird.

        Args:
            account_name: Email account name (e.g., 'imap.gmail.com'). If None, searches all accounts.
            folder_names: List of folder names to query (e.g., ['INBOX', 'Sent Mail'])
            days_back: Number of days to look back (default: 7)
            has_attachments: Only return emails with attachments
            sender: Filter by sender email address
            recipient: Filter by recipient email address
            subject_contains: Filter by subject text
            limit: Maximum number of emails to return (default: 100)

        Returns:
            ResourceData with email metadata
        """
        if not self.available:
            return ResourceData(
                content={},
                error="Evolution is not available"
            )

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            # Query Evolution - no timeout needed, it's instant!
            emails = await asyncio.to_thread(
                self.email_mgr.query_emails,
                account_id=account_name,
                folder_name=folder_names[0] if folder_names else None,
                sender=sender,
                recipient=recipient,
                subject=subject_contains,
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )

            return ResourceData(
                content={
                    'query': {
                        'account': account_name,
                        'folders': folder_names,
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'has_attachments': has_attachments,
                        'limit': limit
                    },
                    'total_results': len(emails),
                    'emails': emails
                }
            )
        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to query emails: {str(e)}"
            )

    async def get_email_content(
        self,
        account_id: str,
        folder: str,
        uid: str
    ) -> ResourceData:
        """
        Get full content of a specific email.

        Args:
            account_id: Evolution account ID
            folder: Folder name (e.g., 'INBOX')
            uid: Message UID from query results

        Returns:
            ResourceData with full email content
        """
        if not self.available:
            return ResourceData(
                content={},
                error="Evolution is not available"
            )

        try:
            # Run in thread pool with timeout (30 seconds for single email)
            try:
                email_content = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.email_mgr.read_email_from_maildir,
                        account_id=account_id,
                        folder_name=folder,
                        uid=uid
                    ),
                    timeout=30
                )
            except asyncio.TimeoutError:
                return ResourceData(
                    content={},
                    error="Email content retrieval timed out after 30 seconds. The email may be very large."
                )

            if not email_content:
                return ResourceData(
                    content={},
                    error="Email not found or could not be read"
                )

            return ResourceData(content=email_content)

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to get email content: {str(e)}"
            )

    async def find_ical_emails(
        self,
        account_name: str,
        folder_names: Optional[List[str]] = None,
        days_back: int = 7,
        limit: int = 50
    ) -> ResourceData:
        """
        Find emails with iCal (.ics) attachments.

        Args:
            account_name: Email account name
            folder_names: List of folder names to search
            days_back: Number of days to look back
            limit: Maximum number of emails to return

        Returns:
            ResourceData with emails containing iCal attachments
        """
        if not self.available:
            return ResourceData(
                content={},
                error="Evolution is not available"
            )

        try:
            # Run query in thread pool with timeout
            # Conservative timeouts to avoid hanging Hugin
            if days_back <= 7:
                timeout_seconds = 30  # 30 seconds for 1 week
            elif days_back <= 30:
                timeout_seconds = 60  # 1 minute for 1 month
            else:
                timeout_seconds = min(120, 60 + (days_back - 30) * 2)  # Max 2 minutes

            try:
                ical_emails = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.email_mgr.find_ical_emails,
                        account_name=account_name,
                        folder_names=folder_names,
                        days_back=days_back,
                        limit=limit
                    ),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                return ResourceData(
                    content={},
                    error=f"iCal email search timed out after {timeout_seconds} seconds. Try reducing the date range (currently {days_back} days)."
                )

            # Parse dates for better readability
            for email in ical_emails:
                if 'date' in email and isinstance(email['date'], str):
                    date_obj = self.email_mgr._parse_date(email['date'])
                    if date_obj:
                        email['date_parsed'] = date_obj.isoformat()

            return ResourceData(
                content={
                    'query': {
                        'account': account_name,
                        'folders': folder_names,
                        'days_back': days_back,
                        'limit': limit
                    },
                    'total_results': len(ical_emails),
                    'emails': ical_emails
                }
            )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Failed to find iCal emails: {str(e)}"
            )
