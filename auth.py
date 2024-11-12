# auth.py
import jwt
from functools import wraps
from flask import request, jsonify, redirect, url_for
from config import app

def get_employee_id():
    token = request.headers.get('Authorization').split()[1]
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    return data['user_id']
