# app.py
import os
import sys
import tempfile
import time

from sqlalchemy import text
# from sqlalchemy import Flask_SQLAlchemy, text
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

app.register_blueprint(files_bp, url_prefix='/api/files')

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
        print("永不宕机！程序开启时间：",time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
        print(f"数据库在: {app.config['SQLALCHEMY_DATABASE_URI']}")
        # print("环境变量:", os.environ)
        print("Python路径:", sys.executable)
        print("临时文件夹:", tempfile.gettempdir())

        # 启用外键约束
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        # 尝试直接创建FTS5表（不加载扩展）
        try:
            create_fts_table_sql = text("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS file_contents_fts 
                        USING fts5(
                            content,
                            tokenize=porter
                        )
                    """)
            db.session.execute(create_fts_table_sql)
            db.session.commit()
            print("成功创建FTS5表")
        except Exception as e:
            # 如果FTS5失败，尝试使用FTS4
            try:
                create_fts4_table_sql = text("""
                            CREATE VIRTUAL TABLE IF NOT EXISTS file_contents_fts 
                            USING fts4(
                                content,
                                tokenize=simple
                            )
                        """)
                db.session.execute(create_fts4_table_sql)
                db.session.commit()
                print("成功创建FTS4表（FTS5不可用，已降级使用FTS4）")
            except Exception as e2:
                print(f"警告: 全文搜索表创建失败 - {str(e2)}")
                print("将使用基础的LIKE查询作为备选方案")

    app.run(host='0.0.0.0', port=6543, debug=False)
