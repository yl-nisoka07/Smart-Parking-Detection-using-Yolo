from database import db
from flask_login import UserMixin
from datetime import datetime

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.username}>'

class ParkingSpace(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(db.Integer, nullable=False)  # Matches id in bounding_boxes.json
    is_occupied = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ParkingSpace {self.space_id} - {"Occupied" if self.is_occupied else "Available"}>'

class ParkingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(db.Integer, nullable=False)
    occupied = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ParkingHistory {self.space_id} - {"Occupied" if self.occupied else "Available"} at {self.timestamp}>'