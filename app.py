# app.py
from config import app, db
from flask import request, jsonify, redirect, url_for
import jwt
import datetime
from models import User, Project
from routes.filemanagement import files_bp
from routes.leaders import leader_bp
from routes.employees import employee_bp
from routes.projectplan import projectplan_bp

app.register_blueprint(leader_bp, url_prefix='/api/leader')
app.register_blueprint(employee_bp, url_prefix='/api/employee')

app.register_blueprint(projectplan_bp, url_prefix='/api/projectplan')

app.register_blueprint(files_bp, url_prefix='/api')


# 用户登录接口
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
            'exp': datetime.datetime.now() + datetime.timedelta(minutes=1)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'token': token,
            'role': user.role,
            'username': user.username,
            'user_id': user.id,
            # 当前时间,返回时分秒
            'now': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            # 过期时间
            'exp': datetime.datetime.now() + datetime.timedelta(minutes=1)

        }), 200
    return jsonify({'message': '用户名或密码无效'}), 401


# 用户注册接口
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
