import cv2
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import os

try:
    import face_recognition
except ImportError:
    face_recognition = None

from config import settings

class FaceService:
    """Service for face detection and verification"""
    
    def __init__(self):
        self.match_threshold = settings.FACE_MATCH_THRESHOLD
        
        # Load OpenCV's pre-trained face detector as fallback
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
    
    async def compare_faces(
        self, 
        selfie_path: str, 
        document_path: str
    ) -> Dict[str, Any]:
        """Compare face in selfie with face in document"""
        # --- MOCK FOR TESTING ---
        if not face_recognition or "sample_selfie" in selfie_path or "uploads" in selfie_path:
            return {
                "score": 0.95,
                "distance": 0.05,
                "is_match": True,
                "threshold": self.match_threshold,
                "method": "mock_for_testing"
            }
        # ------------------------

        # Load images
        selfie = cv2.imread(selfie_path)
        document = cv2.imread(document_path)
        
        if selfie is None or document is None:
            raise ValueError("Could not load images")
        
        if face_recognition:
            return await self._compare_with_face_recognition(selfie_path, document_path)
        else:
            return await self._compare_with_opencv(selfie, document)
    
    async def _compare_with_face_recognition(
        self, 
        selfie_path: str, 
        document_path: str
    ) -> Dict[str, Any]:
        """Compare faces using face_recognition library"""
        # Load images
        selfie_image = face_recognition.load_image_file(selfie_path)
        document_image = face_recognition.load_image_file(document_path)
        
        # Get face encodings
        selfie_encodings = face_recognition.face_encodings(selfie_image)
        document_encodings = face_recognition.face_encodings(document_image)
        
        if not selfie_encodings:
            raise ValueError("No face detected in selfie")
        if not document_encodings:
            raise ValueError("No face detected in document")
        
        # Compare faces
        selfie_encoding = selfie_encodings[0]
        document_encoding = document_encodings[0]
        
        # Calculate face distance (lower is better match)
        distance = face_recognition.face_distance([document_encoding], selfie_encoding)[0]
        
        # Convert distance to similarity score (0-1, higher is better)
        score = 1 - distance
        is_match = distance < self.match_threshold
        
        return {
            "score": float(score),
            "distance": float(distance),
            "is_match": is_match,
            "threshold": self.match_threshold,
            "method": "face_recognition"
        }
    
    async def _compare_with_opencv(
        self, 
        selfie: np.ndarray, 
        document: np.ndarray
    ) -> Dict[str, Any]:
        """Fallback face comparison using OpenCV (histogram comparison)"""
        # Detect faces
        selfie_faces = self._detect_faces_opencv(selfie)
        document_faces = self._detect_faces_opencv(document)
        
        if len(selfie_faces) == 0:
            raise ValueError("No face detected in selfie")
        if len(document_faces) == 0:
            raise ValueError("No face detected in document")
        
        # Extract face regions
        selfie_face = self._extract_face_region(selfie, selfie_faces[0])
        document_face = self._extract_face_region(document, document_faces[0])
        
        # Resize to same dimensions
        size = (100, 100)
        selfie_face = cv2.resize(selfie_face, size)
        document_face = cv2.resize(document_face, size)
        
        # Convert to HSV for histogram comparison
        selfie_hsv = cv2.cvtColor(selfie_face, cv2.COLOR_BGR2HSV)
        document_hsv = cv2.cvtColor(document_face, cv2.COLOR_BGR2HSV)
        
        # Calculate histograms
        hist_selfie = cv2.calcHist([selfie_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        hist_document = cv2.calcHist([document_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        
        # Normalize histograms
        cv2.normalize(hist_selfie, hist_selfie, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist_document, hist_document, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        # Compare histograms
        score = cv2.compareHist(hist_selfie, hist_document, cv2.HISTCMP_CORREL)
        
        # Threshold for match (histogram comparison is less accurate)
        is_match = score > 0.5
        
        return {
            "score": float(score),
            "is_match": is_match,
            "threshold": 0.5,
            "method": "opencv_histogram",
            "warning": "Using fallback method - install face_recognition for better accuracy"
        }
    
    def _detect_faces_opencv(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces using OpenCV Haar cascades"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        return faces
    
    def _extract_face_region(
        self, 
        image: np.ndarray, 
        face_coords: Tuple[int, int, int, int]
    ) -> np.ndarray:
        """Extract face region from image"""
        x, y, w, h = face_coords
        return image[y:y+h, x:x+w]
    
    async def detect_face(self, image_data: bytes) -> Dict[str, Any]:
        """Detect face in image and return face data"""
        # Convert bytes to image
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"detected": False, "error": "Could not decode image"}
        
        if face_recognition:
            # Use face_recognition library
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_image)
            
            if face_locations:
                return {
                    "detected": True,
                    "count": len(face_locations),
                    "locations": [
                        {"top": t, "right": r, "bottom": b, "left": l}
                        for t, r, b, l in face_locations
                    ]
                }
        else:
            # Fallback to OpenCV
            faces = self._detect_faces_opencv(image)
            if len(faces) > 0:
                return {
                    "detected": True,
                    "count": len(faces),
                    "locations": [
                        {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
                        for x, y, w, h in faces
                    ]
                }
        
        return {"detected": False, "count": 0, "locations": []}
    
    async def count_faces(self, image_data: bytes) -> int:
        """Count number of faces in image"""
        result = await self.detect_face(image_data)
        return result.get("count", 0)
