# file_merger.py
import os
import re
import shutil
import tempfile
import io
from datetime import datetime

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

from flask import current_app

# 导入需要的模型
from models import db, Project, ProjectFile, ProjectStage, User, StageTask, Subproject


def setup_fonts():
    """设置字体"""
    try:
        # 获取字体文件路径
        font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fonts', 'simsun.ttf')

        # 注册基本字体
        pdfmetrics.registerFont(TTFont('SimSun', font_path))

        # 注册字体变体
        pdfmetrics.registerFontFamily(
            'SimSun',
            normal='SimSun',
            bold='SimSun',  # 使用同一个字体文件
            italic='SimSun',  # 使用同一个字体文件
            boldItalic='SimSun'  # 使用同一个字体文件
        )
        return True
    except Exception as e:
        print(f"字体设置失败: {str(e)}")
        return False


def create_title_page(text, output_path, font_size=16, subtitle=None):
    """创建带有居中文本的空白页（标题页），可选添加副标题"""
    try:
        if not setup_fonts():
            raise Exception("字体设置失败")

        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # 设置字体
        c.setFont("SimSun", font_size)

        # 在页面中央添加文本
        text_width = c.stringWidth(text, "SimSun", font_size)
        x = (width - text_width) / 2
        y = height / 2

        c.drawString(x, y, text)

        # 如果有副标题，添加副标题
        if subtitle:
            c.setFont("SimSun", font_size - 4)
            subtitle_width = c.stringWidth(subtitle, "SimSun", font_size - 4)
            x = (width - subtitle_width) / 2
            y = height / 2 - font_size - 10
            c.drawString(x, y, subtitle)

        c.showPage()
        c.save()

        return True
    except Exception as e:
        print(f"创建空白页失败: {str(e)}")
        return False


def create_toc_page(toc_items, output_path):
    """创建目录页"""
    try:
        if not setup_fonts():
            raise Exception("字体设置失败")

        # 创建PDF文档
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm
        )

        # 获取样式
        styles = getSampleStyleSheet()

        # 创建自定义样式
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontName='SimSun',
            fontSize=18,
            alignment=1,  # 居中
            spaceAfter=0.5 * cm
        )

        normal_style = ParagraphStyle(
            'NormalStyle',
            parent=styles['Normal'],
            fontName='SimSun',
            fontSize=12,
            leading=18
        )

        level1_style = ParagraphStyle(
            'Level1Style',
            parent=normal_style,
            leftIndent=0,
            fontSize=14
        )

        level2_style = ParagraphStyle(
            'Level2Style',
            parent=normal_style,
            leftIndent=1 * cm,
            fontSize=12
        )

        level3_style = ParagraphStyle(
            'Level3Style',
            parent=normal_style,
            leftIndent=2 * cm,
            fontSize=10
        )

        level4_style = ParagraphStyle(
            'Level4Style',
            parent=normal_style,
            leftIndent=3 * cm,
            fontSize=10
        )

        # 创建内容
        story = []

        # 添加目录标题
        story.append(Paragraph("目录", title_style))
        story.append(Spacer(1, 1 * cm))

        # 添加目录项
        for item in toc_items:
            level = item['level']
            text = item['text']

            if level == 1:
                style = level1_style
                text = f"{text}"
            elif level == 2:
                style = level2_style
                text = f"{text}"
            elif level == 3:
                style = level3_style
                text = f"{text}"
            else:
                style = level4_style
                text = f"{text}"

            story.append(Paragraph(text, style))

            # 对于最后一级（任务），添加任务下的文件列表
            if level == 3 and 'files' in item and item['files']:
                for file_name in item['files']:
                    file_text = f"{file_name}"
                    story.append(Paragraph(file_text, level4_style))

        # 构建文档
        doc.build(story)
        return True

    except Exception as e:
        print(f"创建目录页失败: {str(e)}")
        return False


