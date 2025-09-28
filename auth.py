from flask import Blueprint, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from database import db
from models import User

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password, password):
            flash('Please check your login details and try again.')
            return redirect(url_for('auth.login'))
            
        login_user(user, remember=remember)
        return redirect(url_for('dashboard'))  
    
    return render_template('login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            flash('Email address already exists')
            return redirect(url_for('auth.register'))
            
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            is_admin=False
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))