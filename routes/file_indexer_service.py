# file_indexer_service.py
import os
from datetime import datetime
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from models import ProjectFile, db
from file_indexer import FileContentExtractor
import threading
import queue
import time


class FileIndexerService:
    def __init__(self, app=None):
        self.app = app
        self.index_queue = queue.Queue()
        self.is_running = False
        self.worker_thread = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        """初始化服务，设置事件监听器"""
        self.app = app

        # 在应用启动时开始索引
        @app.before_first_request
        def start_indexing_service():
            self.start()
            self.reindex_all_files()

        # 监听文件创建和更新事件
        @event.listens_for(ProjectFile, 'after_insert')
        def handle_file_created(mapper, connection, target):
            self.queue_file_for_indexing(target.id)

        @event.listens_for(ProjectFile, 'after_update')
        def handle_file_updated(mapper, connection, target):
            self.queue_file_for_indexing(target.id)

    def start(self):
        """启动索引服务"""
        if not self.is_running:
            self.is_running = True
            self.worker_thread = threading.Thread(target=self._process_queue)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            print("File indexing service started")

    def stop(self):
        """停止索引服务"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join()
            print("File indexing service stopped")

    def queue_file_for_indexing(self, file_id):
        """将文件加入索引队列"""
        self.index_queue.put(file_id)

    def _process_queue(self):
        """处理索引队列的后台线程"""
        while self.is_running:
            try:
                file_id = self.index_queue.get(timeout=1)
                self._index_file(file_id)
                self.index_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error processing file index: {str(e)}")

    def _index_file(self, file_id):
        """索引单个文件的内容"""
        with self.app.app_context():
            try:
                file_record = ProjectFile.query.get(file_id)
                if not file_record:
                    return

                file_path = os.path.join(self.app.root_path, file_record.file_path)
                if not os.path.exists(file_path):
                    return

                # 提取文件内容
                content = FileContentExtractor.extract_content(file_path)
                if content:
                    # 更新数据库中的内容文本
                    file_record.content_text = content
                    file_record.indexed_at = datetime.now()
                    db.session.commit()
                    print(f"Indexed file: {file_record.original_name}")

            except Exception as e:
                print(f"Error indexing file {file_id}: {str(e)}")
                db.session.rollback()

    def reindex_all_files(self):
        """重新索引所有文件"""
        with self.app.app_context():
            try:
                files = ProjectFile.query.all()
                for file in files:
                    self.queue_file_for_indexing(file.id)
                print(f"Queued {len(files)} files for reindexing")
            except Exception as e:
                print(f"Error queuing files for reindexing: {str(e)}")

    def search_content(self, query, user_id=None, limit=10):
        """搜索文件内容

        Args:
            query: 搜索关键词
            user_id: 可选的用户ID限制
            limit: 返回结果数量限制

        Returns:
            list: 匹配的文件记录列表
        """
        with self.app.app_context():
            try:
                base_query = ProjectFile.query.filter(
                    ProjectFile.content_text.ilike(f'%{query}%')
                )

                if user_id:
                    base_query = base_query.filter(ProjectFile.upload_user_id == user_id)

                return base_query.limit(limit).all()

            except Exception as e:
                print(f"Error searching content: {str(e)}")
                return []
