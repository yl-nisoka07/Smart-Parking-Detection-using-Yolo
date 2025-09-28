import cv2
import json
import numpy as np
from models import ParkingSpace, ParkingHistory, db
from datetime import datetime
from flask import current_app

class ParkingDetector:
    def __init__(self, video_path, json_path, app=None):
        self.video_path = video_path
        self.json_path = json_path
        self.app = app
        
        # Video capture
        self.cap = cv2.VideoCapture(video_path)
        assert self.cap.isOpened(), "Error reading video file"
        
        # Get video properties
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        # Load bounding boxes
        with open(json_path) as f:
            self.bounding_boxes = json.load(f)
        
        # Store reference frame for comparison
        self.reference_frame = None
        self.get_reference_frame()
        
        # Initialize parking spaces in database if not exists
        self.init_parking_spaces()
    
    def get_reference_frame(self):
        """Capture a reference frame (empty parking lot)"""
        ret, frame = self.cap.read()
        if ret:
            self.reference_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Reset video to beginning
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    
    def init_parking_spaces(self):
        # Use application context if available
        if self.app:
            with self.app.app_context():
                # Check if parking spaces already exist
                if ParkingSpace.query.count() == 0:
                    for box in self.bounding_boxes:
                        space = ParkingSpace(space_id=box['id'], is_occupied=False)
                        db.session.add(space)
                    db.session.commit()
        else:
            # Fallback: just print a message
            print("No app context available for database initialization")
    
    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            # Reset video to beginning if we've reached the end
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return None, None
        
        # Run parking detection
        results = self.detect_occupancy(frame)
        
        # Draw bounding boxes on frame
        annotated_frame = self.draw_bounding_boxes(frame.copy(), results)
        
        # Update database with current status
        self.update_parking_status(results)
        
        return annotated_frame, results
    
    def detect_occupancy(self, frame):
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # If we have a reference frame, use frame difference
        if self.reference_frame is not None:
            # Calculate absolute difference between current frame and reference
            frame_diff = cv2.absdiff(self.reference_frame, blurred)
            
            # Apply threshold to highlight changes
            _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)
            
            # Apply morphological operations to clean up the image
            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        else:
            # Fallback: use edge detection
            edges = cv2.Canny(blurred, 50, 150)
            thresh = edges
        
        # Check each parking space for occupancy using multiple methods
        space_status = []
        for box in self.bounding_boxes:
            space_id = box['id']
            points = box['points']
            
            # Convert points to polygon and create mask
            polygon = np.array(points, np.int32)
            mask = np.zeros_like(thresh)
            cv2.fillPoly(mask, [polygon], 255)
            
            # Method 1: Count non-zero pixels in the masked area
            masked = cv2.bitwise_and(thresh, thresh, mask=mask)
            non_zero = cv2.countNonZero(masked)
            
            # Method 2: Analyze color features in the region
            color_analysis = self.analyze_color_features(frame, polygon)
            
            # Method 3: Check for edges (indicating vehicle presence)
            edge_density = self.calculate_edge_density(gray, polygon)
            
            # Combine multiple detection methods
            area = cv2.contourArea(polygon)
            
            # Adjust these thresholds based on your video
            threshold_1 = non_zero > area * 0.15  # 15% of area has changes
            threshold_2 = color_analysis > 0.4    # Color features indicate vehicle
            threshold_3 = edge_density > 0.1      # Edge density indicates vehicle
            
            # If any two methods detect occupancy, mark as occupied
            occupied = sum([threshold_1, threshold_2, threshold_3]) >= 2
            
            space_status.append(occupied)
        
        return space_status
    
    def analyze_color_features(self, frame, polygon):
        """Analyze color features to detect vehicles"""
        # Create mask for the parking space
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255)
        
        # Extract the region of interest
        masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
        
        # Convert to HSV color space for better color analysis
        hsv = cv2.cvtColor(masked_frame, cv2.COLOR_BGR2HSV)
        
        # Calculate color variance - vehicles typically have more color variation
        mean, std_dev = cv2.meanStdDev(hsv, mask=mask)
        color_variance = np.mean(std_dev)
        
        # Normalize the variance value
        normalized_variance = min(color_variance / 50.0, 1.0)
        
        return normalized_variance
    
    def calculate_edge_density(self, gray_frame, polygon):
        """Calculate edge density in the parking space"""
        # Create mask for the parking space
        mask = np.zeros(gray_frame.shape, dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255)
        
        # Detect edges in the frame
        edges = cv2.Canny(gray_frame, 50, 150)
        
        # Count edges in the masked area
        masked_edges = cv2.bitwise_and(edges, edges, mask=mask)
        edge_count = cv2.countNonZero(masked_edges)
        
        # Calculate edge density
        area = cv2.contourArea(polygon)
        edge_density = edge_count / area if area > 0 else 0
        
        return edge_density
    
    def draw_bounding_boxes(self, frame, results):
        # Draw each parking space with color based on occupancy
        for i, box in enumerate(self.bounding_boxes):
            space_id = box['id']
            points = box['points']
            
            # Convert points to polygon
            polygon = np.array(points, np.int32)
            
            # Choose color based on occupancy (red for occupied, green for available)
            color = (0, 0, 255) if results[i] else (0, 255, 0)
            
            # Draw the polygon
            cv2.polylines(frame, [polygon], True, color, 2)
            
            # Fill the polygon with semi-transparent color
            overlay = frame.copy()
            cv2.fillPoly(overlay, [polygon], color)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            
            # Add space ID text
            center_x = int(sum([p[0] for p in points]) / len(points))
            center_y = int(sum([p[1] for p in points]) / len(points))
            cv2.putText(frame, str(space_id), (int(center_x) - 10, int(center_y)), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Add occupancy status text
            status = "Occupied" if results[i] else "Available"
            text_color = (0, 0, 255) if results[i] else (0, 255, 0)
            cv2.putText(frame, status, (int(center_x) - 30, int(center_y) + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        
        # Add timestamp and statistics
        occupied_count = sum(results)
        total_count = len(results)
        utilization = (occupied_count / total_count * 100) if total_count > 0 else 0
        
        cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Occupied: {occupied_count}/{total_count} ({utilization:.1f}%)", 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return frame
    
    def update_parking_status(self, results):
        # Update database with detection results
        if self.app:
            with self.app.app_context():
                for i, status in enumerate(results):
                    space = ParkingSpace.query.filter_by(space_id=i).first()
                    if space and space.is_occupied != status:
                        space.is_occupied = status
                        space.last_updated = datetime.utcnow()
                        
                        # Add to history
                        history = ParkingHistory(space_id=i, occupied=status)
                        db.session.add(history)
                
                db.session.commit()
        else:
            print("No app context available for database update")
    
    def get_parking_status(self):
        if self.app:
            with self.app.app_context():
                return ParkingSpace.query.all()
        return []
    
    def get_parking_history(self, space_id=None):
        if self.app:
            with self.app.app_context():
                if space_id:
                    return ParkingHistory.query.filter_by(space_id=space_id).order_by(ParkingHistory.timestamp.desc()).all()
                return ParkingHistory.query.order_by(ParkingHistory.timestamp.desc()).limit(100).all()
        return []
    
    def release(self):
        self.cap.release()