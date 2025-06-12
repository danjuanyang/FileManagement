# routes/knowledge_base.py
import os
from functools import wraps
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import mimetypes  # 导入 mimetypes


from models import db, User, KnowledgeBase, KnowledgeBaseNode, KnowledgeBaseFile
from routes.employees import token_required

kb_bp = Blueprint('knowledge_base', __name__)


# --- 权限控制装饰器 ---
def permission_required(roles):
    """
    一个装饰器，用于检查当前用户是否具有所需角色权限。
    :param roles: 允许访问的角色列表 (例如 [0, 1])
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(current_user, *args, **kwargs):
            if current_user.role not in roles:
                return jsonify({'error': '权限不足，无法执行此操作'}), 403
            return f(current_user, *args, **kwargs)

        return decorated_function

    return decorator


# --- 新增API：获取当前用户信息 ---
@kb_bp.route('/users/me', methods=['GET'])
@token_required
def get_current_user_profile(current_user):
    """获取当前登录用户的信息 (包括角色)"""
    if not current_user:
        return jsonify({"error": "用户未找到或Token无效"}), 404

    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role
    }), 200


# --- 辅助函数 ---
def build_node_tree(kb_id):
    """
    为给定的知识库构建完整的节点树。
    """
    # 查找所有根节点 (没有父节点的节点)
    root_nodes = KnowledgeBaseNode.query.filter_by(kb_id=kb_id, parent_id=None).all()
    # 使用模型中定义的 to_dict 方法递归地构建树
    tree = [node.to_dict() for node in root_nodes]
    return tree


# ===============================================================
#  知识库 (KnowledgeBase) 管理 API
# ===============================================================

@kb_bp.route('/kbs', methods=['GET'])
@token_required
def list_knowledge_bases(current_user):
    """获取所有知识库的列表 (对所有登录用户开放)"""
    kbs = KnowledgeBase.query.order_by(KnowledgeBase.name).all()
    return jsonify([kb.to_dict() for kb in kbs]), 200


@kb_bp.route('/kbs', methods=['POST'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def create_knowledge_base(current_user):
    """创建一个新的知识库"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': '缺少知识库名称'}), 400

    if KnowledgeBase.query.filter_by(name=data['name']).first():
        return jsonify({'error': '该知识库名称已存在'}), 409

    new_kb = KnowledgeBase(
        name=data['name'],
        description=data.get('description', ''),
        created_by_id=current_user.id
    )
    db.session.add(new_kb)
    db.session.commit()
    return jsonify(new_kb.to_dict()), 201


