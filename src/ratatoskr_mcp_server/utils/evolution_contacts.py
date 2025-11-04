"""Evolution contacts utilities for fast SQLite-based contact search."""

import sqlite3
from pathlib import Path
from typing import List, Dict, Optional


class EvolutionContactsManager:
    """Manager for Evolution contacts databases."""

    def __init__(self, contacts_path: Optional[str] = None):
        """Initialize Evolution contacts manager.

        Args:
            contacts_path: Path to Evolution contacts data. Defaults to Flatpak location.
        """
        if contacts_path is None:
            contacts_path = str(Path.home() / '.var/app/org.gnome.Evolution/cache/evolution/addressbook')

        self.contacts_path = Path(contacts_path)

        if not self.contacts_path.exists():
            # Try non-Flatpak location
            contacts_path = str(Path.home() / '.cache/evolution/addressbook')
            self.contacts_path = Path(contacts_path)

            if not self.contacts_path.exists():
                raise ValueError(f"Evolution contacts cache not found at {contacts_path}")

    def _parse_vcard(self, vcard_text: str) -> Dict[str, any]:
        """Parse vCard text into structured contact data.

        Args:
            vcard_text: vCard text content

        Returns:
            Dictionary with parsed contact fields
        """
        contact = {
            'name': None,
            'full_name': None,
            'emails': [],
            'phones': [],
            'org': None,
            'title': None,
            'note': None
        }

        if not vcard_text:
            return contact

        for line in vcard_text.split('\n'):
            line = line.strip()

            # Full name
            if line.startswith('FN:'):
                contact['full_name'] = line[3:]

            # Structured name (N:LastName;FirstName;...)
            elif line.startswith('N:'):
                parts = line[2:].split(';')
                if len(parts) >= 2:
                    last = parts[0].strip()
                    first = parts[1].strip()
                    contact['name'] = f"{first} {last}".strip() if first or last else None

            # Email
            elif line.startswith('EMAIL'):
                email_value = line.split(':', 1)[1] if ':' in line else None
                if email_value:
                    contact['emails'].append(email_value.strip())

            # Phone
            elif line.startswith('TEL'):
                phone_value = line.split(':', 1)[1] if ':' in line else None
                if phone_value:
                    contact['phones'].append(phone_value.strip())

            # Organization
            elif line.startswith('ORG:'):
                contact['org'] = line[4:]

            # Title
            elif line.startswith('TITLE:'):
                contact['title'] = line[6:]

            # Note
            elif line.startswith('NOTE:'):
                contact['note'] = line[5:].replace('\\n', '\n')

        # Use full_name as fallback if name is not set
        if not contact['name'] and contact['full_name']:
            contact['name'] = contact['full_name']

        return contact

    def get_contact_sources(self) -> List[str]:
        """Get list of contact source database paths.

        Returns:
            List of database paths
        """
        db_files = list(self.contacts_path.glob('*/contacts.db'))
        return [str(db) for db in db_files]

    def search_contacts(
        self,
        query: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Search contacts across all sources.

        Args:
            query: General search query (searches name, email, org)
            email: Search by specific email address (case-insensitive partial match)
            name: Search by name (case-insensitive partial match)
            limit: Maximum contacts to return

        Returns:
            List of contact dictionaries
        """
        results = []

        for db_path in self.get_contact_sources():
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                # Build SQL query
                sql = "SELECT uid, vcard, bdata FROM folder"
                conditions = []
                params = []

                if query:
                    # Search in vcard text (contains name, email, org, etc.)
                    conditions.append("vcard LIKE ?")
                    params.append(f"%{query}%")

                if email:
                    conditions.append("vcard LIKE ?")
                    params.append(f"%{email}%")

                if name:
                    conditions.append("vcard LIKE ?")
                    params.append(f"%{name}%")

                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)

                sql += f" LIMIT {limit}"

                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    vcard_text = row['vcard'] if row['vcard'] else row['bdata']

                    if vcard_text:
                        # vcard might be bytes
                        if isinstance(vcard_text, bytes):
                            try:
                                vcard_text = vcard_text.decode('utf-8')
                            except:
                                continue

                        contact_data = self._parse_vcard(vcard_text)

                        # Skip if no useful data
                        if not contact_data['name'] and not contact_data['emails']:
                            continue

                        results.append({
                            'uid': row['uid'],
                            'name': contact_data['name'],
                            'full_name': contact_data['full_name'],
                            'emails': contact_data['emails'],
                            'primary_email': contact_data['emails'][0] if contact_data['emails'] else None,
                            'phones': contact_data['phones'],
                            'organization': contact_data['org'],
                            'title': contact_data['title'],
                            'note': contact_data['note'],
                            'source_db': db_path
                        })

                        if len(results) >= limit:
                            break

                conn.close()

                if len(results) >= limit:
                    break

            except Exception as e:
                # Skip databases that can't be read
                continue

        return results

    def get_contact_by_email(self, email: str) -> Optional[Dict]:
        """Get contact by exact email address match.

        Args:
            email: Email address to search for

        Returns:
            Contact dictionary if found, None otherwise
        """
        results = self.search_contacts(email=email, limit=1)

        # Return exact match if found
        for contact in results:
            if email.lower() in [e.lower() for e in contact['emails']]:
                return contact

        return None

    def get_all_contacts(self, limit: int = 1000) -> List[Dict]:
        """Get all contacts.

        Args:
            limit: Maximum contacts to return

        Returns:
            List of all contacts
        """
        results = []

        for db_path in self.get_contact_sources():
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                rows = conn.execute(
                    f"SELECT uid, vcard, bdata FROM folder LIMIT {limit}"
                ).fetchall()

                for row in rows:
                    vcard_text = row['vcard'] if row['vcard'] else row['bdata']

                    if vcard_text:
                        if isinstance(vcard_text, bytes):
                            try:
                                vcard_text = vcard_text.decode('utf-8')
                            except:
                                continue

                        contact_data = self._parse_vcard(vcard_text)

                        if not contact_data['name'] and not contact_data['emails']:
                            continue

                        results.append({
                            'uid': row['uid'],
                            'name': contact_data['name'],
                            'full_name': contact_data['full_name'],
                            'emails': contact_data['emails'],
                            'primary_email': contact_data['emails'][0] if contact_data['emails'] else None,
                            'phones': contact_data['phones'],
                            'organization': contact_data['org'],
                            'title': contact_data['title'],
                            'note': contact_data['note'],
                            'source_db': db_path
                        })

                        if len(results) >= limit:
                            break

                conn.close()

                if len(results) >= limit:
                    break

            except Exception:
                continue

        return results
