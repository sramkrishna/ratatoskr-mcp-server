"""Markdown to PDF conversion using pandoc."""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional


def check_pandoc_installed() -> bool:
    """Check if pandoc is installed."""
    return shutil.which('pandoc') is not None


def convert_markdown_to_pdf(
    markdown_path: str,
    output_path: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    temporary: bool = False
) -> Dict:
    """
    Convert a markdown file to PDF using pandoc.

    Args:
        markdown_path: Path to the markdown file
        output_path: Optional output PDF path (defaults to same name as markdown with .pdf extension)
        title: Optional document title for PDF metadata
        author: Optional author name for PDF metadata
        temporary: If True, creates PDF in /tmp directory for automatic cleanup (useful for email attachments)

    Returns:
        Dict with:
        - success: bool
        - pdf_path: Path to generated PDF (if successful)
        - error: Error message (if failed)
        - temporary: bool (indicates if PDF is in /tmp)
    """
    try:
        # Check if pandoc is installed
        if not check_pandoc_installed():
            return {
                'success': False,
                'error': 'pandoc is not installed. Install it with: sudo dnf install pandoc'
            }

        # Convert to absolute path and validate
        markdown_path = os.path.abspath(os.path.expanduser(markdown_path))

        if not os.path.exists(markdown_path):
            return {
                'success': False,
                'error': f'Markdown file not found: {markdown_path}'
            }

        if not os.path.isfile(markdown_path):
            return {
                'success': False,
                'error': f'Path is not a file: {markdown_path}'
            }

        # Determine output path
        if output_path:
            output_path = os.path.abspath(os.path.expanduser(output_path))
        elif temporary:
            # Create in /tmp for automatic system cleanup
            import tempfile
            markdown_name = Path(markdown_path).stem
            output_path = os.path.join(tempfile.gettempdir(), f"{markdown_name}.pdf")
        else:
            # Default: same directory and name as markdown, with .pdf extension
            markdown_file = Path(markdown_path)
            output_path = str(markdown_file.with_suffix('.pdf'))

        # Build pandoc command
        cmd = [
            'pandoc',
            markdown_path,
            '-o', output_path,
            '--pdf-engine=xelatex',  # Better Unicode support
            '-V', 'geometry:margin=1in',  # Nice margins
        ]

        # Add metadata if provided
        if title:
            cmd.extend(['-V', f'title={title}'])
        if author:
            cmd.extend(['-V', f'author={author}'])

        # Run pandoc
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return {
                'success': True,
                'pdf_path': output_path,
                'markdown_path': markdown_path,
                'temporary': temporary
            }
        else:
            return {
                'success': False,
                'error': f'pandoc conversion failed: {result.stderr}'
            }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'PDF conversion timed out (file too large or complex)'
        }
    except FileNotFoundError:
        return {
            'success': False,
            'error': 'pandoc command not found'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Conversion error: {str(e)}'
        }


def convert_multiple_markdown_to_pdf(
    markdown_paths: list,
    output_dir: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    temporary: bool = False
) -> Dict:
    """
    Convert multiple markdown files to PDF.

    Args:
        markdown_paths: List of markdown file paths
        output_dir: Optional directory for output PDFs (defaults to same dir as each markdown)
        title: Optional title prefix for all PDFs
        author: Optional author for all PDFs
        temporary: If True, creates PDFs in /tmp directory for automatic cleanup (useful for email attachments)

    Returns:
        Dict with:
        - success: bool
        - converted: List of successfully converted files
        - failed: List of failed conversions with errors
        - pdf_paths: List of all generated PDF paths (for easy attachment to emails)
    """
    if not check_pandoc_installed():
        return {
            'success': False,
            'error': 'pandoc is not installed. Install it with: sudo dnf install pandoc'
        }

    converted = []
    failed = []
    pdf_paths = []

    for markdown_path in markdown_paths:
        # Determine output path
        if output_dir:
            output_dir_abs = os.path.abspath(os.path.expanduser(output_dir))
            os.makedirs(output_dir_abs, exist_ok=True)
            markdown_name = Path(markdown_path).stem
            output_path = os.path.join(output_dir_abs, f"{markdown_name}.pdf")
        else:
            output_path = None

        # Convert
        result = convert_markdown_to_pdf(
            markdown_path=markdown_path,
            output_path=output_path,
            title=title,
            author=author,
            temporary=temporary
        )

        if result['success']:
            converted.append({
                'markdown_path': result['markdown_path'],
                'pdf_path': result['pdf_path']
            })
            pdf_paths.append(result['pdf_path'])
        else:
            failed.append({
                'markdown_path': markdown_path,
                'error': result['error']
            })

    return {
        'success': True,
        'converted': converted,
        'failed': failed,
        'total_converted': len(converted),
        'total_failed': len(failed),
        'pdf_paths': pdf_paths,  # Easy list for email attachments
        'temporary': temporary
    }
