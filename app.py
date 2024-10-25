# # app.py
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from models import db, User
# import jwt
# import datetime
#
# app = Flask(__name__)
# CORS(app)
#
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SECRET_KEY'] = '9888898888'
#
# db.init_app(app)
# from routes.leaders import leader_bp
# from routes.employees import employee_bp
#
# app.register_blueprint(leader_bp, url_prefix='/api/leader')
# app.register_blueprint(employee_bp, url_prefix='/api/employee')
#
#
# @app.route('/api/login', methods=['POST'])
# def login():
#     data = request.get_json()
#     username = data.get('username')
#     password = data.get('password')
#
#     user = User.query.filter_by(username=username).first()
#
#     if user and user.check_password(password):
#         token = jwt.encode({
#             'user_id': user.id,
#             'username': user.username,
#             'role': user.role,
#             'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
#         }, app.config['SECRET_KEY'], algorithm='HS256')
#
#         return jsonify({
#             'token': token,
#             'role': user.role,
#             'username': user.username,
#             'user_id': user.id  # 在响应中包含 user_id
#         }), 200
#
#     return jsonify({'message': '用户名或密码无效'}), 401
#
#
# # 注册
# @app.route('/api/register', methods=['POST'])
# def register():
#     data = request.get_json()
#     username = data.get('username')
#     password = data.get('password')
#     role = data.get('role', 2)  # 默认角色为 2 （员工）
#
#     if User.query.filter_by(username=username).first():
#         return jsonify({'message': '用户名已存在'}), 400
#
#     new_user = User(username=username, role=role)
#     new_user.set_password(password)
#
#     db.session.add(new_user)
#     db.session.commit()
#
#     return jsonify({'message': '用户注册成功'}), 201
#
#
# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all()
#     app.run(debug=True, port=7777)


# app.py
from config import app, db
from flask import request, jsonify
import jwt
import datetime
from models import User
from routes.leaders import leader_bp
from routes.employees import employee_bp

app.register_blueprint(leader_bp, url_prefix='/api/leader')
app.register_blueprint(employee_bp, url_prefix='/api/employee')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        token = jwt.encode({
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'token': token,
            'role': user.role,
            'username': user.username,
            'user_id': user.id
        }), 200

    return jsonify({'message': '用户名或密码无效'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 2)

    if User.query.filter_by(username=username).first():
        return jsonify({'message': '用户名已存在'}), 400

    new_user = User(username=username, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '用户注册成功'}), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=7777)