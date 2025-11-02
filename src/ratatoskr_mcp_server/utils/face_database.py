"""Face database using ChromaDB for vector similarity search."""

import os
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import face_recognition
import numpy as np


# Database configuration
CHROMA_DB_DIR = os.path.expanduser("~/.local/share/ratatoskr-mcp-server/faces_db")
COLLECTION_NAME = "known_faces"


class FaceDatabase:
    """Manages face embeddings in ChromaDB."""

    def __init__(self):
        """Initialize ChromaDB client and collection."""
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=CHROMA_DB_DIR,
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Face embeddings for person recognition"}
        )

    def register_face(
        self,
        person_name: str,
        image_path: str,
        replace_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Register a face from an image.

        Args:
            person_name: Name of the person
            image_path: Path to the image file
            replace_existing: Whether to replace existing faces for this person

        Returns:
            Dict with success status and details
        """
        try:
            # Load image and extract face encoding
            abs_path = os.path.abspath(os.path.expanduser(image_path))

            if not os.path.exists(abs_path):
                return {
                    'success': False,
                    'error': f'Image file not found: {abs_path}'
                }

            image = face_recognition.load_image_file(abs_path)
            face_encodings = face_recognition.face_encodings(image)

            if not face_encodings:
                return {
                    'success': False,
                    'error': 'No face detected in image'
                }

            if len(face_encodings) > 1:
                return {
                    'success': False,
                    'error': f'Multiple faces detected ({len(face_encodings)}). Please provide image with single face.'
                }

            face_encoding = face_encodings[0]

            # Check if person already has faces registered
            if replace_existing:
                # Remove existing faces for this person
                existing = self.collection.get(
                    where={"person_name": person_name}
                )
                if existing['ids']:
                    self.collection.delete(ids=existing['ids'])

            # Generate unique ID
            import uuid
            face_id = f"{person_name}_{uuid.uuid4().hex[:8]}"

            # Store in ChromaDB
            self.collection.add(
                embeddings=[face_encoding.tolist()],
                documents=[person_name],
                metadatas=[{
                    "person_name": person_name,
                    "source_image": abs_path,
                    "face_id": face_id
                }],
                ids=[face_id]
            )

            return {
                'success': True,
                'person_name': person_name,
                'face_id': face_id,
                'source_image': abs_path
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to register face: {str(e)}'
            }

    def identify_faces(
        self,
        image_path: str,
        confidence_threshold: float = 0.6
    ) -> Dict[str, Any]:
        """
        Identify faces in an image.

        Args:
            image_path: Path to the image file
            confidence_threshold: Similarity threshold (0-1, lower = more strict)

        Returns:
            Dict with identified people and confidence scores
        """
        try:
            abs_path = os.path.abspath(os.path.expanduser(image_path))

            if not os.path.exists(abs_path):
                return {
                    'success': False,
                    'error': f'Image file not found: {abs_path}'
                }

            # Extract face encodings from image
            image = face_recognition.load_image_file(abs_path)
            face_locations = face_recognition.face_locations(image)
            face_encodings = face_recognition.face_encodings(image, face_locations)

            if not face_encodings:
                return {
                    'success': True,
                    'faces_found': 0,
                    'identified_people': []
                }

            identified_people = []

            for face_encoding in face_encodings:
                # Query ChromaDB for similar faces
                results = self.collection.query(
                    query_embeddings=[face_encoding.tolist()],
                    n_results=1
                )

                if results['distances'] and results['distances'][0]:
                    distance = results['distances'][0][0]
                    # Convert distance to confidence (0 = perfect match)
                    confidence = 1.0 - distance

                    if confidence >= confidence_threshold:
                        metadata = results['metadatas'][0][0]
                        identified_people.append({
                            'person_name': metadata['person_name'],
                            'confidence': round(confidence, 3),
                            'face_id': metadata['face_id']
                        })

            return {
                'success': True,
                'faces_found': len(face_encodings),
                'identified_people': identified_people
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to identify faces: {str(e)}'
            }

    def list_registered_people(self) -> Dict[str, Any]:
        """
        List all registered people.

        Returns:
            Dict with list of people and their face counts
        """
        try:
            all_faces = self.collection.get()

            if not all_faces['metadatas']:
                return {
                    'success': True,
                    'total_people': 0,
                    'people': []
                }

            # Count faces per person
            people_counts = {}
            for metadata in all_faces['metadatas']:
                person_name = metadata['person_name']
                if person_name not in people_counts:
                    people_counts[person_name] = 0
                people_counts[person_name] += 1

            people = [
                {'name': name, 'face_count': count}
                for name, count in sorted(people_counts.items())
            ]

            return {
                'success': True,
                'total_people': len(people),
                'people': people
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to list people: {str(e)}'
            }

    def remove_person(self, person_name: str) -> Dict[str, Any]:
        """
        Remove all faces for a person.

        Args:
            person_name: Name of the person to remove

        Returns:
            Dict with success status
        """
        try:
            existing = self.collection.get(
                where={"person_name": person_name}
            )

            if not existing['ids']:
                return {
                    'success': False,
                    'error': f'No faces found for person: {person_name}'
                }

            self.collection.delete(ids=existing['ids'])

            return {
                'success': True,
                'person_name': person_name,
                'faces_removed': len(existing['ids'])
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to remove person: {str(e)}'
            }
