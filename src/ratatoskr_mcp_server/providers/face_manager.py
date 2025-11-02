"""Provider for face registration and management."""

from ratatoskr_mcp_server.providers.base import ResourceProvider
from ratatoskr_mcp_server.resource_manager import ResourceData
from ratatoskr_mcp_server.utils.face_database import FaceDatabase


class FaceManagerProvider(ResourceProvider):
    """Provides face registration and management functionality."""

    def __init__(self):
        """Initialize face database."""
        self.face_db = FaceDatabase()

    async def get_resource(
        self,
        action: str,
        person_name: str = None,
        image_path: str = None,
        replace_existing: bool = False,
        confidence_threshold: float = 0.6
    ) -> ResourceData:
        """
        Manage face registration and recognition.

        Args:
            action: Action to perform (register, identify, list, remove)
            person_name: Name of the person
            image_path: Path to image file
            replace_existing: Whether to replace existing faces
            confidence_threshold: Similarity threshold for identification

        Returns:
            ResourceData with results
        """
        try:
            if action == "register":
                if not person_name or not image_path:
                    return ResourceData(
                        content={},
                        error="Both person_name and image_path are required for registration"
                    )

                result = self.face_db.register_face(
                    person_name=person_name,
                    image_path=image_path,
                    replace_existing=replace_existing
                )

                if not result['success']:
                    return ResourceData(
                        content={'person_name': person_name},
                        error=result['error']
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'action': 'register',
                        'person_name': result['person_name'],
                        'face_id': result['face_id'],
                        'source_image': result['source_image'],
                        'message': f"Face registered for {result['person_name']}"
                    }
                )

            elif action == "identify":
                if not image_path:
                    return ResourceData(
                        content={},
                        error="image_path is required for identification"
                    )

                result = self.face_db.identify_faces(
                    image_path=image_path,
                    confidence_threshold=confidence_threshold
                )

                if not result['success']:
                    return ResourceData(
                        content={},
                        error=result['error']
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'action': 'identify',
                        'image_path': image_path,
                        'faces_found': result['faces_found'],
                        'identified_people': result['identified_people']
                    }
                )

            elif action == "list":
                result = self.face_db.list_registered_people()

                if not result['success']:
                    return ResourceData(
                        content={},
                        error=result['error']
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'action': 'list',
                        'total_people': result['total_people'],
                        'people': result['people']
                    }
                )

            elif action == "remove":
                if not person_name:
                    return ResourceData(
                        content={},
                        error="person_name is required for removal"
                    )

                result = self.face_db.remove_person(person_name=person_name)

                if not result['success']:
                    return ResourceData(
                        content={'person_name': person_name},
                        error=result['error']
                    )

                return ResourceData(
                    content={
                        'success': True,
                        'action': 'remove',
                        'person_name': result['person_name'],
                        'faces_removed': result['faces_removed'],
                        'message': f"Removed {result['faces_removed']} face(s) for {result['person_name']}"
                    }
                )

            else:
                return ResourceData(
                    content={},
                    error=f"Unknown action: {action}. Valid actions: register, identify, list, remove"
                )

        except Exception as e:
            return ResourceData(
                content={},
                error=f"Face management failed: {str(e)}"
            )

    def close(self) -> None:
        """Clean up resources."""
        pass
