# app.py
import os
import sys
import tempfile
import time
import zipfile

from sqlalchemy import text
from config import app, db, clean_old_backups, start_backup_scheduler
from flask import request, jsonify
import jwt
import datetime
from models import User, UserSession, UserActivityLog
from routes.AI_assistant import ai_bp
from routes.admin import admin_bp
from routes.announcements import announcement_bp
from routes.filemanagement import files_bp
from routes.leaders import leader_bp
from routes.employees import employee_bp
from routes.projectplan import projectplan_bp
from routes.training import training_bp
from utils.activity_tracking import create_user_session, log_user_activity, track_activity
from utils.network_utils import get_real_ip
from routes.file_merge_router import merge_bp  # 导入文件合并蓝图

app.register_blueprint(leader_bp, url_prefix='/api/leader')
app.register_blueprint(employee_bp, url_prefix='/api/employee')

app.register_blueprint(projectplan_bp, url_prefix='/api/projectplan')

app.register_blueprint(files_bp, url_prefix='/api/files')
app.register_blueprint(merge_bp, url_prefix='/api/files')
app.register_blueprint(announcement_bp, url_prefix='/api/announcements')

app.register_blueprint(admin_bp, url_prefix='/api/admin')

app.register_blueprint(training_bp, url_prefix='/api/training')

app.register_blueprint(ai_bp, url_prefix='/api/ai')  # 注册AI蓝图


# 用户登录接口
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        # 创建会话并记录活动
        session_id = create_user_session(user.id)
        log_user_activity(
            user_id=user.id,
            action_type='login',
            # action_detail=f'用户登录，IP: {request.remote_addr}'
            action_detail=f'用户登录，IP: {get_real_ip()}'  # 修改这里
        )

        # 创建JWT令牌，1小时有效期
        token = jwt.encode({
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'exp': datetime.datetime.now() + datetime.timedelta(minutes=60)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'token': token,
            'role': user.role,
            'username': user.username,
            'user_id': user.id,
            'session_id': session_id,
            'login_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    return jsonify({'message': '用户名或密码无效'}), 401


# 用户注册接口
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 3)  # 默认为普通用户

    if User.query.filter_by(username=username).first():
        return jsonify({'message': '用户名已存在'}), 400

    new_user = User(username=username, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '用户注册成功'}), 201


# 用户注销接口
@app.route('/api/logout', methods=['POST'])
@track_activity
def logout():
    try:
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = data['user_id']

        # 关闭活动会话
        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if active_session:
            active_session.end_session()

        # 记录登出活动
        log_user_activity(
            user_id=user_id,
            action_type='logout',
            action_detail='用户正常登出'
        )

        db.session.commit()
        return jsonify({'message': '成功登出'}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 401


# 手动备份
@app.route('/api/backup', methods=['POST'])
@track_activity
def backup_api():
    success, message = run_backup_once()
    if success:
        return jsonify({"message": message}), 200
    else:
        return jsonify({"message": message}), 500


def run_backup_once():
    source_dirs = {
        'FileManagementFolder': '/volume1/web/FileManagementFolder',  # 后端数据和文件
        'FileManagement': '/volume1/web/FileManagement',  # 后端源码
        'Dist': '/volume1/docker/nginx',  # 前端打包的文件
    }
    backup_dir = '/volume1/web/backup'
    max_backups = 5  # 最多保留5份

    try:
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = time.strftime("%Y%m%d_%H%M%S")

        for name, path in source_dirs.items():
            zip_filename = os.path.join(backup_dir, f"{name}_backup_{timestamp}.zip")
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        relative_path = os.path.relpath(abs_path, path)
                        zipf.write(abs_path, arcname=relative_path)

            print(f"{path} 已备份到 {zip_filename}")

            # 清理多余备份
            clean_old_backups(backup_dir, name, max_backups)

        return True, "备份成功"
    except Exception as e:
        print(f"备份过程中出错: {e}")
        return False, f"备份失败: {e}"


# 注册
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 3)  # 默认为普通用户

    if User.query.filter_by(username=username).first():
        return jsonify({'message': '用户名已存在'}), 400

    new_user = User(username=username, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '用户注册成功'}), 201


if __name__ == '__main__':
    # 启动定时任务
    start_backup_scheduler()
    with app.app_context():
        db.create_all()

        # 确保外键约束开启
        db.session.execute(text('PRAGMA foreign_keys=ON'))

        print("创建用户会话和活动日志表...")
        try:
            UserSession.__table__.create(db.engine)
            print("成功创建用户会话表")
        except Exception as e:
            print(f"用户会话表已存在或创建失败: {str(e)}")

        try:
            UserActivityLog.__table__.create(db.engine)
            print("成功创建用户活动日志表")
        except Exception as e:
            print(f"用户活动日志表已存在或创建失败: {str(e)}")

        print("永不宕机！程序开启时间：", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
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
