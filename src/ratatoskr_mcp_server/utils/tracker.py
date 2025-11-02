"""Utilities for querying GNOME TinySPARQL indexer."""

import subprocess
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
import os

from ratatoskr_mcp_server.utils.gsettings import _build_command


def query_sparql(sparql: str) -> List[Dict[str, Any]]:
    """
    Execute a SPARQL query against TinySPARQL.

    Args:
        sparql: SPARQL query string

    Returns:
        List of result dictionaries

    Raises:
        RuntimeError: If query fails
    """
    cmd = _build_command(['tinysparql', 'sparql', '--query', sparql])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"TinySPARQL query failed: {result.stderr}")

        # Parse the output - returns tab-separated values
        lines = result.stdout.strip().split('\n')
        if not lines:
            return []

        # First line might be headers, rest are data
        results = []
        for line in lines:
            if line.strip():
                results.append({'_raw': line})

        return results

    except subprocess.TimeoutExpired:
        raise RuntimeError("TinySPARQL query timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to query TinySPARQL: {e}")


def get_recent_files(directory: str, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recently modified files in a directory.

    Args:
        directory: Directory path to search
        days: Look back this many days (default: 7)
        limit: Maximum number of files to return (default: 50)

    Returns:
        List of file info dicts with url, filename, modified time, file type
    """
    # Convert to file:// URL
    directory_path = Path(directory).resolve()
    directory_url = f"file://{directory_path}"

    # Calculate the date threshold
    threshold = datetime.now() - timedelta(days=days)
    threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

    sparql = f"""
    SELECT ?url ?filename ?modified ?mime
    WHERE {{
        ?url a nfo:FileDataObject ;
             nie:url ?urlstr ;
             nfo:fileName ?filename ;
             nfo:fileLastModified ?modified .
        OPTIONAL {{ ?url nie:mimeType ?mime }}
        FILTER (STRSTARTS(?urlstr, "{directory_url}"))
        FILTER (?modified >= "{threshold_str}"^^xsd:dateTime)
    }}
    ORDER BY DESC(?modified)
    LIMIT {limit}
    """

    try:
        cmd = _build_command(['tinysparql', 'sparql', '--output-format=json', '--query', sparql])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            # TinySPARQL might not be available or directory not indexed
            return []

        # Parse JSON output
        data = json.loads(result.stdout)

        files = []
        for row in data.get('results', {}).get('bindings', []):
            file_info = {
                'url': row.get('url', {}).get('value', ''),
                'filename': row.get('filename', {}).get('value', ''),
                'modified': row.get('modified', {}).get('value', ''),
                'mime_type': row.get('mime', {}).get('value', 'unknown')
            }

            # Convert file:// URL to path
            if file_info['url'].startswith('file://'):
                file_info['path'] = file_info['url'][7:]

            # Parse modified timestamp
            if file_info['modified']:
                try:
                    dt = datetime.fromisoformat(file_info['modified'].replace('Z', '+00:00'))
                    file_info['modified_timestamp'] = dt.isoformat()
                except:
                    pass

            files.append(file_info)

        return files

    except subprocess.TimeoutExpired:
        return []
    except json.JSONDecodeError:
        return []
    except Exception:
        return []


def get_file_type_stats(directory: str, days: int = 7) -> Dict[str, int]:
    """
    Get statistics on file types modified in a directory.

    Args:
        directory: Directory path to search
        days: Look back this many days (default: 7)

    Returns:
        Dictionary mapping mime types to counts
    """
    files = get_recent_files(directory, days=days, limit=1000)

    stats = {}
    for file_info in files:
        mime_type = file_info.get('mime_type', 'unknown')
        stats[mime_type] = stats.get(mime_type, 0) + 1

    return stats


def is_tracker_available() -> bool:
    """
    Check if TinySPARQL is available and running.

    Returns:
        True if TinySPARQL is available, False otherwise
    """
    try:
        # Try a simple query to see if the service responds
        cmd = _build_command([
            'tinysparql', 'query',
            '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
            'SELECT 1 WHERE { }'
        ])
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def get_recent_documents(directory: Optional[str] = None, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recently modified documents (PDFs, office docs, etc.).

    Args:
        directory: Optional directory to filter by (if None, searches all indexed locations)
        days: Look back this many days (default: 7)
        limit: Maximum number of documents to return (default: 50)

    Returns:
        List of document info dicts with url, filename, modified time, mime type
    """
    threshold = datetime.now() - timedelta(days=days)
    threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

    # Build directory filter if provided
    dir_filter = ""
    if directory:
        directory_path = Path(directory).resolve()
        directory_url = f"file://{directory_path}"
        dir_filter = f'FILTER (STRSTARTS(?urlstr, "{directory_url}"))'

    sparql = f"""
    SELECT ?url ?filename ?modified ?mime
    FROM <tracker:Documents>
    WHERE {{
        ?url a nfo:FileDataObject ;
             nie:url ?urlstr ;
             nfo:fileName ?filename ;
             nfo:fileLastModified ?modified ;
             nie:mimeType ?mime .
        {dir_filter}
        FILTER (?modified >= "{threshold_str}"^^xsd:dateTime)
    }}
    ORDER BY DESC(?modified)
    LIMIT {limit}
    """

    try:
        cmd = _build_command(['tinysparql', 'sparql', '--output-format=json', '--query', sparql])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        documents = []

        for row in data.get('results', {}).get('bindings', []):
            doc_info = {
                'url': row.get('url', {}).get('value', ''),
                'filename': row.get('filename', {}).get('value', ''),
                'modified': row.get('modified', {}).get('value', ''),
                'mime_type': row.get('mime', {}).get('value', 'unknown')
            }

            if doc_info['url'].startswith('file://'):
                doc_info['path'] = doc_info['url'][7:]

            if doc_info['modified']:
                try:
                    dt = datetime.fromisoformat(doc_info['modified'].replace('Z', '+00:00'))
                    doc_info['modified_timestamp'] = dt.isoformat()
                except:
                    pass

            documents.append(doc_info)

        return documents
    except:
        return []


def get_recent_images(directory: Optional[str] = None, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recently modified images.

    Args:
        directory: Optional directory to filter by
        days: Look back this many days (default: 7)
        limit: Maximum number of images to return (default: 50)

    Returns:
        List of image info dicts
    """
    threshold = datetime.now() - timedelta(days=days)
    threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

    dir_filter = ""
    if directory:
        directory_path = Path(directory).resolve()
        directory_url = f"file://{directory_path}"
        dir_filter = f'FILTER (STRSTARTS(?urlstr, "{directory_url}"))'

    sparql = f"""
    SELECT ?url ?filename ?modified ?mime
    FROM <tracker:Pictures>
    WHERE {{
        ?url a nfo:FileDataObject ;
             nie:url ?urlstr ;
             nfo:fileName ?filename ;
             nfo:fileLastModified ?modified ;
             nie:mimeType ?mime .
        {dir_filter}
        FILTER (?modified >= "{threshold_str}"^^xsd:dateTime)
    }}
    ORDER BY DESC(?modified)
    LIMIT {limit}
    """

    try:
        cmd = _build_command(['tinysparql', 'sparql', '--output-format=json', '--query', sparql])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        images = []

        for row in data.get('results', {}).get('bindings', []):
            img_info = {
                'url': row.get('url', {}).get('value', ''),
                'filename': row.get('filename', {}).get('value', ''),
                'modified': row.get('modified', {}).get('value', ''),
                'mime_type': row.get('mime', {}).get('value', 'unknown')
            }

            if img_info['url'].startswith('file://'):
                img_info['path'] = img_info['url'][7:]

            if img_info['modified']:
                try:
                    dt = datetime.fromisoformat(img_info['modified'].replace('Z', '+00:00'))
                    img_info['modified_timestamp'] = dt.isoformat()
                except:
                    pass

            images.append(img_info)

        return images
    except:
        return []


def get_recent_media(directory: Optional[str] = None, days: int = 7, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get recently modified media files (audio + video).

    Args:
        directory: Optional directory to filter by
        days: Look back this many days (default: 7)
        limit: Maximum number of files per type (default: 50)

    Returns:
        Dictionary with 'audio' and 'video' keys containing lists of file info
    """
    threshold = datetime.now() - timedelta(days=days)
    threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

    dir_filter = ""
    if directory:
        directory_path = Path(directory).resolve()
        directory_url = f"file://{directory_path}"
        dir_filter = f'FILTER (STRSTARTS(?urlstr, "{directory_url}"))'

    results = {'audio': [], 'video': []}

    # Query audio
    audio_sparql = f"""
    SELECT ?url ?filename ?modified ?mime
    FROM <tracker:Audio>
    WHERE {{
        ?url a nfo:FileDataObject ;
             nie:url ?urlstr ;
             nfo:fileName ?filename ;
             nfo:fileLastModified ?modified ;
             nie:mimeType ?mime .
        {dir_filter}
        FILTER (?modified >= "{threshold_str}"^^xsd:dateTime)
    }}
    ORDER BY DESC(?modified)
    LIMIT {limit}
    """

    # Query video
    video_sparql = f"""
    SELECT ?url ?filename ?modified ?mime
    FROM <tracker:Video>
    WHERE {{
        ?url a nfo:FileDataObject ;
             nie:url ?urlstr ;
             nfo:fileName ?filename ;
             nfo:fileLastModified ?modified ;
             nie:mimeType ?mime .
        {dir_filter}
        FILTER (?modified >= "{threshold_str}"^^xsd:dateTime)
    }}
    ORDER BY DESC(?modified)
    LIMIT {limit}
    """

    try:
        # Get audio files
        cmd = _build_command(['tinysparql', 'sparql', '--output-format=json', '--query', audio_sparql])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            for row in data.get('results', {}).get('bindings', []):
                file_info = {
                    'url': row.get('url', {}).get('value', ''),
                    'filename': row.get('filename', {}).get('value', ''),
                    'modified': row.get('modified', {}).get('value', ''),
                    'mime_type': row.get('mime', {}).get('value', 'unknown')
                }

                if file_info['url'].startswith('file://'):
                    file_info['path'] = file_info['url'][7:]

                if file_info['modified']:
                    try:
                        dt = datetime.fromisoformat(file_info['modified'].replace('Z', '+00:00'))
                        file_info['modified_timestamp'] = dt.isoformat()
                    except:
                        pass

                results['audio'].append(file_info)

        # Get video files
        cmd = _build_command(['tinysparql', 'sparql', '--output-format=json', '--query', video_sparql])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            for row in data.get('results', {}).get('bindings', []):
                file_info = {
                    'url': row.get('url', {}).get('value', ''),
                    'filename': row.get('filename', {}).get('value', ''),
                    'modified': row.get('modified', {}).get('value', ''),
                    'mime_type': row.get('mime', {}).get('value', 'unknown')
                }

                if file_info['url'].startswith('file://'):
                    file_info['path'] = file_info['url'][7:]

                if file_info['modified']:
                    try:
                        dt = datetime.fromisoformat(file_info['modified'].replace('Z', '+00:00'))
                        file_info['modified_timestamp'] = dt.isoformat()
                    except:
                        pass

                results['video'].append(file_info)

    except:
        pass

    return results


def get_file_statistics_by_extension() -> Dict[str, Dict[str, Any]]:
    """
    Get system-wide file statistics organized by file type/extension.

    Returns:
        Dictionary mapping file categories to statistics (count, total_size, examples)
    """
    file_types = {
        'pdfs': {
            'extensions': '\\\\.(pdf|PDF)$',
            'label': 'PDF Documents'
        },
        'images': {
            'extensions': '\\\\.(jpg|jpeg|png|gif|svg|webp|JPG|JPEG|PNG|GIF|SVG|WEBP)$',
            'label': 'Images'
        },
        'videos': {
            'extensions': '\\\\.(mp4|mkv|avi|mov|webm|flv|MP4|MKV|AVI|MOV|WEBM|FLV)$',
            'label': 'Videos'
        },
        'audio': {
            'extensions': '\\\\.(mp3|ogg|flac|wav|m4a|MP3|OGG|FLAC|WAV|M4A)$',
            'label': 'Audio'
        },
        'documents': {
            'extensions': '\\\\.(doc|docx|odt|txt|md|rtf|DOC|DOCX|ODT|TXT|MD|RTF)$',
            'label': 'Text Documents'
        },
        'spreadsheets': {
            'extensions': '\\\\.(xls|xlsx|ods|csv|XLS|XLSX|ODS|CSV)$',
            'label': 'Spreadsheets'
        },
        'archives': {
            'extensions': '\\\\.(zip|tar|gz|bz2|xz|7z|rar|ZIP|TAR|GZ|BZ2|XZ|7Z|RAR)$',
            'label': 'Archives'
        },
        'iso_images': {
            'extensions': '\\\\.(iso|img|ISO|IMG)$',
            'label': 'Disk Images'
        },
    }

    statistics = {}

    for category, info in file_types.items():
        try:
            # Count query
            count_sparql = f"""
            SELECT (COUNT(?file) as ?count)
            WHERE {{
                ?file a nfo:FileDataObject ;
                      nfo:fileName ?filename .
                FILTER(REGEX(?filename, "{info['extensions']}"))
            }}
            """

            cmd = _build_command([
                'tinysparql', 'query',
                '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
                count_sparql
            ])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                count = 0
                # Parse result (format: "Results:\n  <count>")
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    try:
                        count = int(lines[1].strip())
                    except ValueError:
                        pass

                # Total size query
                size_sparql = f"""
                SELECT (SUM(nfo:fileSize(?file)) as ?totalSize)
                WHERE {{
                    ?file a nfo:FileDataObject ;
                          nfo:fileName ?filename ;
                          nfo:fileSize ?size .
                    FILTER(REGEX(?filename, "{info['extensions']}"))
                }}
                """

                cmd = _build_command([
                    'tinysparql', 'query',
                    '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
                    size_sparql
                ])

                size_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                total_size = 0
                if size_result.returncode == 0:
                    lines = size_result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        size_str = lines[1].strip()
                        if size_str and size_str != '(null)':
                            try:
                                total_size = int(size_str)
                            except ValueError:
                                pass

                statistics[category] = {
                    'label': info['label'],
                    'count': count,
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
                    'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2) if total_size else 0,
                }
        except Exception as e:
            statistics[category] = {
                'label': info['label'],
                'count': 0,
                'total_size_bytes': 0,
                'error': str(e)
            }

    return statistics


def get_largest_files(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get the largest files on the system.

    Args:
        limit: Maximum number of files to return (default: 20)

    Returns:
        List of file info dicts with path, filename, and size
    """
    try:
        sparql = f"""
        SELECT ?file ?filename ?size
        WHERE {{
            ?file a nfo:FileDataObject ;
                  nie:url ?file ;
                  nfo:fileName ?filename ;
                  nfo:fileSize ?size .
        }}
        ORDER BY DESC(?size)
        LIMIT {limit}
        """

        cmd = _build_command([
            'tinysparql', 'query',
            '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
            sparql
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return []

        files = []
        lines = result.stdout.strip().split('\n')

        # Skip "Results:" header
        for line in lines[1:]:
            if not line.strip():
                continue

            # Parse line: "file://<path>, <filename>, <size>"
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                file_url = parts[0]
                filename = parts[1]
                try:
                    size = int(parts[2])
                except ValueError:
                    continue

                # Convert file:// URL to path
                path = file_url[7:] if file_url.startswith('file://') else file_url

                files.append({
                    'path': path,
                    'filename': filename,
                    'size_bytes': size,
                    'size_mb': round(size / (1024 * 1024), 2),
                    'size_gb': round(size / (1024 * 1024 * 1024), 2) if size > 1024 * 1024 * 1024 else None,
                })

        return files
    except Exception:
        return []


def get_old_files(days: int = 365, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get files that haven't been modified in a specified number of days.

    Args:
        days: Number of days since last modification (default: 365)
        limit: Maximum number of files to return (default: 50)

    Returns:
        List of file info dicts with path, filename, size, and last modified date
    """
    try:
        threshold = datetime.now() - timedelta(days=days)
        threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

        sparql = f"""
        SELECT ?file ?filename ?modified ?size
        WHERE {{
            ?file a nfo:FileDataObject ;
                  nie:url ?file ;
                  nfo:fileName ?filename ;
                  nfo:fileLastModified ?modified .
            OPTIONAL {{ ?file nfo:fileSize ?size }}
            FILTER (?modified <= "{threshold_str}"^^xsd:dateTime)
        }}
        ORDER BY ASC(?modified)
        LIMIT {limit}
        """

        cmd = _build_command([
            'tinysparql', 'query',
            '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
            sparql
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return []

        files = []
        lines = result.stdout.strip().split('\n')

        # Skip "Results:" header
        for line in lines[1:]:
            if not line.strip():
                continue

            # Parse line: "file://<path>, <filename>, <modified>, <size>"
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                file_url = parts[0]
                filename = parts[1]
                modified = parts[2]
                size = 0
                if len(parts) >= 4 and parts[3] and parts[3] != '(null)':
                    try:
                        size = int(parts[3])
                    except ValueError:
                        pass

                # Convert file:// URL to path
                path = file_url[7:] if file_url.startswith('file://') else file_url

                files.append({
                    'path': path,
                    'filename': filename,
                    'modified': modified,
                    'size_bytes': size,
                    'size_mb': round(size / (1024 * 1024), 2) if size else 0,
                })

        return files
    except Exception:
        return []


def search_files(
    file_type: Optional[str] = None,
    directory: Optional[str] = None,
    min_size_mb: Optional[float] = None,
    max_size_mb: Optional[float] = None,
    min_modified_date: Optional[str] = None,
    max_modified_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Search for files with flexible filtering options.

    Args:
        file_type: File type to search for ('pdf', 'image', 'video', 'audio', 'document',
                   'spreadsheet', 'archive', etc.). If None, searches all files.
        directory: Directory path to search in (e.g., '/home/user/Downloads').
                   If None, searches all indexed directories.
        min_size_mb: Minimum file size in megabytes
        max_size_mb: Maximum file size in megabytes
        min_modified_date: Minimum modification date (ISO 8601 format: '2025-10-01')
        max_modified_date: Maximum modification date (ISO 8601 format: '2025-10-31')
        limit: Maximum number of results to return (default: 100)

    Returns:
        List of dictionaries with file information:
        - path: Full file path
        - filename: File name
        - size_bytes: Size in bytes
        - size_mb: Size in megabytes
        - modified: Last modified date (ISO 8601 format)
    """
    # File type extension mappings (reuse from get_file_statistics_by_extension)
    file_type_patterns = {
        'pdf': '\\\\.(pdf|PDF)$',
        'image': '\\\\.(jpg|jpeg|png|gif|svg|webp|bmp|tiff|JPG|JPEG|PNG|GIF|SVG|WEBP|BMP|TIFF)$',
        'video': '\\\\.(mp4|avi|mkv|mov|wmv|flv|webm|MP4|AVI|MKV|MOV|WMV|FLV|WEBM)$',
        'audio': '\\\\.(mp3|wav|flac|ogg|aac|m4a|wma|MP3|WAV|FLAC|OGG|AAC|M4A|WMA)$',
        'document': '\\\\.(doc|docx|odt|txt|rtf|DOC|DOCX|ODT|TXT|RTF)$',
        'spreadsheet': '\\\\.(xls|xlsx|ods|csv|XLS|XLSX|ODS|CSV)$',
        'presentation': '\\\\.(ppt|pptx|odp|PPT|PPTX|ODP)$',
        'archive': '\\\\.(zip|tar|gz|bz2|xz|7z|rar|ZIP|TAR|GZ|BZ2|XZ|7Z|RAR)$',
        'iso': '\\\\.(iso|img|ISO|IMG)$',
    }

    try:
        # Build FILTER clauses
        filters = []

        # Add file type filter
        if file_type and file_type in file_type_patterns:
            filters.append(f'FILTER(REGEX(?filename, "{file_type_patterns[file_type]}"))')

        # Add directory filter
        if directory:
            # Normalize directory path (remove trailing slash if present)
            dir_path = directory.rstrip('/')
            # Escape for SPARQL regex
            escaped_dir = dir_path.replace('\\', '\\\\\\\\')
            filters.append(f'FILTER(STRSTARTS(STR(?file), "file://{escaped_dir}/"))')

        # Add size filters
        if min_size_mb is not None:
            min_size_bytes = int(min_size_mb * 1024 * 1024)
            filters.append(f'FILTER(?size >= {min_size_bytes})')

        if max_size_mb is not None:
            max_size_bytes = int(max_size_mb * 1024 * 1024)
            filters.append(f'FILTER(?size <= {max_size_bytes})')

        # Add date filters (ISO 8601 format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
        if min_modified_date is not None:
            # If date is in YYYY-MM-DD format, add T00:00:00Z
            if 'T' not in min_modified_date:
                min_modified_date += 'T00:00:00Z'
            filters.append(f'FILTER(?modified >= "{min_modified_date}"^^xsd:dateTime)')

        if max_modified_date is not None:
            # If date is in YYYY-MM-DD format, add T23:59:59Z
            if 'T' not in max_modified_date:
                max_modified_date += 'T23:59:59Z'
            filters.append(f'FILTER(?modified <= "{max_modified_date}"^^xsd:dateTime)')

        # Build SPARQL query
        filters_str = '\n            '.join(filters) if filters else ''
        sparql = f"""
        SELECT DISTINCT ?file ?filename ?size ?modified
        WHERE {{
            ?file a nfo:FileDataObject ;
                  nie:url ?file ;
                  nfo:fileName ?filename ;
                  nfo:fileSize ?size ;
                  nfo:fileLastModified ?modified .
            {filters_str}
        }}
        ORDER BY DESC(?modified)
        LIMIT {limit}
        """

        # Execute query
        cmd = _build_command([
            'tinysparql', 'query',
            '--dbus-service', 'org.freedesktop.Tracker3.Miner.Files',
            sparql
        ])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return []

        # Parse results
        lines = result.stdout.strip().split('\n')
        files = []

        # Skip "Results:" header
        for line in lines[1:]:
            if not line.strip():
                continue

            # Parse line: "file://<path>, <filename>, <size>, <modified>"
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                file_url = parts[0]
                filename = parts[1]
                size = 0
                if parts[2] and parts[2] != '(null)':
                    try:
                        size = int(parts[2])
                    except ValueError:
                        pass

                modified = parts[3] if len(parts) >= 4 else ''

                # Convert file:// URL to path
                path = file_url[7:] if file_url.startswith('file://') else file_url

                files.append({
                    'path': path,
                    'filename': filename,
                    'size_bytes': size,
                    'size_mb': round(size / (1024 * 1024), 2) if size else 0,
                    'modified': modified,
                })

        return files
    except Exception:
        return []


def extract_file_content(file_path: str) -> Dict[str, Any]:
    """
    Extract content and metadata from a file using LocalSearch extractors.

    This uses the native `localsearch extract` command which leverages
    the sandboxed extractors to read content from PDFs, images, and other files.

    Args:
        file_path: Absolute path to the file to extract

    Returns:
        Dictionary containing:
        - success: Whether extraction succeeded
        - file_path: The file path that was extracted
        - metadata: RDF metadata from the file (format, page count, dimensions, etc.)
        - content: Extracted text content (for PDFs and text files)
        - error: Error message if extraction failed
    """
    try:
        # Ensure path is absolute
        abs_path = os.path.abspath(os.path.expanduser(file_path))

        # Check if file exists
        if not os.path.exists(abs_path):
            return {
                'success': False,
                'file_path': file_path,
                'error': f'File not found: {abs_path}'
            }

        # Run localsearch extract command
        cmd = _build_command([
            'localsearch', 'extract', abs_path,
            '--output-format=json-ld'
        ])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {
                'success': False,
                'file_path': abs_path,
                'error': f'Extraction failed: {result.stderr}'
            }

        # Parse the JSON-LD output
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'file_path': abs_path,
                'error': f'Failed to parse extraction output: {str(e)}'
            }

        # Extract relevant information from the JSON-LD
        # The structure is: {"@context": {...}, "@graph": [{...}]}
        graph = data.get('@graph', [])
        if not graph:
            return {
                'success': False,
                'file_path': abs_path,
                'error': 'No data extracted from file'
            }

        file_data = graph[0]

        # Extract text content if available
        content = file_data.get('nie:plainTextContent', '')

        # Extract other useful metadata
        metadata = {}

        # Common metadata fields
        if 'dc:format' in file_data:
            metadata['format'] = file_data['dc:format']
        if 'nfo:pageCount' in file_data:
            metadata['page_count'] = file_data['nfo:pageCount']
        if 'nfo:width' in file_data:
            metadata['width'] = file_data['nfo:width']
        if 'nfo:height' in file_data:
            metadata['height'] = file_data['nfo:height']
        if '@type' in file_data:
            metadata['type'] = file_data['@type']
        if 'dc:title' in file_data:
            metadata['title'] = file_data['dc:title']
        if 'dc:creator' in file_data:
            metadata['creator'] = file_data['dc:creator']
        if 'nie:title' in file_data:
            metadata['nie_title'] = file_data['nie:title']

        # Calculate content stats if text content is available
        content_stats = {}
        if content:
            content_stats['char_count'] = len(content)
            content_stats['word_count'] = len(content.split())
            content_stats['line_count'] = len(content.splitlines())
            # Preview: first 500 characters
            content_stats['preview'] = content[:500] + '...' if len(content) > 500 else content

        return {
            'success': True,
            'file_path': abs_path,
            'filename': os.path.basename(abs_path),
            'metadata': metadata,
            'content': content if content else None,
            'content_stats': content_stats if content_stats else None,
            'raw_data': file_data,  # Include raw RDF data for advanced use
        }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'file_path': file_path,
            'error': 'Extraction timed out after 30 seconds'
        }
    except Exception as e:
        return {
            'success': False,
            'file_path': file_path,
            'error': f'Unexpected error: {str(e)}'
        }
