import os

class Config:
    SECRET_KEY = '8bd5d300ff4320cc496799952ac9dd6691d5a0d3aec0b291'
    SQLALCHEMY_DATABASE_URI ='sqlite:///parking.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size