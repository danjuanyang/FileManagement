# routes/AI_assistant.py
import os
import requests
from datetime import datetime
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from sqlalchemy.exc import SQLAlchemyError

from models import db, User, AIApi, AIConversation, AIMessage, AITag, AIConversationTag, AIMessageFeedback
from routes.employees import token_required
from utils.activity_tracking import track_activity

ai_bp = Blueprint('ai', __name__)
CORS(ai_bp)  # 为此蓝图启用 CORS

# DeepSeek API 配置
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def get_user_api_key(user_id):
    """获取当前用户的 API 密钥"""
    api = AIApi.query.filter_by(user_id=user_id).order_by(AIApi.updated_at.desc()).first()

    if not api:
        # 如果用户没有设置 API 密钥，使用默认密钥
        return current_app.config.get('DEFAULT_DEEPSEEK_API_KEY')

    return api.api_key


def call_deepseek_api(messages, user_id, model="deepseek-chat"):
    """调用 DeepSeek API"""
    api_key = get_user_api_key(user_id)
    if not api_key:
        return {"error": "没有可用的API密钥"}, 400

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": messages
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return response.json(), 200
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"DeepSeek API 错误: {str(e)}")
        return {"error": str(e)}, 500


@ai_bp.route('/api-keys', methods=['GET'])
@track_activity
@token_required
def get_api_keys(current_user):
    """获取用户的所有 API 密钥"""
    # 检查是否为管理员，并是否指定了用户ID
    is_admin = current_user.role == 1
    target_user_id = request.args.get('user_id', type=int)

    if is_admin and target_user_id:
        # 管理员可以查看指定用户的API密钥
        api_keys = AIApi.query.filter_by(user_id=target_user_id).all()
    elif is_admin:
        # 管理员查看所有API密钥
        api_keys = AIApi.query.all()
    else:
        # 普通用户只能查看自己的API密钥
        api_keys = AIApi.query.filter_by(user_id=current_user.id).all()

    result = []
    for api in api_keys:
        # 获取用户名（仅管理员需要）
        username = None
        if is_admin:
            user = User.query.filter_by(id=api.user_id).first()
            username = user.username if user else "未知用户"
        else:
            # 普通用户只能查看自己的用户名
            username = current_user.username

        result.append({
            'id': api.id,
            'user_id': api.user_id,
            'username': username,  # 返回对应的用户名
            'ai_model': api.ai_model,
            'api_key': '*' * 4 + api.api_key[-4:] if api.api_key else '',  # 只显示最后4位
            'updated_at': api.updated_at.isoformat() if api.updated_at else None
        })

    return jsonify(result)


@ai_bp.route('/api-keys', methods=['POST'])
@track_activity
@token_required
def add_api_key(current_user):
    """添加新的 API 密钥"""
    data = request.json
    is_admin = current_user.role == 1

    if not data.get('api_key'):
        return jsonify({"error": "API密钥是必填项"}), 400

    if not data.get('ai_model'):
        return jsonify({"error": "AI模型是必填项"}), 400

    # 确定用户ID
    if is_admin:
        # 管理员必须指定用户
        if not data.get('user_id'):
            return jsonify({"error": "管理员必须指定目标用户"}), 400

        # 验证目标用户是否存在
        target_user_id = data.get('user_id')
        target_user = User.query.get(target_user_id)
        if not target_user:
            return jsonify({"error": "指定的用户不存在"}), 404
    else:
        # 普通用户只能为自己添加API密钥
        target_user_id = current_user.id

    try:
        new_api = AIApi(
            user_id=target_user_id,
            ai_model=data.get('ai_model', 'deepseek-chat'),
            api_key=data.get('api_key'),
            updated_at=datetime.now()
        )
        db.session.add(new_api)
        db.session.commit()

        # 获取用户名（仅管理员需要）
        username = None
        if is_admin:
            user = User.query.filter_by(id=target_user_id).first()
            username = user.username if user else "未知用户"

        return jsonify({
            'id': new_api.id,
            'user_id': new_api.user_id,
            'username': username,
            'ai_model': new_api.ai_model,
            'api_key': '*' * 4 + new_api.api_key[-4:] if new_api.api_key else '',
            'updated_at': new_api.updated_at.isoformat() if new_api.updated_at else None
        }), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "添加API密钥失败"}), 500