def create_task_content_page(subproject_name, stage_name, task_name, file_list, output_path):
    """创建任务内容页，包含完整的路径（子项目-阶段-任务）和文件列表"""
    try:
        if not setup_fonts():
            raise Exception("字体设置失败")

        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # 设置字体
        c.setFont("SimSun", 16)

        # 绘制完整标题路径：子项目-阶段-任务
        full_title = f"{subproject_name} - {stage_name} - {task_name}"
        title_width = c.stringWidth(full_title, "SimSun", 16)
        x = (width - title_width) / 2
        y = height - 2 * cm
        c.drawString(x, y, full_title)

        # 绘制红色标题：合并PDF，任务下的所有PDF
        c.setFillColorRGB(1, 0, 0)  # 设置红色
        c.setFont("SimSun", 14)


        # 重置为黑色
        c.setFillColorRGB(0, 0, 0)
        c.setFont("SimSun", 12)

        # 绘制文件列表
        y_pos = height - 6 * cm
        for i, file_name in enumerate(file_list):
            c.drawString(3 * cm, y_pos, file_name)
            y_pos -= 0.8 * cm

            # 每页最多显示25个文件，如果超过则创建新页
            if (i + 1) % 25 == 0 and i < len(file_list) - 1:
                c.showPage()
                c.setFont("SimSun", 12)
                y_pos = height - 2 * cm

        c.showPage()
        c.save()
        return True
    except Exception as e:
        print(f"创建任务内容页失败: {str(e)}")
        return False


def extract_prefix_number(filename):
    """从文件名中提取前缀数字"""
    match = re.match(r'^(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')


def sort_files_by_prefix(files):
    """按照文件名前缀数字排序文件"""
    return sorted(files, key=lambda x: extract_prefix_number(x.file_name))


