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
from models import db, Project, ProjectFile, ProjectStage, User, StageTask
from auth import get_employee_id

# 获取Python解释器所在目录
python_dir = os.path.dirname(sys.executable)
# 设置上传目录为程序根目录下文件夹
UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')
ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
BASE_UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')  # 基础上传目录

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

# 2024年11月26日15:21:31
def create_upload_path(user_id, project_id, stage_id, task_id=None):
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

        # 如果有任务ID，获取任务名称
        safe_task = ''
        if task_id:
            task = StageTask.query.get_or_404(task_id)
            safe_task = get_safe_path_component(task.name)

        # 构建完整路径
        if task_id:
            relative_path = os.path.join(UPLOAD_FOLDER, safe_user, safe_project, safe_stage, safe_task)
        else:
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


# 获取文件列表
@files_bp.route('/stage/<int:stage_id>/task/<int:task_id>', methods=['GET'])
def get_stage_task_files(stage_id, task_id):
    try:
        files = ProjectFile.query.filter_by(
            stage_id=stage_id,
            task_id=task_id
        ).all()

        files_data = []
        for file in files:
            # 获取上传用户信息
            uploader = User.query.get(file.upload_user_id)
            uploader_name = get_user_display_name(uploader)

            # 获取文件大小
            try:
                file_size = os.path.getsize(os.path.join(current_app.root_path, file.file_path)) if os.path.exists(
                    os.path.join(current_app.root_path, file.file_path)) else 0
            except:
                file_size = 0

            files_data.append({
                'id': file.id,
                'fileName': file.file_name,
                'originalName': file.original_name,
                'fileSize': file_size,
                'fileType': file.file_type,
                'uploadTime': file.upload_date.isoformat(),
                'uploader': uploader_name,
                'stageName': file.stage.name if file.stage else None,
                'taskName': file.task.name if file.task else None
            })

        return jsonify(files_data)

    except Exception as e:
        print(f"获取阶段文件时出错： {str(e)}")
        return jsonify({'error': str(e)}), 500


# 上传文件可用   2024年11月27日
@files_bp.route('/<int:project_id>/stages/<int:stage_id>/tasks/<int:task_id>/upload', methods=['POST'])
def upload_task_file(project_id, stage_id, task_id):
    file = request.files.get('file')
    if not file:
        return jsonify({'error': '请提供文件'}), 400

    # 验证任务、阶段和项目的关系
    task = StageTask.query.get_or_404(task_id)
    stage = ProjectStage.query.get_or_404(stage_id)
    # project = Project.query.get_or_404(project_id)

    if task.stage_id != stage_id or stage.project_id != project_id:
        return jsonify({'error': '任务、阶段或项目信息不匹配'}), 400

    # 验证文件类型和大小
    if not allowed_file(file.filename):
        return jsonify({'error': '文件类型不允许'}), 400
    if file.content_length > MAX_FILE_SIZE:
        return jsonify({'error': '文件大小超过限制'}), 400

    # 构建上传路径
    employee_id = get_employee_id()
    try:
        relative_path, absolute_path = create_upload_path(employee_id, project_id, stage_id, task_id)
    except Exception as e:
        return jsonify({'error': f'创建上传路径失败: {str(e)}'}), 500

    # 保存文件
    try:
        unique_filename = generate_unique_filename(absolute_path, file.filename)
        file_path = os.path.join(absolute_path, unique_filename)
        file.save(file_path)
    except Exception as e:
        return jsonify({'error': f'保存文件失败: {str(e)}'}), 500

    # 创建文件记录
    try:
        project_file = ProjectFile(
            project_id=project_id,
            stage_id=stage_id,
            task_id=task_id,
            original_name=file.filename,
            file_name=unique_filename,
            file_type=file.content_type,
            file_path=os.path.join(relative_path, unique_filename),
            upload_user_id=employee_id,
            upload_date=datetime.now(),
        )
        db.session.add(project_file)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'数据库操作失败: {str(e)}'}), 500

    return jsonify({'message': '文件上传成功', 'file_id': project_file.id})


#  文件删除接口
@files_bp.route('/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        # 获取当前用户ID
        current_user_id = get_employee_id()

        # 获取文件记录
        file = ProjectFile.query.get_or_404(file_id)

        # 验证权限 (只允许文件上传者或管理员删除)
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': '用户未找到'}), 404

        if file.upload_user_id != current_user_id and user.role != 1:  # 1表示管理员角色
            return jsonify({'error': '没有权限删除此文件'}), 403

        # 获取物理文件路径
        file_path = os.path.join(current_app.root_path, file.file_path)

        # 删除物理文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"删除文件时出错： {e}")
                return jsonify({'error': '删除物理文件失败'}), 500

        # 检查并删除空文件夹
        try:
            directory = os.path.dirname(file_path)
            if os.path.exists(directory) and not os.listdir(directory):
                os.rmdir(directory)
        except OSError as e:
            print(f"删除空目录时出错： {e}")
            # 继续执行，因为这不是致命错误
        # 删除数据库记录
        db.session.delete(file)
        db.session.commit()

        return jsonify({
            'message': '文件删除成功',
            'file_id': file_id
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error in delete_file: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 文件下载
@files_bp.route('/download/<int:file_id>', methods=['GET'])
def download_file(file_id):
    try:
        file = ProjectFile.query.get_or_404(file_id)
        file_path = os.path.join(current_app.root_path, file.file_path)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(file_path, as_attachment=True, download_name=file.original_name)

    except Exception as e:
        print(f"下载错误：{str(e)}")
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


# 搜索文件
@files_bp.route('/search', methods=['GET'])
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
                    'tasks_id': file.task_id,
                    'tasks_name': file.task.name if file.task else None,
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
                print(f"处理搜索结果时出错： {str(e)}")
                continue

        return jsonify({
            'results': results,
            'total': len(results)
        })

    except Exception as e:
        print(f"搜索错误： {str(e)}")
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
