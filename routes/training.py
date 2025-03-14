import base64
import re
import os
import io
import urllib
import hashlib
import json
import time
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from datetime import datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename
from models import db, Training, Comment, Reply, User
from routes.employees import token_required
from routes.filemanagement import python_dir
from utils.activity_tracking import track_activity
import urllib.parse

# 用于缓存的 Redis 集成（带回退）
try:
    import redis

    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    REDIS_AVAILABLE = True
except (ImportError, redis.exceptions.ConnectionError):
    REDIS_AVAILABLE = False
    print("Redis 不可用，回退到基于文件的缓存")

# 创建蓝图
training_bp = Blueprint('training', __name__)

# 文件上传配置，修改为PDF
ALLOWED_EXTENSIONS = {'pdf'}
UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')  # 基础上传目录
# PDF缓存设置
CACHE_EXPIRY = 60 * 60 * 24 * 7  # 缓存七天
CACHE_DIR = os.path.join(python_dir, 'cache', 'pdf_previews')

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)


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


def generate_cache_key(file_path, scale=2.0):
    """
    根据文件路径和最后修改时间生成缓存键
    这样如果文件更新，缓存会自动失效
    """
    mod_time = os.path.getmtime(file_path)
    cache_key = f"pdf_preview:{file_path}:{mod_time}:{scale}"
    return hashlib.md5(cache_key.encode()).hexdigest()


def get_cache_file_path(cache_key):
    """获取缓存文件路径"""
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def save_cache(cache_key, data):
    """保存数据到缓存中"""
    if REDIS_AVAILABLE:
        try:
            # 将数据保存到Redis（使用JSON转换以便处理binary数据）
            redis_client.setex(
                cache_key,
                CACHE_EXPIRY,
                json.dumps({
                    'timestamp': time.time(),
                    'data': data
                })
            )
            return True
        except Exception as e:
            print(f"Redis缓存失败，切换到文件缓存: {str(e)}")

    # 文件缓存备选方案
    try:
        cache_file = get_cache_file_path(cache_key)
        with open(cache_file, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'data': data
            }, f)
        return True
    except Exception as e:
        print(f"文件缓存失败: {str(e)}")
        return False


def get_cache(cache_key):
    """从缓存获取数据"""
    if REDIS_AVAILABLE:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"Redis获取缓存失败，切换到文件缓存: {str(e)}")

    # 文件缓存备选方案
    cache_file = get_cache_file_path(cache_key)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                # 检查缓存是否已过期
                if time.time() - cache_data['timestamp'] < CACHE_EXPIRY:
                    return cache_data['data']
                # 过期则删除缓存文件
                os.remove(cache_file)
        except Exception as e:
            print(f"文件缓存读取失败: {str(e)}")

    return None


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
            trainer_id=trainer_id,
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


# 上传培训材料 - 更新为PDF
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
                'message': '不支持的文件类型，仅支持 PDF 格式'
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


@training_bp.route('/preview/<path:filename>')
@token_required
def preview_training_file(current_user, filename):
    try:
        # 解码文件名
        filename = urllib.parse.unquote(filename)

        # 构建完整的文件路径
        file_path = os.path.join(current_app.root_path, 'uploads', filename)

        if not os.path.exists(file_path):
            return jsonify({
                'code': 404,
                'message': '文件不存在'
            }), 404

        # 对于PDF文件，返回文件信息和访问URL，而不是转换为图像
        if file_path.lower().endswith('.pdf'):
            # 计算文件大小
            file_size = os.path.getsize(file_path)

            # 生成用于前端访问的URL
            file_url = f'/api/training/view/{urllib.parse.quote(filename)}'

            # 尝试获取PDF页数
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                page_count = len(doc)
                doc.close()
            except Exception as e:
                print(f"获取PDF页数失败: {str(e)}")
                page_count = 0

            return jsonify({
                'code': 200,
                'data': {
                    'file_url': file_url,
                    'file_size': file_size,
                    'page_count': page_count,
                    'file_name': os.path.basename(file_path)
                }
            })
        else:
            return jsonify({
                'code': 400,
                'message': '不支持的文件类型，只能预览PDF文件'
            }), 400

    except Exception as e:
        print(f"获取文件信息失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'code': 500,
            'message': f'获取文件信息失败: {str(e)}'
        }), 500