def merge_project_files_to_pdf(project_id):
    """将项目文件按照子项目-阶段-任务层次结构合并为PDF，并创建目录和标题页"""
    temp_dir = None
    try:
        # 获取项目信息
        project = Project.query.get(project_id)
        if not project:
            return None, "项目不存在"

        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        os.makedirs(temp_dir, exist_ok=True)

        # 创建最终PDF合并器
        final_pdf_merger = PdfMerger()
        has_files = False
        processed_files = []
        skipped_files = []

        # 收集目录项信息
        toc_items = []
        toc_counter = {'project': 0, 'subproject': 0, 'stage': 0, 'task': 0}

        # 获取项目下的所有子项目
        subprojects = Subproject.query.filter_by(project_id=project_id).all()

        # 如果没有子项目，直接返回错误
        if not subprojects:
            return None, "项目中没有子项目"

        # 1. 创建项目标题页
        project_title_page = os.path.join(temp_dir, "project_title.pdf")
        if create_title_page(project.name, project_title_page, font_size=24):
            final_pdf_merger.append(project_title_page)

        # 将项目添加到目录
        toc_counter['project'] += 1
        toc_items.append({
            'level': 1,
            'text': f"{toc_counter['project']} 项目一",
            'name': project.name
        })

        # 2. 处理每个子项目
        for subproject_index, subproject in enumerate(subprojects, 1):
            # 更新子项目计数
            toc_counter['subproject'] = subproject_index
            toc_counter['stage'] = 0  # 重置阶段计数

            # 添加子项目到目录
            toc_items.append({
                'level': 2,
                'text': f"{toc_counter['project']}.{toc_counter['subproject']} 子项目一",
                'name': subproject.name
            })

            # 创建子项目标题页
            subproject_title_page = os.path.join(temp_dir, f"subproject_{subproject.id}_title.pdf")
            if create_title_page(subproject.name, subproject_title_page, font_size=20):
                final_pdf_merger.append(subproject_title_page)

            # 记录当前处理的子项目名称（调试用）
            print(f"处理子项目: {subproject.name}")

            # 获取子项目下所有阶段
            stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()

            # 3. 处理每个阶段
            for stage_index, stage in enumerate(stages, 1):
                # 更新阶段计数
                toc_counter['stage'] = stage_index
                toc_counter['task'] = 0  # 重置任务计数

                # 添加阶段到目录，使用完整路径
                toc_items.append({
                    'level': 3,
                    'text': f"{toc_counter['project']}.{toc_counter['subproject']}.{toc_counter['stage']} {subproject.name} - {stage.name}",
                    'name': stage.name
                })

                # 创建阶段标题页
                stage_title_page = os.path.join(temp_dir, f"stage_{stage.id}_title.pdf")
                if create_title_page(stage.name, stage_title_page, font_size=18):
                    final_pdf_merger.append(stage_title_page)

                # 记录当前处理的阶段名称（调试用）
                print(f"  处理阶段: {stage.name}")

                # 获取阶段下所有任务
                tasks = StageTask.query.filter_by(stage_id=stage.id).all()

                # 4. 处理每个任务
                for task_index, task in enumerate(tasks, 1):
                    # 更新任务计数
                    toc_counter['task'] = task_index

                    # 获取任务下所有PDF文件
                    files = ProjectFile.query.filter_by(
                        project_id=project_id,
                        subproject_id=subproject.id,
                        stage_id=stage.id,
                        task_id=task.id
                    ).all()

                    # 按文件名前缀排序
                    sorted_files = sort_files_by_prefix(files)

                    # 过滤出PDF文件
                    pdf_files = [file for file in sorted_files if os.path.splitext(file.file_name.lower())[1] == '.pdf']

                    # 记录当前处理的任务名称和文件数量（调试用）
                    print(f"    处理任务: {task.name} (找到 {len(pdf_files)} 个PDF文件)")

                    # 如果任务下有PDF文件，则创建任务标题页并合并文件
                    if pdf_files:
                        # 添加任务到目录，使用完整路径
                        file_names = [file.original_name for file in pdf_files]
                        toc_items.append({
                            'level': 4,
                            'text': f"{subproject.name} - {stage.name} - {task.name}",
                            'name': task.name,
                            'files': file_names
                        })

                        # 构建完整的标题路径
                        task_path_title = f"{subproject.name} - {stage.name} - {task.name}"

                        # 创建任务标题页（初始页面）
                        task_title_page = os.path.join(temp_dir, f"task_{task.id}_title.pdf")
                        if create_title_page(task_path_title, task_title_page, font_size=16):
                            final_pdf_merger.append(task_title_page)

                        # 创建任务内容页，显示完整路径和文件列表
                        task_content_page = os.path.join(temp_dir, f"task_{task.id}_content.pdf")
                        if create_task_content_page(subproject.name, stage.name, task.name,
                                                    [file.original_name for file in pdf_files],
                                                    task_content_page):
                            final_pdf_merger.append(task_content_page)

                        # 合并任务下的所有PDF文件
                        for file in pdf_files:
                            input_path = os.path.join(current_app.root_path, file.file_path)

                            if not os.path.exists(input_path):
                                skipped_files.append({
                                    'name': file.original_name,
                                    'reason': '文件不存在'
                                })
                                continue

                            try:
                                # 直接添加PDF文件到合并器
                                final_pdf_merger.append(input_path)
                                processed_files.append(file.original_name)
                                has_files = True
                                print(f"      已添加文件: {file.original_name}")
                            except Exception as e:
                                skipped_files.append({
                                    'name': file.original_name,
                                    'reason': f'处理错误: {str(e)}'
                                })
                                print(f"      文件处理错误: {file.original_name} - {str(e)}")

                        # 任务合并完成后，创建一个任务完成页面
                        task_complete_page = os.path.join(temp_dir, f"task_{task.id}_complete.pdf")
                        if create_title_page(f"{task_path_title}", task_complete_page, font_size=16,
                                             subtitle="任务合并完毕，插入新页面"):
                            final_pdf_merger.append(task_complete_page)

        if not has_files:
            return None, "没有可合并的PDF文件"

        # 创建目录页
        toc_page = os.path.join(temp_dir, "toc.pdf")
        if create_toc_page(toc_items, toc_page):
            # 创建新的合并器，先放入目录，再放入之前的所有内容
            complete_pdf_merger = PdfMerger()
            complete_pdf_merger.append(toc_page)

            # 将最终的合并内容存为临时文件
            temp_final = os.path.join(temp_dir, "temp_final.pdf")
            final_pdf_merger.write(temp_final)
            final_pdf_merger.close()

            # 将临时文件添加到新的合并器
            complete_pdf_merger.append(temp_final)

            # 生成最终PDF
            output_filename = f"{project.name}_merged.pdf"
            output_path = os.path.join(temp_dir, output_filename)
            complete_pdf_merger.write(output_path)
            complete_pdf_merger.close()
        else:
            # 如果目录创建失败，就使用原来的合并结果
            output_filename = f"{project.name}_merged.pdf"
            output_path = os.path.join(temp_dir, output_filename)
            final_pdf_merger.write(output_path)
            final_pdf_merger.close()

        # 复制到临时文件并返回
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        shutil.copy2(output_path, temp_output.name)

        print(f"PDF合并完成: {output_filename}")
        print(f"处理的文件数量: {len(processed_files)}")
        print(f"跳过的文件数量: {len(skipped_files)}")

        return temp_output.name, None

    except Exception as e:
        print(f"合并PDF时出错: {str(e)}")
        return None, str(e)
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"清理临时文件失败: {str(e)}")