from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from flask_login import login_required, current_user, LoginManager
from config import Config
from database import db
from models import User, ParkingSpace, ParkingHistory
from yolo_parking_detector import YOLOParkingDetector
from auth import auth
import cv2
import threading
import time

# Initialize parking detector (will be initialized in main)
parking_detector = None
latest_frame = None
frame_lock = threading.Lock()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth)
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    # Main routes
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        
        # Get parking status for user view
        parking_spaces = ParkingSpace.query.all()
        return render_template('dashboard.html', parking_spaces=parking_spaces)
    
    @app.route('/admin')
    @login_required
    def admin_dashboard():
        if not current_user.is_admin:
            return redirect(url_for('dashboard'))
        
        # Get all users for admin management
        users = User.query.all()
        parking_spaces = ParkingSpace.query.all()
        parking_history = ParkingHistory.query.order_by(ParkingHistory.timestamp.desc()).limit(50).all()
        
        return render_template('admin.html', 
                              users=users, 
                              parking_spaces=parking_spaces,
                              parking_history=parking_history)
    
    @app.route('/parking_status')
    @login_required
    def parking_status():
        parking_spaces = ParkingSpace.query.all()
        return render_template('parking_status.html', parking_spaces=parking_spaces)
    
    @app.route('/video_feed')
    @login_required
    def video_feed():
        def generate():
            global latest_frame
            while True:
                with frame_lock:
                    if latest_frame is not None:
                        # Encode frame as JPEG
                        ret, jpeg = cv2.imencode('.jpg', latest_frame)
                        if ret:
                            frame_data = jpeg.tobytes()
                            
                            # Yield frame in multipart format
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n\r\n')
                time.sleep(0.033)  # ~30 FPS
        
        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    
    @app.route('/api/parking_status')
    def api_parking_status():
        parking_spaces = ParkingSpace.query.all()
        return jsonify([{
            'id': space.space_id,
            'occupied': space.is_occupied,
            'last_updated': space.last_updated.isoformat() if space.last_updated else None
        } for space in parking_spaces])
    
    @app.route('/api/process_frame')
    @login_required
    def api_process_frame():
        if not current_user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if parking_detector:
            frame, results = parking_detector.process_frame()
            if frame is not None:
                # Save processed frame
                cv2.imwrite('static/latest_frame.jpg', frame)
                return jsonify({'success': True, 'message': 'Frame processed'})
        
        return jsonify({'success': False, 'message': 'No frame processed'})
    
    @app.route('/api/parking_recommendations')
    @login_required
    def api_parking_recommendations():
        """Get best parking spot recommendations"""
        parking_spaces = ParkingSpace.query.all()
        available_spaces = [space for space in parking_spaces if not space.is_occupied]
        
        if not available_spaces:
            return jsonify({
                'available': False,
                'message': 'No parking spaces available'
            })
        
        # Simple recommendation: first 3 available spaces
        best_spots = [space.space_id for space in available_spaces[:3]]
        
        return jsonify({
            'available': True,
            'total_available': len(available_spaces),
            'best_spots': best_spots,
            'message': f'Recommended spots: {", ".join(map(str, best_spots))}'
        })

    @app.route('/api/available_spaces')
    @login_required
    def api_available_spaces():
        """Get all available spaces"""
        parking_spaces = ParkingSpace.query.all()
        available_spaces = [space for space in parking_spaces if not space.is_occupied]
        
        return jsonify({
            'available_spaces': [{
                'space_id': space.space_id,
                'last_updated': space.last_updated.isoformat() if space.last_updated else None
            } for space in available_spaces]
        })
    
    return app

def video_processing_thread():
    """Thread for continuous video processing"""
    global latest_frame, parking_detector
    while True:
        try:
            if parking_detector:
                frame, results = parking_detector.process_frame()
                if frame is not None:
                    with frame_lock:
                        latest_frame = frame
            time.sleep(0.033)  # ~30 FPS
        except Exception as e:
            print(f"Error in video processing thread: {e}")
            time.sleep(1)


if __name__ == '__main__':
    app = create_app()
    
    # Initialize parking detector with app context
    try:
            parking_detector = YOLOParkingDetector(
                video_path="carPark.mp4",
                json_path="bounding_boxes.json",
                model_path="yolov11n_- visdrone.pt",  # Path to your YOLO model
                app=app  # Pass the app for context
            )
            print("YOLO Parking detector initialized successfully")
            
            # Start video processing thread
            video_thread = threading.Thread(target=video_processing_thread, daemon=True)
            video_thread.start()
            print("Video processing thread started")
            
    except Exception as e:
            print(f"Error initializing YOLO parking detector: {e}")
            parking_detector = None
        
    app.run(debug=True, threaded=True)