@kb_bp.route('/kbs/<int:kb_id>', methods=['PUT'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def update_knowledge_base(current_user, kb_id):
    """更新一个知识库的名称或描述"""
    kb = KnowledgeBase.query.get_or_404(kb_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体为空'}), 400

    if 'name' in data:
        # 检查新名称是否与其它知识库冲突
        existing_kb = KnowledgeBase.query.filter(KnowledgeBase.name == data['name'], KnowledgeBase.id != kb_id).first()
        if existing_kb:
            return jsonify({'error': '该知识库名称已存在'}), 409
        kb.name = data['name']

    if 'description' in data:
        kb.description = data['description']

    db.session.commit()
    return jsonify(kb.to_dict()), 200


@kb_bp.route('/kbs/<int:kb_id>', methods=['DELETE'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def delete_knowledge_base(current_user, kb_id):
    """删除一个知识库及其所有内容"""
    kb = KnowledgeBase.query.get_or_404(kb_id)
    # 由于模型中设置了 cascade='all, delete-orphan'，相关节点和文件会被自动删除
    db.session.delete(kb)
    db.session.commit()
    return jsonify({'message': f'知识库 "{kb.name}" 已被成功删除'}), 200


# ===============================================================
#  知识库节点 (Node) 管理 API
# ===============================================================

@kb_bp.route('/kbs/<int:kb_id>/tree', methods=['GET'])
@token_required
def get_knowledge_base_tree(current_user, kb_id):
    """获取指定知识库的完整节点树 (对所有登录用户开放)"""
    if not KnowledgeBase.query.get(kb_id):
        return jsonify({'error': '知识库不存在'}), 404
    tree = build_node_tree(kb_id)
    return jsonify(tree), 200


@kb_bp.route('/nodes', methods=['POST'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def create_node(current_user):
    """创建一个新节点（根节点或子节点）"""
    data = request.get_json()
    if not data or 'name' not in data or 'kb_id' not in data:
        return jsonify({'error': '缺少必要参数 (name, kb_id)'}), 400

    if not KnowledgeBase.query.get(data['kb_id']):
        return jsonify({'error': '指定的知识库不存在'}), 404

    new_node = KnowledgeBaseNode(
        name=data['name'],
        description=data.get('description', ''),
        kb_id=data['kb_id'],
        parent_id=data.get('parent_id')  # 如果没有parent_id，则为根节点
    )
    db.session.add(new_node)
    db.session.commit()
    return jsonify(new_node.to_dict(include_children=False)), 201


@kb_bp.route('/nodes/<int:node_id>', methods=['PUT'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def update_node(current_user, node_id):
    """更新一个节点的名称或描述"""
    node = KnowledgeBaseNode.query.get_or_404(node_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体为空'}), 400

    if 'name' in data:
        node.name = data['name']
    if 'description' in data:
        node.description = data['description']

    node.updated_at = datetime.now()  # 修复：正确地更新时间
    db.session.commit()
    return jsonify(node.to_dict(include_children=False)), 200


@kb_bp.route('/nodes/<int:node_id>', methods=['DELETE'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def delete_node(current_user, node_id):
    """删除一个节点及其所有子节点和文件"""
    node = KnowledgeBaseNode.query.get_or_404(node_id)
    db.session.delete(node)
    db.session.commit()
    return jsonify({'message': f'节点 "{node.name}" 已被成功删除'}), 200


@kb_bp.route('/nodes/insert', methods=['POST'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def insert_node_layer(current_user):
    """
    在已有节点下插入一个新的层级，并将原节点的文件移动到新层级。
    """
    data = request.get_json()
    if not data or 'parent_id' not in data or 'name' not in data:
        return jsonify({'error': '缺少必要参数 (parent_id, name)'}), 400

    parent_node = KnowledgeBaseNode.query.get(data['parent_id'])
    if not parent_node:
        return jsonify({'error': '指定的父节点不存在'}), 404

    try:
        # 1. 创建新节点
        new_child_node = KnowledgeBaseNode(
            name=data['name'],
            parent_id=parent_node.id,
            kb_id=parent_node.kb_id  # 继承父节点的知识库ID
        )
        db.session.add(new_child_node)
        db.session.flush()  # 刷新会话以获取 new_child_node.id

        # 2. 查找原父节点的所有文件
        files_to_move = list(parent_node.files)

        # 3. 如果有文件，则移动它们
        if files_to_move:
            for file in files_to_move:
                file.node_id = new_child_node.id

        db.session.commit()
        return jsonify(new_child_node.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'插入层级时发生错误: {str(e)}'}), 500


# ===============================================================
#  知识库文件 (File) 管理 API
# ===============================================================

@kb_bp.route('/nodes/<int:node_id>/files', methods=['POST'])
@token_required
def upload_file(current_user, node_id):
    """
    上传文件到一个指定的节点 (对所有登录用户开放)。
    """
    if 'file' not in request.files:
        return jsonify({'error': '请求中没有文件部分'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    node = KnowledgeBaseNode.query.get(node_id)
    if not node:
        return jsonify({'error': '目标节点不存在'}), 404

    # 检查节点是否为叶子节点（没有子节点）
    if node.children.first():
        return jsonify({'error': '只能向最末端的节点上传文件'}), 400

    if file:
        filename = secure_filename(file.filename)
        # 创建一个与知识库相关的唯一文件路径
        kb_folder = f"kb_{node.kb_id}"

        base_upload_path = current_app.config['UPLOAD_FOLDER']
        upload_path = os.path.join(base_upload_path, 'knowledge_base', kb_folder)
        os.makedirs(upload_path, exist_ok=True)

        # 防止文件名冲突，可以加上时间戳或UUID
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(upload_path, unique_filename)

        file.save(file_path)

        # 在数据库中创建记录
        new_file = KnowledgeBaseFile(
            node_id=node.id,
            original_name=filename,
            file_path=os.path.join('knowledge_base', kb_folder, unique_filename),  # 存储相对路径
            file_type=file.mimetype,
            upload_user_id=current_user.id
        )
        db.session.add(new_file)
        db.session.commit()

        return jsonify(new_file.to_dict()), 201

    return jsonify({'error': '文件上传失败'}), 500


@kb_bp.route('/files/<int:file_id>', methods=['DELETE'])
@token_required
@permission_required([0, 1])  # 仅限管理员和领导
def delete_file(current_user, file_id):
    """删除一个文件"""
    file_record = KnowledgeBaseFile.query.get_or_404(file_id)

    try:
        # 从文件系统中删除物理文件
        physical_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_record.file_path)
        if os.path.exists(physical_file_path):
            os.remove(physical_file_path)

        # 从数据库中删除记录
        db.session.delete(file_record)
        db.session.commit()

        return jsonify({'message': '文件已成功删除'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'删除文件时发生错误: {str(e)}'}), 500


# --- 优化 #4: 修改下载路由以支持预览 ---
@kb_bp.route('/download/files/<int:file_id>', methods=['GET'])
@token_required
def download_file(current_user, file_id):
    """下载或预览一个文件 (对所有登录用户开放)"""
    file_record = KnowledgeBaseFile.query.get_or_404(file_id)

    # 检查 'preview' 查询参数
    is_preview = request.args.get('preview', 'false').lower() == 'true'

    try:
        directory = os.path.join(current_app.config['UPLOAD_FOLDER'])
        path_parts = file_record.file_path.replace('\\', '/').split('/')
        filename = path_parts[-1]
        sub_directory = '/'.join(path_parts[:-1])

        full_directory_path = os.path.join(directory, sub_directory)

        # 尝试获取mimetype，如果失败则使用通用类型
        mimetype, _ = mimetypes.guess_type(file_record.original_name)
        if mimetype is None:
            mimetype = 'application/octet-stream'

        return send_from_directory(
            full_directory_path,
            filename,
            as_attachment=not is_preview,  # 如果是预览，则不是附件
            download_name=file_record.original_name,
            mimetype=mimetype  # 指定mimetype
        )
    except FileNotFoundError:
        return jsonify({'error': '文件在服务器上未找到'}), 404
    except Exception as e:
        return jsonify({'error': f'下载文件时出错: {str(e)}'}), 500
