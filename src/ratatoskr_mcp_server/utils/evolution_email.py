"""Evolution email utilities for fast SQLite-based email search."""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import configparser


class EvolutionEmailManager:
    """Manager for Evolution email databases."""

    def __init__(self, evolution_path: Optional[str] = None, sources_path: Optional[str] = None):
        """Initialize Evolution email manager.

        Args:
            evolution_path: Path to Evolution data. Defaults to Flatpak location.
            sources_path: Path to Evolution sources config. Defaults to Flatpak location.
        """
        if evolution_path is None:
            evolution_path = str(Path.home() / '.var/app/org.gnome.Evolution/cache/evolution/mail')

        if sources_path is None:
            sources_path = str(Path.home() / '.var/app/org.gnome.Evolution/config/evolution/sources')

        self.mail_path = Path(evolution_path)
        self.sources_path = Path(sources_path)

        if not self.mail_path.exists():
            raise ValueError(f"Evolution mail cache not found at {evolution_path}")

    def _get_email_address_for_account(self, account_id: str) -> Optional[str]:
        """Get email address for an account ID by searching Evolution source files.

        Args:
            account_id: The account ID (hash) from the mail cache folder

        Returns:
            Email address if found, None otherwise
        """
        if not self.sources_path.exists():
            return None

        # Look for a source file named after the account_id
        source_file = self.sources_path / f"{account_id}.source"
        if source_file.exists():
            try:
                config = configparser.ConfigParser()
                config.read(source_file)

                # Try to get email from Authentication section (most common)
                if config.has_option('Authentication', 'User'):
                    user = config.get('Authentication', 'User')
                    # For regular accounts, User is the email
                    # For OAuth2 (Microsoft365, Google), User might be an ID
                    if '@' in user:
                        return user

                # Fallback: Try DisplayName in Data Source section
                # This works for OAuth2 accounts where User is not an email
                if config.has_option('Data Source', 'DisplayName'):
                    display_name = config.get('Data Source', 'DisplayName')
                    # Check if it looks like an email
                    if '@' in display_name:
                        return display_name

            except Exception:
                pass

        return None

    def get_accounts(self) -> List[Dict]:
        """Get list of Evolution email accounts with email addresses."""
        accounts = []

        # Find all folders.db files (one per account)
        for db_path in self.mail_path.glob('*/folders.db'):
            account_id = db_path.parent.name

            # Check if this account has any emails
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                'SELECT SUM(saved_count) as total FROM folders'
            ).fetchone()

            conn.close()

            if row and row['total'] and row['total'] > 0:
                # Get email address from Evolution source files
                email_address = self._get_email_address_for_account(account_id)

                accounts.append({
                    'account_id': account_id,
                    'email_address': email_address or 'Unknown',
                    'db_path': str(db_path),
                    'email_count': row['total']
                })

        return accounts

    def get_folders(self, account_id: str) -> List[Dict]:
        """Get folders for an account."""
        db_path = self.mail_path / account_id / 'folders.db'
        if not db_path.exists():
            return []

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            'SELECT folder_name, saved_count, unread_count FROM folders WHERE saved_count > 0'
        ).fetchall()

        conn.close()

        return [dict(row) for row in rows]

    def _find_messages_table(self, conn: sqlite3.Connection) -> Optional[str]:
        """Find which messages_* table has data."""
        # Evolution uses multiple messages_N tables
        # Find the one with the most rows
        for i in range(1, 30):  # Check up to messages_30
            table_name = f'messages_{i}'
            try:
                row = conn.execute(f'SELECT COUNT(*) as count FROM {table_name}').fetchone()
                if row and row['count'] > 0:
                    return table_name
            except sqlite3.OperationalError:
                # Table doesn't exist
                continue

        return None

    def query_emails(
        self,
        account_id: Optional[str] = None,
        folder_name: Optional[str] = None,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        subject: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query emails from Evolution.

        Args:
            account_id: Specific account ID to search, or None for all accounts
            folder_name: Specific folder name (e.g., 'INBOX')
            sender: Filter by sender email
            recipient: Filter by recipient email
            subject: Filter by subject text
            start_date: Filter emails after this date
            end_date: Filter emails before this date
            limit: Maximum results

        Returns:
            List of email dictionaries
        """
        results = []

        # Determine which accounts to search
        if account_id:
            accounts = [{'account_id': account_id}]
        else:
            accounts = self.get_accounts()

        for account in accounts:
            acc_id = account['account_id']
            db_path = self.mail_path / acc_id / 'folders.db'

            if not db_path.exists():
                continue

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Find the messages table
            messages_table = self._find_messages_table(conn)
            if not messages_table:
                conn.close()
                continue

            # Build query
            conditions = []
            params = []

            if sender:
                conditions.append('mail_from LIKE ?')
                params.append(f'%{sender}%')

            if recipient:
                conditions.append('(mail_to LIKE ? OR mail_cc LIKE ?)')
                params.extend([f'%{recipient}%', f'%{recipient}%'])

            if subject:
                conditions.append('subject LIKE ?')
                params.append(f'%{subject}%')

            if start_date:
                conditions.append('dsent >= ?')
                params.append(int(start_date.timestamp()))

            if end_date:
                conditions.append('dsent <= ?')
                params.append(int(end_date.timestamp()))

            where_clause = ' AND '.join(conditions) if conditions else '1=1'

            query = f'''
                SELECT
                    uid,
                    subject,
                    mail_from as sender,
                    mail_to as recipients,
                    mail_cc as cc,
                    datetime(dsent, 'unixepoch', 'localtime') as date,
                    dsent as date_timestamp,
                    size,
                    flags
                FROM {messages_table}
                WHERE {where_clause}
                ORDER BY dsent DESC
                LIMIT ?
            '''

            params.append(limit - len(results))

            try:
                rows = conn.execute(query, params).fetchall()

                for row in rows:
                    email_dict = dict(row)
                    email_dict['account_id'] = acc_id
                    email_dict['folder'] = folder_name or 'INBOX'
                    results.append(email_dict)

                    if len(results) >= limit:
                        break

            except Exception as e:
                print(f"Error querying {acc_id}: {e}")

            conn.close()

            if len(results) >= limit:
                break

        return results[:limit]

    def get_email_content(self, account_id: str, uid: str) -> Optional[Dict]:
        """Get full email content by UID.

        Note: Evolution stores email bodies in separate mbox files.
        This returns the metadata only.
        """
        db_path = self.mail_path / account_id / 'folders.db'
        if not db_path.exists():
            return None

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        messages_table = self._find_messages_table(conn)
        if not messages_table:
            conn.close()
            return None

        row = conn.execute(
            f'SELECT * FROM {messages_table} WHERE uid = ?',
            (uid,)
        ).fetchone()

        conn.close()

        if row:
            return dict(row)

        return None