# 4. 添加新路由用于直接查看PDF文件
@training_bp.route('/view/<path:filename>')
# 修改为支持URL参数获取token
@training_bp.route('/view/<path:filename>')
def view_pdf_file(filename):
    try:
        # 从URL参数获取token
        token = request.args.get('token')
        if not token:
            return jsonify({
                'code': 401,
                'message': '未授权访问'
            }), 401

        # 验证token
        try:
            # 使用与token_required相同的验证逻辑
            import jwt
            from flask import current_app
            from models import User

            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.filter_by(id=data['user_id']).first()

            if not current_user:
                return jsonify({'code': 401, 'message': '用户不存在'}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({'code': 401, 'message': 'token已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'code': 401, 'message': '无效的token'}), 401
        except Exception as e:
            return jsonify({
                'code': 401,
                'message': f'token验证失败: {str(e)}'
            }), 401

        # 解码文件名
        filename = urllib.parse.unquote(filename)

        # 构建完整的文件路径
        file_path = os.path.join(current_app.root_path, 'uploads', filename)

        if not os.path.exists(file_path):
            return jsonify({
                'code': 404,
                'message': '文件不存在'
            }), 404

        # 获取文件目录和文件名
        directory = os.path.dirname(file_path)
        return send_from_directory(
            directory,
            os.path.basename(file_path),
            mimetype='application/pdf',
            as_attachment=False  # 不作为附件，直接在浏览器中显示
        )

    except Exception as e:
        print(f"查看文件失败: {str(e)}")
        return jsonify({
            'code': 500,
            'message': f'查看文件失败: {str(e)}'
        }), 500






# 下载文件
@training_bp.route('/download/<path:filename>')
@token_required
def download_training_file(current_user, filename):
    try:
        # 解码文件名
        filename = urllib.parse.unquote(filename)

        # 构建完整的文件路径
        file_path = os.path.join(current_app.root_path, 'uploads', filename)

        if not os.path.exists(file_path):
            return jsonify({
                'code': 404,
                'message': '文件不存在'
            }), 404

        # 获取文件的原始名称
        directory = os.path.dirname(file_path)
        return send_from_directory(
            directory,
            os.path.basename(file_path),
            as_attachment=True
        )

    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'下载失败: {str(e)}'
        }), 500


# 修改为PDF预览 - 使用PyMuPDF (fitz)
class PDFPreviewHandler:
    """使用PyMuPDF处理PDF预览的类"""

    @staticmethod
    def process_pdf(pdf_path, scale=2.0):
        """
        处理PDF文件，将每页转换为图像

        Args:
            pdf_path: PDF文件路径
            scale: 缩放因子，用于提高图像质量

        Returns:
            字典，包含成功标志和页面数据
        """
        try:
            print(f"处理PDF文件: {pdf_path}")

            import fitz  # PyMuPDF

            # 打开PDF文件
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            print(f"PDF共有 {total_pages} 页")

            slides = []

            # 处理每一页
            for page_num in range(total_pages):
                print(f"处理第 {page_num + 1} 页")

                # 获取页面
                page = doc.load_page(page_num)

                # 设置渲染参数 - 提高分辨率
                matrix = fitz.Matrix(scale, scale)

                # 渲染页面为像素图
                pix = page.get_pixmap(matrix=matrix)

                # 将图像数据转换为PIL图像
                img_data = pix.tobytes("png")

                # 转换为base64
                img_base64 = base64.b64encode(img_data).decode()

                # 添加到结果中
                slides.append({
                    'image': img_base64,
                    'page_number': page_num + 1,
                    'texts': []  # PDF预览不提取文本
                })

            # 关闭PDF文档
            doc.close()

            return {
                'success': True,
                'slides': slides,
                'total_slides': total_pages
            }

        except Exception as e:
            print(f"处理PDF时出错: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }


# 清理过期缓存的计划任务函数 - 可以通过Celery或其他方式定时调用
def clean_expired_cache():
    """清理过期的文件缓存"""
    now = time.time()
    count = 0

    # 检查文件缓存
    for filename in os.listdir(CACHE_DIR):
        if not filename.endswith('.json'):
            continue

        file_path = os.path.join(CACHE_DIR, filename)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if now - data['timestamp'] > CACHE_EXPIRY:
                    os.remove(file_path)
                    count += 1
        except Exception as e:
            print(f"清理缓存文件出错: {str(e)}")
            # 如果文件损坏，直接删除
            try:
                os.remove(file_path)
                count += 1
            except:
                pass

    print(f"清理了 {count} 个过期缓存文件")
    return count