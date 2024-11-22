# filemanagement.py
import re
import sys

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

# 获取Python解释器所在目录
python_dir = os.path.dirname(sys.executable)
# 设置上传目录为程序根目录下文件夹
UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')
ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
BASE_UPLOAD_FOLDER = os.path.join(python_dir, 'uploads') # 基础上传目录

files_bp = Blueprint('files', __name__)
CORS(files_bp)


def sanitize_filename(filename):
    """
    安全地处理文件名，保留中文字符
    移除或替换不安全的字符，但保留中文和基本标点
    """
    # 替换Windows文件系统中的非法字符
    illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
    # 将非法字符替换为下划线
    safe_name = re.sub(illegal_chars, '_', filename)
    # 去除首尾空格和点
    safe_name = safe_name.strip('. ')
    # 如果文件名为空，返回默认名称
    return safe_name or 'unnamed'


def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_safe_path_component(component):
    """
    安全地处理路径组件名称，保留中文字符
    """
    if not component:
        return 'unnamed'
    # 使用改进的文件名清理函数
    return sanitize_filename(component)


def get_user_display_name(user):
    """获取用户显示名称"""
    if hasattr(user, 'username'):
        return user.username
    elif hasattr(user, 'name'):
        return user.name
    return f"User_{user.id}" if hasattr(user, 'id') else "Unknown User"


def create_upload_path(user_id, project_id, stage_id):
    """创建并返回上传路径"""
    try:
        # 获取必要信息
        user = User.query.get_or_404(user_id)
        project = Project.query.get_or_404(project_id)
        stage = ProjectStage.query.get_or_404(stage_id)

        # 安全地处理各个路径组件，保留中文
        safe_user = get_safe_path_component(user.username)
        safe_project = get_safe_path_component(project.name)
        safe_stage = get_safe_path_component(stage.name)

        # 构建完整路径
        relative_path = os.path.join(UPLOAD_FOLDER, safe_user, safe_project, safe_stage)
        absolute_path = os.path.join(current_app.root_path, relative_path)

        # 确保目录存在
        os.makedirs(absolute_path, exist_ok=True)

        return relative_path, absolute_path
    except Exception as e:
        raise Exception(f"创建上传路径失败: {str(e)}")


def generate_unique_filename(directory, original_filename):
    """生成唯一的文件名，处理文件名冲突"""
    base_name, extension = os.path.splitext(original_filename)
    safe_base_name = get_safe_path_component(base_name)
    counter = 1
    new_filename = f"{safe_base_name}{extension}"

    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{safe_base_name}({counter}){extension}"
        counter += 1

    return new_filename


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

        # 获取当前用户和阶段信息
        user_id = get_employee_id()
        stage = ProjectStage.query.get_or_404(stage_id)
        project_id = stage.project_id

        # 创建上传路径
        relative_path, absolute_path = create_upload_path(user_id, project_id, stage_id)

        # 生成唯一文件名
        unique_filename = generate_unique_filename(absolute_path, file.filename)
        file_path = os.path.join(absolute_path, unique_filename)
        relative_file_path = os.path.join(relative_path, unique_filename)

        # 保存文件
        file.save(file_path)

        # 创建数据库记录
        file_record = ProjectFile(
            project_id=project_id,
            stage_id=stage_id,
            file_name=unique_filename,
            original_name=file.filename,
            file_type=file.content_type,
            file_path=relative_file_path,
            upload_user_id=user_id,
            upload_date=datetime.now()
        )

        db.session.add(file_record)
        db.session.commit()

        return jsonify({
            'message': '文件上传成功',
            'file': {
                'id': file_record.id,
                'fileName': unique_filename,
                'originalName': file.filename,
                'fileSize': file_size,
                'uploadTime': file_record.upload_date.isoformat(),
                'uploader': file_record.upload_user.username
            }
        })

    except Exception as e:
        # 发生错误时清理已上传的文件
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
        file_path = os.path.join(current_app.root_path, file_record.file_path)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_record.original_name
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@files_bp.route('/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        file_record = ProjectFile.query.get_or_404(file_id)

        # 权限检查
        if file_record.upload_user_id != get_employee_id():
            return jsonify({'error': '没有权限删除此文件'}), 403

        file_path = os.path.join(current_app.root_path, file_record.file_path)

        # 删除物理文件
        if os.path.exists(file_path):
            os.remove(file_path)

            # 递归删除空目录
            current_dir = os.path.dirname(file_path)
            while current_dir != os.path.join(current_app.root_path, UPLOAD_FOLDER):
                if len(os.listdir(current_dir)) == 0:
                    os.rmdir(current_dir)
                    current_dir = os.path.dirname(current_dir)
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
            print("无 Authorization 标头")
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
        print("令牌已过期")
        return None
    except jwt.InvalidTokenError as e:
        print(f"无效令牌错误： {str(e)}")
        return None
    except Exception as e:
        print(f"令牌处理中出现意外错误: {str(e)}")
        return None


@files_bp.route('/files/search', methods=['GET'])
def search_files():
    try:
        search_query = request.args.get('query', '').strip()
        search_type = request.args.get('type', 'all')  # 可选值: all, filename, content

        if not search_query:
            return jsonify({'error': 'Search query is required'}), 400

        # 验证用户身份
        user_info = get_user_info_from_token()
        if not user_info:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # 构建基础查询
        base_query = ProjectFile.query.options(
            joinedload(ProjectFile.project),
            joinedload(ProjectFile.upload_user)
        )

        # 根据用户角色限制查询范围
        if user_info.get('role') != 1:  # 非管理员
            base_query = base_query.filter(ProjectFile.upload_user_id == user_info.get('user_id'))

        # 构建搜索条件
        search_conditions = []
        if search_type in ['all', 'filename']:
            search_conditions.extend([
                ProjectFile.original_name.ilike(f'%{search_query}%'),
                Project.name.ilike(f'%{search_query}%'),
                User.username.ilike(f'%{search_query}%')
            ])

        if search_type in ['all', 'content']:
            search_conditions.append(ProjectFile.content_text.ilike(f'%{search_query}%'))

        # 执行查询
        search_results = base_query \
            .join(Project) \
            .join(User, ProjectFile.upload_user_id == User.id) \
            .filter(or_(*search_conditions)) \
            .all()

        # 处理结果
        results = []
        for file in search_results:
            try:
                file_path = os.path.join(current_app.root_path, file.file_path)
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

                # 获取内容匹配的上下文
                content_preview = None
                if file.content_text and search_type in ['all', 'content']:
                    content_preview = get_content_preview(file.content_text, search_query)

                results.append({
                    'id': file.id,
                    'fileName': file.file_name,
                    'stageName': file.stage.name if file.stage else None,
                    'originalName': file.original_name,
                    'fileType': file.file_type,
                    'fileSize': file_size,
                    'uploadTime': file.upload_date.isoformat(),
                    'uploader': file.upload_user.username,
                    'projectName': file.project.name if file.project else None,
                    'contentPreview': content_preview
                })
            except Exception as e:
                print(f"Error processing search result: {str(e)}")
                continue

        return jsonify({
            'results': results,
            'total': len(results)
        })

    except Exception as e:
        print(f"Search error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_content_preview(content, query, context_length=100):
    """获取匹配内容的上下文预览"""
    if not content:
        return None

    try:
        index = content.lower().find(query.lower())
        if index == -1:
            return None

        start = max(0, index - context_length // 2)
        end = min(len(content), index + len(query) + context_length // 2)

        preview = content[start:end]
        if start > 0:
            preview = f"...{preview}"
        if end < len(content):
            preview = f"{preview}..."

        return preview
    except:
        return None
