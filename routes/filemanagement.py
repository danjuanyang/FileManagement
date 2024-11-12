from datetime import datetime
from functools import wraps
# from operator import or_

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
from routes.employees import token_required, get_profile

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

files_bp = Blueprint('files', __name__)
CORS(files_bp)


def get_user_display_name(user):
    """
    获取用户显示名称
    根据实际的User模型字段返回合适的显示名称
    """
    # 根据User模型实际字段修改这里
    # 按优先级尝试不同的字段
    if hasattr(user, 'username'):
        return user.username
    elif hasattr(user, 'name'):
        return user.name
    elif hasattr(user, 'employee_name'):
        return user.employee_name
    elif hasattr(user, 'email'):
        return user.email
    else:
        return f"User_{user.id}" if hasattr(user, 'id') else "Unknown User"


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def create_upload_folder():
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)


def generate_secure_filename(original_filename):
    """
    生成安全的文件名，保留原始文件名的信息
    """
    # 获取文件名和扩展名
    name, ext = os.path.splitext(original_filename)

    # 使用secure_filename处理文件名
    secure_name = secure_filename(name)

    # 如果secure_filename处理后为空，使用时间戳作为文件名
    if not secure_name:
        secure_name = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 生成最终的文件名
    final_filename = secure_name + ext.lower()

    # 如果文件已存在，添加时间戳
    if os.path.exists(os.path.join(UPLOAD_FOLDER, final_filename)):
        final_filename = f"{secure_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext.lower()}"

    return final_filename


@files_bp.route('/files/stage/<int:stage_id>', methods=['GET'])
def get_stage_files(stage_id):
    try:
        files = ProjectFile.query.filter_by(stage_id=stage_id).all()
        return jsonify([{
            'id': file.id,
            'fileName': file.file_name,
            'originalName': file.original_name,  # 添加原始文件名字段
            'fileSize': os.path.getsize(os.path.join(UPLOAD_FOLDER, file.file_name)) if os.path.exists(
                os.path.join(UPLOAD_FOLDER, file.file_name)) else 0,
            'uploadTime': file.upload_date.isoformat(),
            'uploader': get_user_display_name(file.upload_user),
            'fileType': file.file_type,
            'projectName': file.project.name
        } for file in files])
    except Exception as e:
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
        file.seek(0)  # 重置文件指针到开始位置

        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': '文件大小超过限制'}), 400

        # 保存原始文件名
        original_filename = file.filename
        # 生成安全的文件名
        secure_filename = generate_secure_filename(original_filename)

        create_upload_folder()

        # 保存文件
        file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
        file.save(file_path)

        # 获取项目ID和用户
        stage = ProjectStage.query.get_or_404(stage_id)
        user_id = get_employee_id()

        # 创建文件记录
        file_record = ProjectFile(
            project_id=stage.project_id,
            stage_id=stage_id,
            file_name=secure_filename,  # 保存安全文件名
            original_name=original_filename,  # 保存原始文件名
            file_type=file.content_type,
            file_path=file_path,
            upload_user_id=user_id,
            upload_date=datetime.utcnow()
        )

        db.session.add(file_record)
        db.session.commit()

        return jsonify({
            'message': '文件上传成功',
            'file': {
                'id': file_record.id,
                'fileName': file_record.file_name,
                'originalName': file_record.original_name,
                'fileSize': os.path.getsize(file_path),
                'uploadTime': file_record.upload_date.isoformat(),
                'uploader': get_user_display_name(file_record.upload_user)
            }
        })

    except Exception as e:
        # 如果出现错误，清理已上传的文件
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
        file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_record.original_name  # 使用原始文件名作为下载文件名
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

        file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)

        # 删除物理文件
        if os.path.exists(file_path):
            os.remove(file_path)

        # 删除数据库记录
        db.session.delete(file_record)
        db.session.commit()

        return jsonify({'message': '文件删除成功'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500






#
# # 搜索
#
# def get_user_info_from_token():
#     """
#     Get user information from the authorization token with improved error handling
#     """
#     try:
#         auth_header = request.headers.get('Authorization', '')
#         # print(f"Received Authorization header: {auth_header}")  # 调试日志
#
#         if not auth_header:
#             print("No Authorization header")
#             return None
#
#         # 处理可能的不同token格式
#         if 'Bearer' in auth_header:
#             token = auth_header.split('Bearer')[-1].strip()
#         else:
#             token = auth_header.strip()
#
#         # print(f"Extracted token: {token[:30]}...")  # 打印token前30个字符
#
#         if not token:
#             print("Empty token")
#             return None
#
#         # 解码token
#         payload = jwt.decode(
#             token,
#             current_app.config['SECRET_KEY'],
#             algorithms=['HS256']
#         )
#
#         # print(f"Successfully decoded payload: {payload}")  # 调试日志
#         return payload
#
#     except jwt.ExpiredSignatureError:
#         print("Token has expired")
#         return None
#     except jwt.InvalidTokenError as e:
#         print(f"Invalid token error: {str(e)}")
#         return None
#     except Exception as e:
#         print(f"Unexpected error in token processing: {str(e)}")
#         return None
#
#
# @files_bp.route('/files/search', methods=['GET'])
# def search_files():
#     try:
#         search_query = request.args.get('query', '').strip()
#         if not search_query:
#             return jsonify({'error': 'Search query is required'}), 400
#
#         # 获取并验证用户信息
#         user_info = get_user_info_from_token()
#         print(f"User info from token: {user_info}")  # 调试日志
#
#         if not user_info:
#             return jsonify({'error': 'Invalid or expired token'}), 401
#
#         user_id = user_info.get('user_id')
#         user_role = user_info.get('role')
#
#         # print(f"Processed user_id: {user_id}, role: {user_role}")  # 调试日志
#
#         # 构建查询
#         base_query = ProjectFile.query
#
#         # 基于角色过滤
#         if user_role != 1:  # 非管理员角色
#             base_query = base_query.filter(ProjectFile.upload_user_id == user_id)
#
#         # 修复 or_ 查询
#         search_results = base_query.join(Project).join(
#             User, ProjectFile.upload_user_id == User.id
#         ).filter(
#             or_(
#                 ProjectFile.original_name.ilike(f'%{search_query}%'),
#                 ProjectFile.file_type.ilike(f'%{search_query}%'),
#                 Project.name.ilike(f'%{search_query}%'),
#                 User.username.ilike(f'%{search_query}%')
#             )
#         ).all()
#
#         # print(f"Found {len(search_results)} results")  # 调试日志
#
#         # 格式化结果
#         results = [{
#             'id': file.id,
#             'fileName': file.file_name,
#             'originalName': file.original_name,
#             'fileType': file.file_type,
#             'fileSize': os.path.getsize(os.path.join(UPLOAD_FOLDER, file.file_name))
#             if os.path.exists(os.path.join(UPLOAD_FOLDER, file.file_name)) else 0,
#             'uploadTime': file.upload_date.isoformat(),
#             'uploader': get_user_display_name(file.upload_user),
#             'projectName': file.project.name if file.project else None
#         } for file in search_results]
#
#         return jsonify({
#             'results': results,
#             'total': len(results)
#         })
#
#     except Exception as e:
#         # print(f"Search error: {str(e)}")  # 调试日志
#         return jsonify({'error': str(e)}), 500
#


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