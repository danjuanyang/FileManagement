# from datetime import datetime
# import os
# from werkzeug.utils import secure_filename
# from flask import Blueprint, request, jsonify, send_file, abort
# from flask_cors import CORS
#
# from config import app
# from models import db, Project, ProjectFile, ProjectStage
# from auth import get_employee_id
#
# UPLOAD_FOLDER = 'uploads'
# ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
# MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
#
# files_bp = Blueprint('files', __name__)
# CORS(files_bp)
#
#
# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
#
#
# def create_upload_folder():
#     if not os.path.exists(UPLOAD_FOLDER):
#         os.makedirs(UPLOAD_FOLDER)
#
#
# # 获取阶段的文件列表
# @files_bp.route('/files/stage/<int:stage_id>', methods=['GET'])
# def get_stage_files(stage_id):
#     try:
#         files = ProjectFile.query.filter_by(stage_id=stage_id).all()
#         return jsonify([{
#             'id': file.id,
#             'fileName': file.file_name,
#             'fileSize': os.path.getsize(os.path.join(UPLOAD_FOLDER, file.file_name)) if os.path.exists(
#                 os.path.join(UPLOAD_FOLDER, file.file_name)) else 0,
#             'uploadTime': file.upload_date.isoformat(),
#             'uploader': file.upload_user.name,  # 假设User模型有name字段
#             'fileType': file.file_type
#         } for file in files])
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#
# # 文件上传
# @files_bp.route('/files/upload/<int:stage_id>', methods=['POST'])
# def upload_file(stage_id):
#     try:
#         if 'file' not in request.files:
#             return jsonify({'error': '没有文件'}), 400
#
#         file = request.files['file']
#         if file.filename == '':
#             return jsonify({'error': '没有选择文件'}), 400
#
#         if not allowed_file(file.filename):
#             return jsonify({'error': '不支持的文件类型'}), 400
#
#         if file.content_length and file.content_length > MAX_FILE_SIZE:
#             return jsonify({'error': '文件大小超过限制'}), 400
#
#         filename = secure_filename(file.filename)
#         create_upload_folder()
#
#         # 保存文件
#         file_path = os.path.join(UPLOAD_FOLDER, filename)
#         file.save(file_path)
#
#         # 获取项目ID
#         stage = ProjectStage.query.get_or_404(stage_id)
#
#         # 创建文件记录
#         file_record = ProjectFile(
#             project_id=stage.project_id,
#             stage_id=stage_id,
#             file_name=filename,
#             file_type=file.content_type,
#             file_path=file_path,
#             upload_user_id=get_employee_id(),
#             upload_date=datetime.utcnow()
#         )
#
#         db.session.add(file_record)
#         db.session.commit()
#
#         return jsonify({
#             'message': '文件上传成功',
#             'file': {
#                 'id': file_record.id,
#                 'fileName': file_record.file_name,
#                 'fileSize': os.path.getsize(file_path),
#                 'uploadTime': file_record.upload_date.isoformat(),
#                 'uploader': file_record.upload_user.name
#             }
#         })
#
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#
# # 文件下载
# @files_bp.route('/files/download/<int:file_id>', methods=['GET'])
# def download_file(file_id):
#     try:
#         file_record = ProjectFile.query.get_or_404(file_id)
#         file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)
#
#         if not os.path.exists(file_path):
#             return jsonify({'error': '文件不存在'}), 404
#
#         return send_file(
#             file_path,
#             as_attachment=True,
#             download_name=file_record.file_name
#         )
#
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#
# # 文件预览
# @files_bp.route('/files/preview/<int:file_id>', methods=['GET'])
# def preview_file(file_id):
#     try:
#         file_record = ProjectFile.query.get_or_404(file_id)
#         file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)
#
#         if not os.path.exists(file_path):
#             return jsonify({'error': '文件不存在'}), 404
#
#         # 对于PDF文件直接返回
#         if file_record.file_name.lower().endswith('.pdf'):
#             return send_file(
#                 file_path,
#                 mimetype='application/pdf'
#             )
#
#         # 对于其他文件类型，可以实现相应的预览逻辑
#         # 比如使用第三方服务转换文档为PDF或HTML
#
#         return jsonify({'error': '此文件类型暂不支持预览'}), 400
#
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#
# # 删除文件
# @files_bp.route('/files/<int:file_id>', methods=['DELETE'])
# def delete_file(file_id):
#     try:
#         file_record = ProjectFile.query.get_or_404(file_id)
#
#         # 检查权限
#         if file_record.upload_user_id != get_employee_id():
#             return jsonify({'error': '没有权限删除此文件'}), 403
#
#         file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)
#
#         # 删除物理文件
#         if os.path.exists(file_path):
#             os.remove(file_path)
#
#         # 删除数据库记录
#         db.session.delete(file_record)
#         db.session.commit()
#
#         return jsonify({'message': '文件删除成功'})
#
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#