@ai_bp.route('/api-keys/<int:api_id>', methods=['DELETE'])
@track_activity
@token_required
def delete_api_key(current_user, api_id):
    """删除 API 密钥"""
    is_admin = current_user.role == 1
    api = AIApi.query.get(api_id)

    if not api:
        return jsonify({"error": "未找到API密钥"}), 404

    # 权限检查
    if not is_admin and api.user_id != current_user.id:
        return jsonify({"error": "无权限删除此API密钥"}), 403

    try:
        db.session.delete(api)
        db.session.commit()
        return jsonify({"message": "API密钥删除成功"}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "删除API密钥失败"}), 500


@ai_bp.route('/conversations', methods=['GET'])
@track_activity
@token_required
def get_conversations(current_user):
    """获取用户的所有对话"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    is_admin = current_user.role == 1
    target_user_id = request.args.get('user_id', type=int)

    # 构建查询
    query = AIConversation.query.filter_by(is_archived=False)

    # if is_admin and target_user_id:
    #     # 管理员查看特定用户的对话
    #     query = query.filter_by(user_id=target_user_id)
    # elif not is_admin:
    #     # 普通用户只能查看自己的对话
    #     query = query.filter_by(user_id=current_user.id)

    # 管理员和用户都只能看到自己会话
    query = query.filter_by(user_id=current_user.id)

    # 按更新时间排序并分页
    conversations = query.order_by(AIConversation.updated_at.desc()).paginate(page=page, per_page=per_page)

    result = {
        'items': [],
        'total': conversations.total,
        'pages': conversations.pages,
        'page': page
    }

    for conv in conversations.items:
        # 获取用户名（仅管理员需要）
        username = None
        if is_admin:
            user = User.query.filter_by(id=conv.user_id).first()
            username = user.username if user else "未知用户"

        result['items'].append({
            'id': conv.id,
            'user_id': conv.user_id,
            'username': username,
            'title': conv.title,
            'created_at': conv.created_at.isoformat() if conv.created_at else None,
            'updated_at': conv.updated_at.isoformat() if conv.updated_at else None,
            'tags': [tag.name for tag in conv.tags]
        })

    return jsonify(result)


@ai_bp.route('/conversations', methods=['POST'])
@track_activity
@token_required
def create_conversation(current_user):
    """创建新对话"""
    data = request.json

    try:
        title = data.get('title', '新对话')
        conversation = AIConversation(
            user_id=current_user.id,
            title=title,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(conversation)
        db.session.flush()  # 获取新会话ID

        # 添加系统消息（如果提供）
        system_message = data.get('system_message')
        if system_message:
            message = AIMessage(
                conversation_id=conversation.id,
                content=system_message,
                role='system',
                created_at=datetime.now()
            )
            db.session.add(message)

        # 添加标签（如果提供）
        tags = data.get('tags', [])
        for tag_name in tags:
            # 查找或创建标签
            tag = AITag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = AITag(name=tag_name)
                db.session.add(tag)
                db.session.flush()  # 获取新标签的ID

            # 将标签和对话关联起来
            conversation.tags.append(tag)

        db.session.commit()

        return jsonify({
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat() if conversation.created_at else None,
            'updated_at': conversation.updated_at.isoformat() if conversation.updated_at else None,
            'tags': [tag.name for tag in conversation.tags]
        }), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "创建对话失败"}), 500


@ai_bp.route('/conversations/<int:conv_id>', methods=['GET'])
@track_activity
@token_required
def get_conversation(current_user, conv_id):
    """获取特定对话及其消息"""
    is_admin = current_user.role == 1
    conversation = AIConversation.query.get(conv_id)

    if not conversation:
        return jsonify({"error": "未找到对话"}), 404

    # 权限检查
    if not is_admin and conversation.user_id != current_user.id:
        return jsonify({"error": "无权访问此对话"}), 403

    messages = AIMessage.query.filter_by(conversation_id=conv_id).order_by(AIMessage.created_at).all()

    # 获取用户名（仅管理员需要）
    username = None
    if is_admin:
        user = User.query.filter_by(id=conversation.user_id).first()
        username = user.username if user else "未知用户"

    return jsonify({
        'id': conversation.id,
        'user_id': conversation.user_id,
        'username': username,
        'title': conversation.title,
        'created_at': conversation.created_at.isoformat() if conversation.created_at else None,
        'updated_at': conversation.updated_at.isoformat() if conversation.updated_at else None,
        'tags': [tag.name for tag in conversation.tags],
        'messages': [{
            'id': msg.id,
            'content': msg.content,
            'role': msg.role,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
            'tokens_used': msg.tokens_used,
            'model_version': msg.model_version
        } for msg in messages]
    })


@ai_bp.route('/conversations/<int:conv_id>', methods=['PUT'])
@track_activity
@token_required
def update_conversation(current_user, conv_id):
    """更新对话（如标题、标签等）"""
    is_admin = current_user.role == 1
    conversation = AIConversation.query.get(conv_id)

    if not conversation:
        return jsonify({"error": "未找到对话"}), 404

    # 权限检查
    if not is_admin and conversation.user_id != current_user.id:
        return jsonify({"error": "无权更新此对话"}), 403

    data = request.json

    try:
        if 'title' in data:
            conversation.title = data['title']

        if 'is_archived' in data:
            conversation.is_archived = data['is_archived']

        if 'tags' in data:
            # 移除所有现有标签
            conversation.tags.clear()

            # 添加新标签
            for tag_name in data['tags']:
                tag = AITag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = AITag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()

                conversation.tags.append(tag)

        conversation.updated_at = datetime.now()
        db.session.commit()

        # 获取用户名（仅管理员需要）
        username = None
        if is_admin:
            user = User.query.filter_by(id=conversation.user_id).first()
            username = user.username if user else "未知用户"

        return jsonify({
            'id': conversation.id,
            'user_id': conversation.user_id,
            'username': username,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat() if conversation.created_at else None,
            'updated_at': conversation.updated_at.isoformat() if conversation.updated_at else None,
            'is_archived': conversation.is_archived,
            'tags': [tag.name for tag in conversation.tags]
        })

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "更新对话失败"}), 500


@ai_bp.route('/conversations/<int:conv_id>', methods=['DELETE'])
@track_activity
@token_required
def delete_conversation(current_user, conv_id):
    """删除对话（实际上是归档）"""
    is_admin = current_user.role == 1
    conversation = AIConversation.query.get(conv_id)

    if not conversation:
        return jsonify({"error": "未找到对话"}), 404

    # 权限检查
    if not is_admin and conversation.user_id != current_user.id:
        return jsonify({"error": "无权删除此对话"}), 403

    try:
        # 可以选择软删除（归档）或硬删除
        if request.args.get('hard_delete') == 'true':
            db.session.delete(conversation)  # 级联删除所有消息和关联
        else:
            conversation.is_archived = True
            conversation.updated_at = datetime.now()

        db.session.commit()
        return jsonify({"message": "对话删除成功"})

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "删除对话失败"}), 500


@ai_bp.route('/conversations/<int:conv_id>/messages', methods=['POST'])
@track_activity
@token_required
def send_message(current_user, conv_id):
    """发送新消息并获取 AI 回复"""
    is_admin = current_user.role == 1
    conversation = AIConversation.query.get(conv_id)

    if not conversation:
        return jsonify({"error": "未找到对话"}), 404

    # 权限检查
    if not is_admin and conversation.user_id != current_user.id:
        return jsonify({"error": "无权访问此对话"}), 403

    data = request.json
    if not data.get('content'):
        return jsonify({"error": "消息内容是必填项"}), 400

    try:
        # 使用指定的 AI 模型（如果提供）
        model = data.get('model', 'deepseek-chat')

        # 保存用户消息
        user_message = AIMessage(
            conversation_id=conv_id,
            content=data['content'],
            role='user',
            created_at=datetime.now()
        )
        db.session.add(user_message)
        db.session.flush()  # 获取消息ID

        # 获取对话历史
        messages = AIMessage.query.filter_by(conversation_id=conv_id).order_by(AIMessage.created_at).all()
        message_history = [{"role": msg.role, "content": msg.content} for msg in messages]

        # 调用 DeepSeek API
        ai_response, status_code = call_deepseek_api(message_history, conversation.user_id, model)

        if status_code != 200:
            return jsonify(ai_response), status_code

        # 保存 AI 回复
        assistant_message = AIMessage(
            conversation_id=conv_id,
            content=ai_response['choices'][0]['message']['content'],
            role='assistant',
            created_at=datetime.now(),
            tokens_used=ai_response.get('usage', {}).get('total_tokens', 0),
            model_version=model
        )
        db.session.add(assistant_message)

        # 更新对话的最后更新时间
        conversation.updated_at = datetime.now()

        # 如果对话没有标题，使用对话的前几个词作为标题
        if not conversation.title or conversation.title == '新对话':
            content_words = data['content'].strip().split()
            title_words = content_words[:5] if len(content_words) > 5 else content_words
            conversation.title = ' '.join(title_words) + '...'

        db.session.commit()

        return jsonify({
            'user_message': {
                'id': user_message.id,
                'content': user_message.content,
                'role': user_message.role,
                'created_at': user_message.created_at.isoformat() if user_message.created_at else None
            },
            'ai_message': {
                'id': assistant_message.id,
                'content': assistant_message.content,
                'role': assistant_message.role,
                'created_at': assistant_message.created_at.isoformat() if assistant_message.created_at else None,
                'tokens_used': assistant_message.tokens_used,
                'model_version': assistant_message.model_version
            }
        })

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "处理消息失败"}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"处理消息时出错: {str(e)}")
        return jsonify({"error": str(e)}), 500


@ai_bp.route('/messages/<int:msg_id>/feedback', methods=['POST'])
@track_activity
@token_required
def add_message_feedback(current_user, msg_id):
    """为 AI 消息添加反馈"""
    is_admin = current_user.role == 1
    message = AIMessage.query.filter_by(id=msg_id, role='assistant').first()

    if not message:
        return jsonify({"error": "未找到消息"}), 404

    # 确认用户拥有该消息所属的对话或是管理员
    conversation = AIConversation.query.get(message.conversation_id)
    if not conversation:
        return jsonify({"error": "未找到对话"}), 404

    if not is_admin and conversation.user_id != current_user.id:
        return jsonify({"error": "无权访问此消息"}), 403

    data = request.json
    if 'rating' not in data or data['rating'] not in [1, -1]:
        return jsonify({"error": "需要有效的评分 (1 或 -1)"}), 400

    try:
        # 检查是否已存在反馈，如果存在则更新
        feedback = AIMessageFeedback.query.filter_by(message_id=msg_id).first()

        if feedback:
            feedback.rating = data['rating']
            feedback.feedback_text = data.get('feedback_text')
        else:
            feedback = AIMessageFeedback(
                message_id=msg_id,
                rating=data['rating'],
                feedback_text=data.get('feedback_text'),
                created_at=datetime.now()
            )
            db.session.add(feedback)

        db.session.commit()

        return jsonify({
            'id': feedback.id,
            'message_id': feedback.message_id,
            'rating': feedback.rating,
            'feedback_text': feedback.feedback_text,
            'created_at': feedback.created_at.isoformat() if feedback.created_at else None
        })

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"数据库错误: {str(e)}")
        return jsonify({"error": "保存反馈失败"}), 500


@ai_bp.route('/feedbacks', methods=['GET'])
@track_activity
@token_required
def get_feedbacks(current_user):
    """获取消息反馈列表"""
    is_admin = current_user.role == 1
    target_user_id = request.args.get('user_id', type=int)

    # 基本查询
    query = db.session.query(
        AIMessageFeedback,
        AIMessage.content.label('message_content'),
        AIConversation.user_id.label('user_id'),
        User.username.label('username')
    ).join(
        AIMessage, AIMessageFeedback.message_id == AIMessage.id
    ).join(
        AIConversation, AIMessage.conversation_id == AIConversation.id
    ).join(
        User, AIConversation.user_id == User.id
    )

    # 权限过滤
    if is_admin and target_user_id:
        # 管理员查看特定用户的反馈
        query = query.filter(AIConversation.user_id == target_user_id)
    elif not is_admin:
        # 普通用户只能查看自己的反馈
        query = query.filter(AIConversation.user_id == current_user.id)

    # 执行查询
    results = query.order_by(AIMessageFeedback.created_at.desc()).all()

    feedbacks = []
    for feedback, message_content, user_id, username in results:
        feedbacks.append({
            'id': feedback.id,
            'message_id': feedback.message_id,
            'message_content': message_content,
            'user_id': user_id,
            'username': username,
            'rating': feedback.rating,
            'feedback_text': feedback.feedback_text,
            'created_at': feedback.created_at.isoformat() if feedback.created_at else None
        })

    return jsonify(feedbacks)


@ai_bp.route('/tags', methods=['GET'])
@track_activity
@token_required
def get_tags(current_user):
    """获取所有标签"""
    tags = AITag.query.all()
    return jsonify([{
        'id': tag.id,
        'name': tag.name
    } for tag in tags])


@ai_bp.route('/stats', methods=['GET'])
@track_activity
@token_required
def get_usage_stats(current_user):
    """获取用户的 API 使用统计信息"""
    is_admin = current_user.role == 1
    target_user_id = request.args.get('user_id', type=int)

    # 确定要查询的用户ID
    if is_admin and target_user_id:
        user_id = target_user_id
    else:
        user_id = current_user.id

    # 获取总对话数
    total_conversations_query = AIConversation.query

    # 管理员可以查看所有用户的统计
    if is_admin and not target_user_id:
        total_conversations = total_conversations_query.count()
        conversation_ids = [c.id for c in total_conversations_query.all()]
    else:
        total_conversations = total_conversations_query.filter_by(user_id=user_id).count()
        conversation_ids = [c.id for c in total_conversations_query.filter_by(user_id=user_id).all()]

    # 获取总消息数
    total_messages = AIMessage.query.filter(
        AIMessage.conversation_id.in_(conversation_ids)).count() if conversation_ids else 0

    # 获取总令牌使用量
    total_tokens = db.session.query(db.func.sum(AIMessage.tokens_used)). \
                       filter(AIMessage.conversation_id.in_(conversation_ids)).scalar() or 0 if conversation_ids else 0

    # 获取按模型分组的令牌使用量
    tokens_by_model = {}
    if conversation_ids:
        model_stats = db.session.query(
            AIMessage.model_version,
            db.func.sum(AIMessage.tokens_used)
        ).filter(
            AIMessage.conversation_id.in_(conversation_ids)
        ).group_by(
            AIMessage.model_version
        ).all()

        tokens_by_model = {model: tokens for model, tokens in model_stats if model}

    # 按月统计使用情况
    monthly_usage = {}
    if conversation_ids:
        month_stats = db.session.query(
            db.func.strftime('%Y-%m', AIMessage.created_at).label('month'),
            db.func.sum(AIMessage.tokens_used)
        ).filter(
            AIMessage.conversation_id.in_(conversation_ids)
        ).group_by(
            'month'
        ).order_by(
            'month'
        ).all()

        monthly_usage = {month: tokens for month, tokens in month_stats if month}

    return jsonify({
        'total_conversations': total_conversations,
        'total_messages': total_messages,
        'total_tokens': total_tokens,
        'tokens_by_model': tokens_by_model,
        'monthly_usage': monthly_usage
    })
