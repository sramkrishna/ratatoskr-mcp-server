"""Safe file operations utilities."""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
import subprocess


# Safety constraints - different limits for different operations
MAX_BATCH_SIZE_TRASH = 10   # Conservative for destructive operations
MAX_BATCH_SIZE_MOVE = 50     # Moderate for moving files
MAX_BATCH_SIZE_COPY = 100    # Generous for non-destructive copying

ALLOWED_BASE_PATHS = ['/home', '/var/home', '/tmp']
FORBIDDEN_PATHS = ['/etc', '/usr', '/bin', '/sbin', '/sys', '/proc', '/dev', '/boot', '/root']


def _is_safe_path(path: str) -> bool:
    """
    Check if a path is safe to operate on.

    Prevents operations on system directories.
    """
    abs_path = os.path.abspath(os.path.expanduser(path))

    # Check if path starts with any forbidden directory
    for forbidden in FORBIDDEN_PATHS:
        if abs_path.startswith(forbidden):
            return False

    # Check if path is within allowed base paths
    is_allowed = False
    for allowed in ALLOWED_BASE_PATHS:
        if abs_path.startswith(allowed):
            is_allowed = True
            break

    return is_allowed


def _validate_file_list(file_paths: List[str], max_size: int) -> Dict[str, Any]:
    """
    Validate a list of file paths for safety.

    Returns dict with 'valid' (bool) and 'error' (str) keys.
    """
    if not file_paths:
        return {'valid': False, 'error': 'No files provided'}

    if len(file_paths) > max_size:
        return {
            'valid': False,
            'error': f'Too many files ({len(file_paths)}). Maximum batch size is {max_size} files.'
        }

    # Check each path for safety
    unsafe_paths = []
    nonexistent_paths = []

    for path in file_paths:
        if not _is_safe_path(path):
            unsafe_paths.append(path)

        abs_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(abs_path):
            nonexistent_paths.append(path)

    if unsafe_paths:
        return {
            'valid': False,
            'error': f'Unsafe paths detected (system directories): {", ".join(unsafe_paths[:3])}'
        }

    if nonexistent_paths:
        return {
            'valid': False,
            'error': f'Files do not exist: {", ".join(nonexistent_paths[:3])}'
        }

    return {'valid': True}


