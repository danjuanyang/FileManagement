import base64
import io
import re
import subprocess
import tempfile
import urllib
import os
import base64
import uuid

from pdf2image import convert_from_path
from PIL import Image
import io
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from datetime import datetime
import os

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename
from models import db, Training, Comment, Reply, User
from routes.employees import token_required
from routes.filemanagement import python_dir
from utils.activity_tracking import track_activity
import urllib.parse

# 创建蓝图
training_bp = Blueprint('training', __name__)

# 文件上传配置
ALLOWED_EXTENSIONS = {'ppt', 'pptx'}
UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')  # 基础上传目录


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def get_safe_path_component(component):
    """
    安全地处理路径组件名称，保留中文字符
    """
    if not component:
        return 'unnamed'
    return sanitize_filename(component)

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
def ensure_upload_folder():
    """确保上传目录存在"""
    folder_path = os.path.join(current_app.static_folder, UPLOAD_FOLDER)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


# 分配培训任务
@training_bp.route('/assign', methods=['POST'])
@token_required
@track_activity
def assign_training(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'code': 400,
                'message': '无效的请求数据'
            }), 400

        # 获取并验证必要字段
        trainer_id = data.get('trainer_id')
        training_month = data.get('training_month')
        title = data.get('title')
        description = data.get('description')

        # 检查必要字段
        if not all([trainer_id, training_month, title]):
            return jsonify({
                'code': 400,
                'message': '缺少必要字段'
            }), 400

        # 确保trainer_id是整数类型
        try:
            trainer_id = int(trainer_id)
        except (TypeError, ValueError):
            return jsonify({
                'code': 400,
                'message': '无效的培训人ID'
            }), 400

        # 验证培训人是否存在
        trainer = User.query.get(trainer_id)
        if not trainer:
            return jsonify({
                'code': 404,
                'message': '培训人不存在'
            }), 404

        # 验证月份格式 (YYYY-MM)
        try:
            datetime.strptime(training_month, '%Y-%m')
        except ValueError:
            return jsonify({
                'code': 400,
                'message': '无效的月份格式，应为YYYY-MM'
            }), 400

        # 检查是否已存在该月份的培训任务
        existing_training = Training.query.filter_by(
            trainer_id=trainer_id,
            training_month=training_month
        ).first()

        if existing_training:
            return jsonify({
                'code': 400,
                'message': '该员工在此月份已有培训任务'
            }), 400

        # 创建新的培训任务
        new_training = Training(
            trainer_id=trainer_id,  # 确保这里使用正确的trainer_id
            training_month=training_month,
            title=title,
            description=description,
            status='pending',  # 初始状态为待上传
            create_time=datetime.now()
        )

        db.session.add(new_training)
        db.session.commit()

        # 返回成功响应
        return jsonify({
            'code': 200,
            'message': '培训任务分配成功',
            'data': {
                'id': new_training.id,
                'trainer_id': new_training.trainer_id,
                'trainer_name': trainer.username,  # 添加培训人姓名
                'training_month': new_training.training_month,
                'title': new_training.title,
                'status': new_training.status
            },
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error in assign_training: {str(e)}")  # 添加错误日志
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500


# 上传培训材料
@training_bp.route('/upload/<int:training_id>', methods=['POST'])
@token_required
@track_activity
def upload_training_material(current_user, training_id):
    try:
        # 获取培训记录
        training = Training.query.get_or_404(training_id)

        # 验证当前用户是否为指定培训者
        if current_user.id != training.trainer_id:
            return jsonify({
                'code': 403,
                'message': '您不是该培训的指定培训者'
            }), 403

        # 验证培训状态是否为待上传
        if training.status != 'pending':
            return jsonify({
                'code': 400,
                'message': '该培训材料已上传完成，无法重复上传'
            }), 400

        # 检查是否有文件被上传
        if 'file' not in request.files:
            return jsonify({
                'code': 400,
                'message': '未找到上传文件'
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'code': 400,
                'message': '未选择文件'
            }), 400

        # 验证文件类型
        if not allowed_file(file.filename):
            return jsonify({
                'code': 400,
                'message': '不支持的文件类型，仅支持 PPT/PPTX 格式'
            }), 400

        # 确保上传目录存在
        upload_folder = os.path.join(current_app.root_path, 'uploads', 'training')
        os.makedirs(upload_folder, exist_ok=True)

        # 处理文件名，保留中文字符并确保唯一性
        original_filename = file.filename
        safe_filename = generate_unique_filename(upload_folder, original_filename)

        # 保存文件
        file_path = os.path.join(upload_folder, safe_filename)
        file.save(file_path)

        # 更新培训记录，存储相对路径
        training.material_path = os.path.join('training', safe_filename)
        training.status = 'completed'
        training.upload_time = datetime.now()

        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '培训材料上传成功',
            'data': {
                'original_name': original_filename,
                'saved_name': safe_filename,
                'upload_time': training.upload_time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': training.status
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"upload_training_material 错误： {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500





# 获取培训列表
@training_bp.route('/list', methods=['GET'])
@token_required
@track_activity
def get_training_list(current_user):  # 添加 current_user 参数
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        month = request.args.get('month')  # 可选过滤条件

        query = Training.query

        if month:
            query = query.filter_by(training_month=month)

        trainings = query.order_by(Training.training_month.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'code': 200,
            'data': {
                'items': [{
                    'id': t.id,
                    'trainer_id': t.trainer_id,
                    'trainer_name': t.trainer.username,  # 假设User模型中有name字段
                    'training_month': t.training_month,
                    'title': t.title,
                    'description': t.description,
                    'status': t.status,
                    'material_path': t.material_path,
                    'upload_time': t.upload_time.strftime('%Y-%m-%d %H:%M:%S') if t.upload_time else None
                } for t in trainings.items],
                'total': trainings.total,
                'pages': trainings.pages,
                'current_page': trainings.page
            }
        })

    except Exception as e:
        print(f"Error in get_training_list: {str(e)}")  # 添加日志输出
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500


# 获取培训详情
@training_bp.route('/<int:training_id>', methods=['GET'])
@token_required
@track_activity
def get_training_detail(current_user, training_id):
    try:
        training = Training.query.get_or_404(training_id)

        # 获取评论及其回复
        comments = Comment.query.filter_by(training_id=training_id) \
            .order_by(Comment.create_time.desc()).all()

        return jsonify({
            'code': 200,
            'data': {
                'id': training.id,
                'trainer_id': training.trainer_id,
                'trainer_name': training.trainer.username,
                'training_month': training.training_month,
                'title': training.title,
                'description': training.description,
                'status': training.status,
                'material_path': training.material_path,
                'is_trainer': current_user.id == training.trainer_id,
                'upload_time': training.upload_time.strftime('%Y-%m-%d %H:%M:%S') if training.upload_time else None,
                'comments': [{
                    'id': comment.id,
                    'user_id': comment.user_id,
                    'user_name': comment.user.name,
                    'content': comment.content,
                    'create_time': comment.create_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'replies': [{
                        'id': reply.id,
                        'user_id': reply.user_id,
                        'user_name': reply.user.name,
                        'content': reply.content,
                        'create_time': reply.create_time.strftime('%Y-%m-%d %H:%M:%S')
                    } for reply in comment.replies]
                } for comment in comments]
            }
        })

    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500


# 添加评论
@training_bp.route('/<int:training_id>/comment', methods=['POST'])
@token_required
@track_activity
def add_comment(training_id):
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({
                'code': 400,
                'message': '评论内容不能为空'
            }), 400

        comment = Comment(
            training_id=training_id,
            user_id=request.user.id,
            content=content
        )

        db.session.add(comment)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '评论成功',
            'data': {
                'id': comment.id,
                'user_id': comment.user_id,
                'user_name': comment.user.name,
                'content': comment.content,
                'create_time': comment.create_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500


# 添加回复
@training_bp.route('/comment/<int:comment_id>/reply', methods=['POST'])
@token_required
@track_activity
def add_reply(comment_id):
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({
                'code': 400,
                'message': '回复内容不能为空'
            }), 400

        reply = Reply(
            comment_id=comment_id,
            user_id=request.user.id,
            content=content
        )

        db.session.add(reply)
        db.session.commit()

        return jsonify({
            'code': 200,
            'message': '回复成功',
            'data': {
                'id': reply.id,
                'user_id': reply.user_id,
                'user_name': reply.user.name,
                'content': reply.content,
                'create_time': reply.create_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500


# 获取培训文件
# @training_bp.route('/files/<path:filename>')
# @token_required
# def get_training_file(current_user, filename):
#     try:
#         return send_from_directory(
#             os.path.join(current_app.static_folder, UPLOAD_FOLDER),
#             filename,
#             as_attachment=True
#         )
#     except Exception as e:
#         return jsonify({
#             'code': 404,
#             'message': f'文件不存在: {str(e)}'
#         }), 404
#
#
# def convert_ppt_to_images(ppt_path):
#     """将 PPT 转换为图片列表"""
#     pdf_path = None
#     try:
#         # 检查源文件是否存在
#         if not os.path.exists(ppt_path):
#             raise FileNotFoundError(f"源文件不存在: {ppt_path}")
#
#         # 创建临时文件路径
#         with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
#             pdf_path = tmp_pdf.name
#
#         # 检查 LibreOffice 是否安装
#         if os.name == 'nt':  # Windows 系统
#             # 检查常见的 LibreOffice 安装路径
#             libreoffice_paths = [
#                 r"C:\Program Files\LibreOffice\program\soffice.exe",
#                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
#             ]
#             libreoffice_exe = None
#             for path in libreoffice_paths:
#                 if os.path.exists(path):
#                     libreoffice_exe = path
#                     break
#             if not libreoffice_exe:
#                 raise Exception("未找到 LibreOffice，请确保已安装 LibreOffice")
#
#             convert_command = [
#                 libreoffice_exe,
#                 '--headless',
#                 '--convert-to',
#                 'pdf',
#                 '--outdir',
#                 os.path.dirname(pdf_path),
#                 ppt_path
#             ]
#         else:  # Linux/Mac 系统
#             convert_command = [
#                 'libreoffice',
#                 '--headless',
#                 '--convert-to',
#                 'pdf',
#                 '--outdir',
#                 os.path.dirname(pdf_path),
#                 ppt_path
#             ]
#
#         # 执行转换命令
#         print(f"执行命令: {' '.join(convert_command)}")  # 添加日志
#         process = subprocess.run(
#             convert_command,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             timeout=60  # 增加超时时间
#         )
#
#         if process.returncode != 0:
#             error_message = process.stderr.decode()
#             print(f"转换失败，错误信息: {error_message}")  # 添加日志
#             raise Exception(f"PPT转PDF失败: {error_message}")
#
#         # 确保 PDF 文件存在
#         if not os.path.exists(pdf_path):
#             raise FileNotFoundError(f"PDF文件未生成: {pdf_path}")
#
#         # 将 PDF 转换为图片
#         images = convert_from_path(
#             pdf_path,
#             dpi=200,
#             fmt="jpeg",
#             thread_count=2
#         )
#
#         # 将图片转换为 base64 字符串列表
#         image_data = []
#         for i, img in enumerate(images):
#             print(f"处理第 {i + 1}/{len(images)} 页")  # 添加日志
#             # 调整图片大小以优化传输
#             max_size = (1024, 768)
#             img.thumbnail(max_size, Image.LANCZOS)
#
#             # 转换为 JPEG 并压缩
#             img_byte_arr = io.BytesIO()
#             img.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
#             img_byte_arr = img_byte_arr.getvalue()
#
#             # 转换为 base64
#             image_data.append(base64.b64encode(img_byte_arr).decode())
#
#         return image_data
#
#     except FileNotFoundError as e:
#         print(f"文件不存在错误: {str(e)}")
#         raise
#     except subprocess.TimeoutExpired:
#         print("转换超时")
#         raise Exception("PPT转换超时，请检查文件是否过大或系统资源是否充足")
#     except Exception as e:
#         print(f"转换过程出错: {str(e)}")
#         raise
#     finally:
#         # 清理临时文件
#         try:
#             if pdf_path and os.path.exists(pdf_path):
#                 os.remove(pdf_path)
#                 print(f"临时PDF文件已删除: {pdf_path}")
#         except Exception as e:
#             print(f"清理临时文件失败: {str(e)}")
#
#
# @training_bp.route('/preview/<path:filename>')
# @token_required
# def preview_training_file(current_user, filename):
#     try:
#         # 解码文件名
#         filename = urllib.parse.unquote(filename)
#         print(f"准备预览文件: {filename}")  # 添加日志
#
#         # 从数据库获取培训记录
#         material_path = os.path.join('training', os.path.basename(filename))
#         training = Training.query.filter_by(material_path=material_path).first()
#         if not training:
#             return jsonify({
#                 'code': 404,
#                 'message': '培训记录不存在'
#             }), 404
#
#         # 构建完整的文件路径
#         file_path = os.path.join(current_app.root_path, 'uploads', 'training', os.path.basename(filename))
#         print(f"完整文件路径: {file_path}")  # 添加日志
#
#         if not os.path.exists(file_path):
#             return jsonify({
#                 'code': 404,
#                 'message': f'文件不存在: {file_path}'
#             }), 404
#
#         # 检查文件扩展名
#         if not filename.lower().endswith(('.ppt', '.pptx')):
#             return jsonify({
#                 'code': 400,
#                 'message': '不支持的文件格式，仅支持 PPT/PPTX'
#             }), 400
#
#         print("开始转换PPT文件")  # 添加日志
#         # 将 PPT 转换为图片列表
#         image_data = convert_ppt_to_images(file_path)
#
#         if not image_data:
#             raise Exception("转换后的图片数据为空")
#
#         print(f"成功转换 {len(image_data)} 页")  # 添加日志
#         return jsonify({
#             'code': 200,
#             'data': {
#                 'images': image_data,
#                 'total_slides': len(image_data)
#             }
#         })
#
#     except FileNotFoundError as e:
#         print(f"文件不存在错误: {str(e)}")
#         return jsonify({
#             'code': 404,
#             'message': str(e)
#         }), 404
#     except Exception as e:
#         print(f"预览生成错误: {str(e)}")
#         return jsonify({
#             'code': 500,
#             'message': f'预览生成失败: {str(e)}'
#         }), 500




