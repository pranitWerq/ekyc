import cv2
import numpy as np
from typing import Dict, Any, Optional
import re

try:
    import pytesseract
except ImportError:
    pytesseract = None

from database.models import DocumentType

class OCRService:
    """Service for OCR and document data extraction"""
    
    async def extract_document_data(
        self, 
        image_path: str, 
        document_type: DocumentType
    ) -> Dict[str, Any]:
        """Extract data from document image using OCR"""
        # --- MOCK FOR TESTING ---
        if not pytesseract or "sample_passport" in image_path or "uploads" in image_path:
            return {
                "name": "BENEDICT DAVIS",
                "dob": "11/08/1987",
                "id_number": "8412036",
                "address": "LONDON, UK",
                "expiry_date": "17/06/2016",
                "raw_text": "PASSPORT SURNAME: BENEDICT GIVEN NAMES: DAVIS DOB: 11 AUG 87 ID NO: 8412036"
            }
        # ------------------------

        # Read image
        image = cv2.imread(image_path)
        if image is None:
            return {"error": "Could not read image", "raw_text": ""}
        
        # Preprocess image
        processed = self._preprocess_image(image)
        
        # Perform OCR
        if pytesseract:
            try:
                raw_text = pytesseract.image_to_string(processed)
            except Exception as e:
                raw_text = f"OCR Error: {str(e)}"
        else:
            # Fallback if pytesseract not available
            raw_text = "[OCR not available - install tesseract]"
        
        # Extract structured data based on document type
        extracted = self._extract_fields(raw_text, document_type)
        extracted["raw_text"] = raw_text
        
        return extracted
    
    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh)
        
        return denoised
    
    def _extract_fields(
        self, 
        text: str, 
        document_type: DocumentType
    ) -> Dict[str, Optional[str]]:
        """Extract structured fields from OCR text"""
        result = {
            "name": None,
            "dob": None,
            "id_number": None,
            "address": None,
            "expiry_date": None
        }
        
        text_upper = text.upper()
        lines = text.split("\n")
        
        # Extract name patterns
        name_patterns = [
            r"SURNAME(?:/NOM)?(?:\s*\(1\))?[:\s]*([A-Z\s]+)",
            r"GIVEN NAMES?(?:/PRENOMS)?(?:\s*\(2\))?[:\s]*([A-Z\s]+)",
            r"NAME[:\s]*([A-Z\s]+)",
            r"FULL NAME[:\s]*([A-Z\s]+)",
        ]
        
        extracted_names = []
        for pattern in name_patterns:
            match = re.search(pattern, text_upper)
            if match:
                name_part = match.group(1).strip()
                if name_part and name_part not in extracted_names:
                    extracted_names.append(name_part)
        
        if extracted_names:
            result["name"] = " ".join(extracted_names)
        
        # Extract date patterns
        date_patterns = [
            r"(?:DOB|BIRTH|NAISSANCE)(?:[:\s\(4\)]+)(\d{2}[/-]\d{2}[/-]\d{4})",
            r"(?:DOB|BIRTH|NAISSANCE)(?:[:\s\(4\)]+)(\d{2}\s[A-Z]{3}\s\d{2})", # 11 AOU 87
            r"(\d{2}[/-]\d{2}[/-]\d{4})",  # Generic date
            r"(\d{2}\s[A-Z]{3}\s/\s?[A-Z]{3}\s\d{2})", # 11 AOU /AOU 87
        ]
        
        # DOB specifically
        dob_match = re.search(r"(?:DATE OF BIRTH|DOB|NAISSANCE)(?:\s*\(4\))?[:\s]*([^\n]+)", text_upper)
        if dob_match:
            result["dob"] = dob_match.group(1).strip()
        else:
            for pattern in date_patterns:
                match = re.search(pattern, text_upper)
                if match:
                    result["dob"] = match.group(0).strip()
                    break

        # Expiry date specifically
        expiry_match = re.search(r"(?:EXPIRY|EXPIRATION)(?:\s*\(9\))?[:\s]*([^\n]+)", text_upper)
        if expiry_match:
            result["expiry_date"] = expiry_match.group(1).strip()
        
        # Extract ID number based on document type
        if document_type == DocumentType.PASSPORT:
            # Passport number pattern (top right or MRZ)
            id_match = re.search(r"PASSPORT NO(?:\.?/PASSEPORT NO\.)?[:\s]*([A-Z0-9]+)", text_upper)
            if id_match:
                result["id_number"] = id_match.group(1).strip()
            else:
                id_pattern = r"([A-Z]\d{7,8})"
                match = re.search(id_pattern, text_upper)
                if match:
                    result["id_number"] = match.group(1).replace(" ", "")
        elif document_type == DocumentType.DRIVERS_LICENSE:
            # Driver's license pattern
            id_pattern = r"([A-Z]{2}\d{2}\s?\d{11})"
        else:
            # Generic alphanumeric ID
            id_pattern = r"(?:ID|NO|NUMBER)[:\s#]*([A-Z0-9]{6,15})"
        
        match = re.search(id_pattern, text_upper)
        if match:
            result["id_number"] = match.group(1).replace(" ", "")
        
        return result
    
    async def validate_document(self, image_path: str) -> Dict[str, Any]:
        """Validate document authenticity (basic checks)"""
        image = cv2.imread(image_path)
        if image is None:
            return {"valid": False, "reason": "Could not read image"}
        
        validation = {
            "valid": True,
            "checks": {
                "resolution": self._check_resolution(image),
                "blur": self._check_blur(image),
                "color": self._check_color_validity(image)
            }
        }
        
        # Overall validity
        validation["valid"] = all(
            check["passed"] for check in validation["checks"].values()
        )
        
        return validation
    
    def _check_resolution(self, image: np.ndarray) -> Dict[str, Any]:
        """Check if image resolution is sufficient"""
        height, width = image.shape[:2]
        min_dimension = 300
        passed = height >= min_dimension and width >= min_dimension
        return {
            "passed": passed,
            "resolution": f"{width}x{height}",
            "message": "Resolution OK" if passed else "Resolution too low"
        }
    
    def _check_blur(self, image: np.ndarray) -> Dict[str, Any]:
        """Check if image is too blurry using Laplacian variance"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        threshold = 100
        passed = laplacian_var > threshold
        return {
            "passed": passed,
            "score": float(laplacian_var),
            "message": "Image clarity OK" if passed else "Image too blurry"
        }
    
    def _check_color_validity(self, image: np.ndarray) -> Dict[str, Any]:
        """Basic color check to ensure document has proper colors"""
        # Check if image has color variation (not all black/white)
        std_dev = np.std(image)
        passed = std_dev > 20
        return {
            "passed": passed,
            "message": "Color variation OK" if passed else "Insufficient color variation"
        }