def move_files(file_paths: List[str], destination: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Move files to a destination directory.

    Args:
        file_paths: List of file paths to move (max MAX_BATCH_SIZE)
        destination: Destination directory
        overwrite: Whether to overwrite existing files (default: False)

    Returns:
        Dict with success status, moved files, and any errors
    """
    try:
        # Validate inputs
        validation = _validate_file_list(file_paths, MAX_BATCH_SIZE_MOVE)
        if not validation['valid']:
            return {
                'success': False,
                'error': validation['error'],
                'moved': []
            }

        # Validate destination
        dest_abs = os.path.abspath(os.path.expanduser(destination))
        if not _is_safe_path(dest_abs):
            return {
                'success': False,
                'error': f'Unsafe destination path: {destination}',
                'moved': []
            }

        # Create destination if it doesn't exist
        os.makedirs(dest_abs, exist_ok=True)

        # Move files
        moved = []
        errors = []

        for file_path in file_paths:
            try:
                abs_path = os.path.abspath(os.path.expanduser(file_path))
                filename = os.path.basename(abs_path)
                dest_file = os.path.join(dest_abs, filename)

                # Check for conflicts
                if os.path.exists(dest_file) and not overwrite:
                    errors.append({
                        'file': file_path,
                        'error': f'Destination file exists: {dest_file}'
                    })
                    continue

                # Move the file
                shutil.move(abs_path, dest_file)
                moved.append({
                    'source': file_path,
                    'destination': dest_file
                })

            except Exception as e:
                errors.append({
                    'file': file_path,
                    'error': str(e)
                })

        return {
            'success': len(moved) > 0,
            'moved': moved,
            'errors': errors,
            'total_moved': len(moved),
            'total_errors': len(errors)
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Move operation failed: {str(e)}',
            'moved': []
        }


def copy_files(file_paths: List[str], destination: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Copy files to a destination directory.

    Args:
        file_paths: List of file paths to copy (max MAX_BATCH_SIZE)
        destination: Destination directory
        overwrite: Whether to overwrite existing files (default: False)

    Returns:
        Dict with success status, copied files, and any errors
    """
    try:
        # Validate inputs
        validation = _validate_file_list(file_paths, MAX_BATCH_SIZE_COPY)
        if not validation['valid']:
            return {
                'success': False,
                'error': validation['error'],
                'copied': []
            }

        # Validate destination
        dest_abs = os.path.abspath(os.path.expanduser(destination))
        if not _is_safe_path(dest_abs):
            return {
                'success': False,
                'error': f'Unsafe destination path: {destination}',
                'copied': []
            }

        # Create destination if it doesn't exist
        os.makedirs(dest_abs, exist_ok=True)

        # Copy files
        copied = []
        errors = []

        for file_path in file_paths:
            try:
                abs_path = os.path.abspath(os.path.expanduser(file_path))
                filename = os.path.basename(abs_path)
                dest_file = os.path.join(dest_abs, filename)

                # Check for conflicts
                if os.path.exists(dest_file) and not overwrite:
                    errors.append({
                        'file': file_path,
                        'error': f'Destination file exists: {dest_file}'
                    })
                    continue

                # Copy the file
                shutil.copy2(abs_path, dest_file)  # copy2 preserves metadata
                copied.append({
                    'source': file_path,
                    'destination': dest_file
                })

            except Exception as e:
                errors.append({
                    'file': file_path,
                    'error': str(e)
                })

        return {
            'success': len(copied) > 0,
            'copied': copied,
            'errors': errors,
            'total_copied': len(copied),
            'total_errors': len(errors)
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Copy operation failed: {str(e)}',
            'copied': []
        }


def trash_files(file_paths: List[str]) -> Dict[str, Any]:
    """
    Move files to trash/recycle bin (safe deletion).

    Uses GNOME's trash system via gio trash command.
    Does NOT permanently delete files.

    Args:
        file_paths: List of file paths to trash (max MAX_BATCH_SIZE)

    Returns:
        Dict with success status, trashed files, and any errors
    """
    try:
        # Validate inputs
        validation = _validate_file_list(file_paths, MAX_BATCH_SIZE_TRASH)
        if not validation['valid']:
            return {
                'success': False,
                'error': validation['error'],
                'trashed': []
            }

        # Trash files using gio
        trashed = []
        errors = []

        for file_path in file_paths:
            try:
                abs_path = os.path.abspath(os.path.expanduser(file_path))

                # Use gio trash command (GNOME standard)
                result = subprocess.run(
                    ['flatpak-spawn', '--host', 'gio', 'trash', abs_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    trashed.append({
                        'file': file_path,
                        'status': 'moved to trash'
                    })
                else:
                    errors.append({
                        'file': file_path,
                        'error': result.stderr.strip() or 'Unknown error'
                    })

            except subprocess.TimeoutExpired:
                errors.append({
                    'file': file_path,
                    'error': 'Trash operation timed out'
                })
            except Exception as e:
                errors.append({
                    'file': file_path,
                    'error': str(e)
                })

        return {
            'success': len(trashed) > 0,
            'trashed': trashed,
            'errors': errors,
            'total_trashed': len(trashed),
            'total_errors': len(errors),
            'note': 'Files moved to trash. Can be restored from trash if needed.'
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Trash operation failed: {str(e)}',
            'trashed': []
        }


def rename_file(file_path: str, new_name: str) -> Dict[str, Any]:
    """
    Rename a single file.

    Args:
        file_path: Path to the file to rename
        new_name: New filename (not a full path, just the filename)

    Returns:
        Dict with success status and new path
    """
    try:
        # Validate input
        validation = _validate_file_list([file_path], max_size=1)
        if not validation['valid']:
            return {
                'success': False,
                'error': validation['error']
            }

        abs_path = os.path.abspath(os.path.expanduser(file_path))

        # Ensure new_name is just a filename, not a path
        if '/' in new_name or '\\' in new_name:
            return {
                'success': False,
                'error': 'new_name must be a filename only, not a path'
            }

        # Build new path in same directory
        directory = os.path.dirname(abs_path)
        new_path = os.path.join(directory, new_name)

        # Check if destination already exists
        if os.path.exists(new_path):
            return {
                'success': False,
                'error': f'File already exists: {new_path}'
            }

        # Rename the file
        os.rename(abs_path, new_path)

        return {
            'success': True,
            'old_path': file_path,
            'new_path': new_path,
            'new_name': new_name
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Rename failed: {str(e)}'
        }


def create_directory(directory_path: str, parents: bool = False) -> Dict[str, Any]:
    """
    Create a new directory.

    Args:
        directory_path: Path to the directory to create
        parents: If True, create parent directories as needed (like mkdir -p)

    Returns:
        Dict with success status and created path
    """
    try:
        abs_path = os.path.abspath(os.path.expanduser(directory_path))

        # Validate path safety
        if not _is_safe_path(abs_path):
            return {
                'success': False,
                'error': f'Unsafe directory path: {directory_path}'
            }

        # Check if directory already exists
        if os.path.exists(abs_path):
            if os.path.isdir(abs_path):
                return {
                    'success': False,
                    'error': f'Directory already exists: {abs_path}'
                }
            else:
                return {
                    'success': False,
                    'error': f'A file with this name already exists: {abs_path}'
                }

        # Create the directory
        if parents:
            os.makedirs(abs_path, exist_ok=False)
        else:
            os.mkdir(abs_path)

        return {
            'success': True,
            'path': abs_path,
            'created_parents': parents
        }

    except FileNotFoundError:
        return {
            'success': False,
            'error': f'Parent directory does not exist. Use parents=True to create parent directories.'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Directory creation failed: {str(e)}'
        }


def remove_directory(directory_path: str) -> Dict[str, Any]:
    """
    Remove an empty directory (safe deletion - directory must be empty).

    This only removes empty directories. For non-empty directories,
    files must be moved to trash first.

    Args:
        directory_path: Path to the directory to remove

    Returns:
        Dict with success status
    """
    try:
        abs_path = os.path.abspath(os.path.expanduser(directory_path))

        # Validate path safety
        if not _is_safe_path(abs_path):
            return {
                'success': False,
                'error': f'Unsafe directory path: {directory_path}'
            }

        # Check if path exists
        if not os.path.exists(abs_path):
            return {
                'success': False,
                'error': f'Directory does not exist: {abs_path}'
            }

        # Check if it's actually a directory
        if not os.path.isdir(abs_path):
            return {
                'success': False,
                'error': f'Path is not a directory: {abs_path}'
            }

        # Check if directory is empty
        if os.listdir(abs_path):
            return {
                'success': False,
                'error': f'Directory is not empty: {abs_path}. Move files to trash first.'
            }

        # Remove the empty directory
        os.rmdir(abs_path)

        return {
            'success': True,
            'path': abs_path,
            'note': 'Empty directory removed successfully'
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Directory removal failed: {str(e)}'
        }
