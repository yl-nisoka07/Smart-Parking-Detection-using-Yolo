import cv2
import json
import numpy as np
from ultralytics import YOLO
from models import ParkingSpace, ParkingHistory, db
from datetime import datetime
from flask import current_app

class YOLOParkingDetector:
    def __init__(self, video_path, json_path, model_path="yolov11n_- visdrone.pt", app=None):
        self.video_path = video_path
        self.json_path = json_path
        self.app = app
        
        # Load YOLO model
        self.model = YOLO(model_path)
        self.model.conf = 0.3  # Confidence threshold
        self.model.iou = 0.5   # IOU threshold
        
        # Define vehicle classes (adjust based on your model's classes)
        self.vehicle_classes = [3,4,8]  # car, motorcycle, bus, truck (common in visdrone)
        
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
        
        # Initialize parking spaces in database if not exists
        self.init_parking_spaces()
    
    def init_parking_spaces(self):
        if self.app:
            with self.app.app_context():
                if ParkingSpace.query.count() == 0:
                    for box in self.bounding_boxes:
                        space = ParkingSpace(space_id=box['id'], is_occupied=False)
                        db.session.add(space)
                    db.session.commit()
        else:
            print("No app context available for database initialization")
    
    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            # Reset video to beginning if we've reached the end
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return None, None
        
        # Run YOLO detection
        results = self.model(frame, verbose=False)
        
        # Process detections for parking occupancy
        occupancy_results = self.detect_parking_occupancy(frame, results)
        
        # Draw bounding boxes on frame
        annotated_frame = self.draw_bounding_boxes(frame.copy(), occupancy_results, results)
        
        # Update database with current status
        self.update_parking_status(occupancy_results)
        
        return annotated_frame, occupancy_results
    
    def detect_parking_occupancy(self, frame, yolo_results):
        """Detect parking occupancy using YOLO detections"""
        space_status = [False] * len(self.bounding_boxes)
        
        if len(yolo_results) == 0:
            return space_status
        
        # Get detections
        detections = yolo_results[0].boxes
        
        if detections is None or len(detections) == 0:
            return space_status
        
        # Process each parking space
        for i, box in enumerate(self.bounding_boxes):
            space_id = box['id']
            points = box['points']
            
            # Convert points to polygon
            polygon = np.array(points, np.int32)
            
            # Check if any vehicle detection overlaps with this parking space
            is_occupied = self.check_space_occupancy(detections, polygon)
            space_status[i] = is_occupied
        
        return space_status
    
    def check_space_occupancy(self, detections, parking_polygon):
        """Check if a parking space is occupied by any vehicle detection"""
        for detection in detections:
            # Check if detection is a vehicle
            class_id = int(detection.cls.item())
            if class_id not in self.vehicle_classes:
                continue
            
            # Get detection bounding box
            x1, y1, x2, y2 = detection.xyxy[0].tolist()
            detection_center = ((x1 + x2) / 2, (y1 + y2) / 2)
            
            # Check if detection center is inside parking polygon
            if self.point_in_polygon(detection_center, parking_polygon):
                return True
            
            # Additional check: if significant overlap exists
            if self.calculate_iou([x1, y1, x2, y2], parking_polygon) > 0.3:
                return True
        
        return False
    
    def point_in_polygon(self, point, polygon):
        """Check if a point is inside a polygon using ray casting algorithm"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def calculate_iou(self, detection_box, parking_polygon):
        """Calculate Intersection over Union between detection box and parking polygon"""
        # Convert polygon to bounding box
        poly_points = np.array(parking_polygon)
        poly_x = poly_points[:, 0]
        poly_y = poly_points[:, 1]
        poly_bbox = [min(poly_x), min(poly_y), max(poly_x), max(poly_y)]
        
        # Calculate intersection area
        x1 = max(detection_box[0], poly_bbox[0])
        y1 = max(detection_box[1], poly_bbox[1])
        x2 = min(detection_box[2], poly_bbox[2])
        y2 = min(detection_box[3], poly_bbox[3])
        
        if x2 < x1 or y2 < y1:
            return 0.0
        
        intersection_area = (x2 - x1) * (y2 - y1)
        
        # Calculate union area
        detection_area = (detection_box[2] - detection_box[0]) * (detection_box[3] - detection_box[1])
        poly_area = (poly_bbox[2] - poly_bbox[0]) * (poly_bbox[3] - poly_bbox[1])
        union_area = detection_area + poly_area - intersection_area
        
        return intersection_area / union_area if union_area > 0 else 0.0
    
    def get_best_parking_spaces(self, available_spaces):
        """
        Simple ranking: spaces closer to entrance are better
        """
        if not available_spaces:
            return []
        
        # Define entrance point (top-left corner of video)
        entrance_point = (0, 0)
        
        ranked_spaces = []
        for space_id in available_spaces:
            box = self.bounding_boxes[space_id]
            points = box['points']
            
            # Calculate center of parking space
            center_x = sum([p[0] for p in points]) / len(points)
            center_y = sum([p[1] for p in points]) / len(points)
            
            # Simple distance calculation
            distance = ((center_x - entrance_point[0])**2 + (center_y - entrance_point[1])**2)**0.5
            
            ranked_spaces.append((space_id, distance))
        
        # Sort by distance (closest first)
        ranked_spaces.sort(key=lambda x: x[1])
        return [space[0] for space in ranked_spaces]
    
    def draw_bounding_boxes(self, frame, occupancy_results, yolo_results):
        # Draw parking spaces
        for i, box in enumerate(self.bounding_boxes):
            space_id = box['id']
            points = box['points']
            
            polygon = np.array(points, np.int32)
            color = (0, 0, 255) if occupancy_results[i] else (0, 255, 0)
            
            # Draw parking space
            cv2.polylines(frame, [polygon], True, color, 2)
            
            # Semi-transparent fill
            overlay = frame.copy()
            cv2.fillPoly(overlay, [polygon], color)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            
            # Add space ID and status
            center_x = int(sum([p[0] for p in points]) / len(points))
            center_y = int(sum([p[1] for p in points]) / len(points))
            
            cv2.putText(frame, str(space_id), (int(center_x) - 10, int(center_y)), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            status = "Occupied" if occupancy_results[i] else "Available"
            text_color = (0, 0, 255) if occupancy_results[i] else (0, 255, 0)
            cv2.putText(frame, status, (int(center_x) - 30, int(center_y) + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        
        '''# Draw YOLO detections
        if len(yolo_results) > 0:
            detections = yolo_results[0].boxes
            if detections is not None:
                for detection in detections:
                    x1, y1, x2, y2 = detection.xyxy[0].tolist()
                    conf = detection.conf.item()
                    class_id = int(detection.cls.item())
                    
                    # Only draw vehicle detections
                    if class_id in self.vehicle_classes:
                        label = f"{self.model.names[class_id]} {conf:.2f}"
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)
                        cv2.putText(frame, label, (int(x1), int(y1) - 10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)'''
        
        # Add statistics
        occupied_count = sum(occupancy_results)
        total_count = len(occupancy_results)
        utilization = (occupied_count / total_count * 100) if total_count > 0 else 0
        
        cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Occupied: {occupied_count}/{total_count} ({utilization:.1f}%)", 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        available_spaces = [i for i, occupied in enumerate(occupancy_results) if not occupied]
        best_spaces = self.get_best_parking_spaces(available_spaces)
        
        # Highlight top 3 best spaces
        for i, space_id in enumerate(best_spaces[:3]):
            box = self.bounding_boxes[space_id]
            points = box['points']
            polygon = np.array(points, np.int32)
            
            # Gold border for best spots
            color = (0, 215, 255)  # Gold color
            cv2.polylines(frame, [polygon], True, color, 4)
            
            # Add "BEST" text
            center_x = int(sum([p[0] for p in points]) / len(points))
            center_y = int(sum([p[1] for p in points]) / len(points))
            
            cv2.putText(frame, "BEST", (center_x - 20, center_y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
        
    
    def update_parking_status(self, results):
        if self.app:
            with self.app.app_context():
                for i, status in enumerate(results):
                    space = ParkingSpace.query.filter_by(space_id=i).first()
                    if space and space.is_occupied != status:
                        space.is_occupied = status
                        space.last_updated = datetime.utcnow()
                        
                        history = ParkingHistory(space_id=i, occupied=status)
                        db.session.add(history)
                
                db.session.commit()
        else:
            print("No app context available for database update")
    
    def release(self):
        self.cap.release()