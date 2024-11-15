# filemanagement.py
from flask import Blueprint
from flask_cors import CORS
from datetime import datetime
import jwt
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file, abort, current_app
from flask_cors import CORS
from flask import jsonify, request
import os
from models import db, Project, ProjectFile, ProjectStage, User
from auth import get_employee_id

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
BASE_UPLOAD_FOLDER = 'uploads'  # 基础上传目录

files_bp = Blueprint('files', __name__)
CORS(files_bp)



def get_user_display_name(user):
    """获取用户显示名称"""
    if hasattr(user, 'username'):
        return user.username
    elif hasattr(user, 'name'):
        return user.name
    return f"User_{user.id}" if hasattr(user, 'id') else "Unknown User"


def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_path(user_name, project_name, stage_name):
    """生成上传路径"""
    # 移除文件名中的非法字符
    safe_user = secure_filename(user_name)
    safe_project = secure_filename(project_name)
    safe_stage = secure_filename(stage_name)

    # 构建路径
    path = os.path.join(BASE_UPLOAD_FOLDER, safe_user, safe_project, safe_stage)

    # 确保目录存在
    if not os.path.exists(path):
        os.makedirs(path)

    return path


def check_stage_progress(stage_id):
    """检查阶段进度是否达到100%"""
    stage = ProjectStage.query.get(stage_id)
    if not stage:
        return False
    return stage.progress >= 100


# 添加新的路由来处理stage文件获取
@files_bp.route('/files/stage/<int:stage_id>', methods=['GET'])
def get_stage_files(stage_id):
    try:
        files = ProjectFile.query.filter_by(stage_id=stage_id).all()
        files_data = []

        for file in files:
            # 获取上传用户信息
            uploader = User.query.get(file.upload_user_id)
            uploader_name = get_user_display_name(uploader)

            # 获取文件大小
            try:
                file_size = os.path.getsize(file.file_path) if os.path.exists(file.file_path) else 0
            except:
                file_size = 0

            files_data.append({
                'id': file.id,
                'fileName': file.file_name,
                'originalName': file.original_name,
                'fileSize': file_size,
                'uploadTime': file.upload_date.isoformat(),
                'uploader': uploader_name
            })

        return jsonify(files_data)

    except Exception as e:
        print(f"Error getting stage files: {str(e)}")  # 添加日志记录
        return jsonify({'error': str(e)}), 500



@files_bp.route('/files/upload/<int:stage_id>', methods=['POST'])
def upload_file(stage_id):
    try:
        # 检查阶段进度
        if not check_stage_progress(stage_id):
            return jsonify({'error': '当前阶段未完成，无法上传文件'}), 403

        if 'file' not in request.files:
            return jsonify({'error': '没有文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型'}), 400

        # 检查文件大小
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': '文件大小超过限制'}), 400

        # 获取必要信息
        stage = ProjectStage.query.get_or_404(stage_id)
        project = Project.query.get_or_404(stage.project_id)
        user = User.query.get_or_404(get_employee_id())

        # 生成上传路径
        upload_path = get_upload_path(user.username, project.name, stage.name)

        # 保持原始文件名，但处理同名文件
        original_filename = file.filename
        final_filename = original_filename
        base_name, extension = os.path.splitext(original_filename)
        counter = 1

        while os.path.exists(os.path.join(upload_path, final_filename)):
            final_filename = f"{base_name}({counter}){extension}"
            counter += 1

        # 保存文件
        file_path = os.path.join(upload_path, final_filename)
        file.save(file_path)

        # 创建文件记录
        file_record = ProjectFile(
            project_id=project.id,
            stage_id=stage_id,
            file_name=final_filename,
            original_name=original_filename,
            file_type=file.content_type,
            file_path=file_path,
            upload_user_id=user.id,
            upload_date=datetime.now()
        )

        db.session.add(file_record)
        db.session.commit()

        return jsonify({
            'message': '文件上传成功',
            'file': {
                'id': file_record.id,
                'fileName': file_record.file_name,
                'originalName': file_record.original_name,
                'fileSize': file_size,
                'uploadTime': file_record.upload_date.isoformat(),
                'uploader': get_user_display_name(file_record.upload_user)
            }
        })

    except Exception as e:
        # 清理已上传的文件
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        return jsonify({'error': str(e)}), 500


@files_bp.route('/files/download/<int:file_id>', methods=['GET'])
def download_file(file_id):
    try:
        file_record = ProjectFile.query.get_or_404(file_id)
        if not os.path.exists(file_record.file_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(
            file_record.file_path,
            as_attachment=True,
            download_name=file_record.original_name
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@files_bp.route('/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        file_record = ProjectFile.query.get_or_404(file_id)

        # 检查权限
        if file_record.upload_user_id != get_employee_id():
            return jsonify({'error': '没有权限删除此文件'}), 403

        # 删除物理文件
        if os.path.exists(file_record.file_path):
            os.remove(file_record.file_path)

            # 检查并删除空文件夹
            directory = os.path.dirname(file_record.file_path)
            while directory != BASE_UPLOAD_FOLDER:
                if not os.listdir(directory):
                    os.rmdir(directory)
                    directory = os.path.dirname(directory)
                else:
                    break

        # 删除数据库记录
        db.session.delete(file_record)
        db.session.commit()

        return jsonify({'message': '文件删除成功'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_user_info_from_token():
    """
    从授权令牌中获取用户信息，并进行改进的错误处理
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            print("No Authorization header")
            return None

        token = auth_header.replace('Bearer ', '').strip()
        if not token:
            print("Empty token")
            return None

        payload = jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        return payload

    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token error: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected error in token processing: {str(e)}")
        return None



@files_bp.route('/files/search', methods=['GET'])
def search_files():
    try:
        # 获取搜索查询参数
        search_query = request.args.get('query', '').strip()
        if not search_query:
            return jsonify({'error': 'Search query is required'}), 400

        # 验证用户身份
        user_info = get_user_info_from_token()
        if not user_info:
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = user_info.get('user_id')
        user_role = user_info.get('role')

        # 构建基础查询
        base_query = ProjectFile.query.options(
            joinedload(ProjectFile.project),
            joinedload(ProjectFile.upload_user)
        )

        # 非管理员只能看到自己的文件
        if user_role != 1:  # 非管理员角色
            base_query = base_query.filter(ProjectFile.upload_user_id == user_id)

        # 构建搜索条件
        search_conditions = or_(
            ProjectFile.original_name.ilike(f'%{search_query}%'),
            ProjectFile.file_type.ilike(f'%{search_query}%'),
            Project.name.ilike(f'%{search_query}%'),
            User.username.ilike(f'%{search_query}%')
        )

        # 执行查询
        search_results = base_query \
            .join(Project) \
            .join(User, ProjectFile.upload_user_id == User.id) \
            .filter(search_conditions) \
            .all()

        # 处理查询结果
        results = []
        for file in search_results:
            file_path = os.path.join(UPLOAD_FOLDER, file.file_name)
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

            results.append({
                'id': file.id,
                'fileName': file.file_name,
                'originalName': file.original_name,
                'fileType': file.file_type,
                'fileSize': file_size,
                'uploadTime': file.upload_date.isoformat(),
                'uploader': file.upload_user.username,
                'projectName': file.project.name if file.project else None
            })

        return jsonify({
            'results': results,
            'total': len(results)
        })

    except Exception as e:
        print(f"Search error: {str(e)}")  # 调试日志
        return jsonify({'error': str(e)}), 500