# from datetime import datetime
# import os
# from werkzeug.utils import secure_filename
# from flask import Blueprint, request, jsonify, send_file, abort
# from flask_cors import CORS
#
# from config import app
# from models import db, Project, ProjectFile, ProjectStage
# from auth import get_employee_id
#
# UPLOAD_FOLDER = 'uploads'
# ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
# MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
#
# files_bp = Blueprint('files', __name__)
# CORS(files_bp)
#
#
# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
#
#
# def create_upload_folder():
#     if not os.path.exists(UPLOAD_FOLDER):
#         os.makedirs(UPLOAD_FOLDER)
#
#
# def generate_secure_filename(original_filename):
#     """
#     生成安全的文件名，保留原始文件名的信息
#     """
#     # 获取文件名和扩展名
#     name, ext = os.path.splitext(original_filename)
#
#     # 使用secure_filename处理文件名
#     secure_name = secure_filename(name)
#
#     # 如果secure_filename处理后为空，使用时间戳作为文件名
#     if not secure_name:
#         secure_name = datetime.now().strftime('%Y%m%d_%H%M%S')
#
#     # 生成最终的文件名
#     final_filename = secure_name + ext.lower()
#
#     # 如果文件已存在，添加时间戳
#     if os.path.exists(os.path.join(UPLOAD_FOLDER, final_filename)):
#         final_filename = f"{secure_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext.lower()}"
#
#     return final_filename
#
#
# @files_bp.route('/files/stage/<int:stage_id>', methods=['GET'])
# def get_stage_files(stage_id):
#     try:
#         files = ProjectFile.query.filter_by(stage_id=stage_id).all()
#         return jsonify([{
#             'id': file.id,
#             'fileName': file.file_name,
#             'originalName': file.original_name,  # 添加原始文件名字段
#             'fileSize': os.path.getsize(os.path.join(UPLOAD_FOLDER, file.file_name)) if os.path.exists(
#                 os.path.join(UPLOAD_FOLDER, file.file_name)) else 0,
#             'uploadTime': file.upload_date.isoformat(),
#             'uploader': file.upload_user.name,
#             'fileType': file.file_type
#         } for file in files])
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#
#
# @files_bp.route('/files/upload/<int:stage_id>', methods=['POST'])
# def upload_file(stage_id):
#     try:
#         if 'file' not in request.files:
#             return jsonify({'error': '没有文件'}), 400
#
#         file = request.files['file']
#         if file.filename == '':
#             return jsonify({'error': '没有选择文件'}), 400
#
#         if not allowed_file(file.filename):
#             return jsonify({'error': '不支持的文件类型'}), 400
#
#         # 检查文件大小
#         file.seek(0, os.SEEK_END)
#         file_size = file.tell()
#         file.seek(0)  # 重置文件指针到开始位置
#
#         if file_size > MAX_FILE_SIZE:
#             return jsonify({'error': '文件大小超过限制'}), 400
#
#         # 保存原始文件名
#         original_filename = file.filename
#         # 生成安全的文件名
#         secure_filename = generate_secure_filename(original_filename)
#
#         create_upload_folder()
#
#         # 保存文件
#         file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
#         file.save(file_path)
#
#         # 获取项目ID
#         stage = ProjectStage.query.get_or_404(stage_id)
#
#         # 创建文件记录
#         file_record = ProjectFile(
#             project_id=stage.project_id,
#             stage_id=stage_id,
#             file_name=secure_filename,
#             original_name=original_filename,  # 保存原始文件名
#             file_type=file.content_type,
#             file_path=file_path,
#             upload_user_id=get_employee_id(),
#             upload_date=datetime.utcnow()
#         )
#
#         db.session.add(file_record)
#         db.session.commit()
#
#         return jsonify({
#             'message': '文件上传成功',
#             'file': {
#                 'id': file_record.id,
#                 'fileName': file_record.file_name,
#                 'originalName': file_record.original_name,
#                 'fileSize': os.path.getsize(file_path),
#                 'uploadTime': file_record.upload_date.isoformat(),
#                 'uploader': file_record.upload_user.name
#             }
#         })
#
#     except Exception as e:
#         # 如果出现错误，清理已上传的文件
#         if 'file_path' in locals() and os.path.exists(file_path):
#             try:
#                 os.remove(file_path)
#             except:
#                 pass
#         return jsonify({'error': str(e)}), 500
#
#
# @files_bp.route('/files/download/<int:file_id>', methods=['GET'])
# def download_file(file_id):
#     try:
#         file_record = ProjectFile.query.get_or_404(file_id)
#         file_path = os.path.join(UPLOAD_FOLDER, file_record.file_name)
#
#         if not os.path.exists(file_path):
#             return jsonify({'error': '文件不存在'}), 404
#
#         return send_file(
#             file_path,
#             as_attachment=True,
#             download_name=file_record.original_name  # 使用原始文件名作为下载文件名
#         )
#
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500


from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file, abort
from flask_cors import CORS

from config import app
from models import db, Project, ProjectFile, ProjectStage
from auth import get_employee_id

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
    # 根据您的User模型实际字段修改这里
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