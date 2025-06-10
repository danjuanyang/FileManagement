# utils/Email_reminder.py
import smtplib
import requests
import pandas as pd
import schedule
import time
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
import io

# 从 config.py 导入配置
try:
    from config import MAIL_CONFIG, API_CONFIG, SCHEDULE_CONFIG
except ImportError:
    print("错误：无法从 config.py 导入配置。请确保文件存在且路径正确。")
    exit()


# --- 邮件发送核心函数 (已优化) ---
def send_email(subject, html_content, recipients, attachment_data=None, attachment_filename=None):
    """
    发送邮件的核心函数。
    此版本能为附件设置更精确的MIME类型，以避免文件名变成.bin。
    """
    msg = MIMEMultipart()
    msg['From'] = MAIL_CONFIG['SENDER_EMAIL']
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    if attachment_data and attachment_filename:
        if attachment_filename.endswith('.xlsx'):
            maintype, subtype = 'application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif attachment_filename.endswith('.png'):
            maintype, subtype = 'image', 'png'
        else:
            maintype, subtype = 'application', 'octet-stream'

        part = MIMEBase(maintype, subtype)
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        msg.attach(part)

    try:
        print(f"正在尝试使用 SMTP_SSL (端口 {MAIL_CONFIG['SMTP_PORT']}) 连接邮件服务器...")
        with smtplib.SMTP_SSL(MAIL_CONFIG['SMTP_SERVER'], MAIL_CONFIG['SMTP_PORT']) as server:
            server.login(MAIL_CONFIG['SMTP_USERNAME'], MAIL_CONFIG['SMTP_PASSWORD'])
            server.send_message(msg)
            print(f"邮件 '{subject}' 已成功发送至: {', '.join(recipients)}")
            return
    except Exception as e_ssl:
        print(f"使用 SMTP_SSL 失败: {e_ssl}")
        print("--- 正在回退到 STARTTLS 方案 ---")
        try:
            print(f"正在尝试使用 STARTTLS (端口 {MAIL_CONFIG['SMTP_PORT']}) 连接邮件服务器...")
            with smtplib.SMTP(MAIL_CONFIG['SMTP_SERVER'], MAIL_CONFIG['SMTP_PORT']) as server:
                server.starttls()
                server.login(MAIL_CONFIG['SMTP_USERNAME'], MAIL_CONFIG['SMTP_PASSWORD'])
                server.send_message(msg)
                print(f"邮件 '{subject}' 已成功发送至: {', '.join(recipients)}")
        except Exception as e_starttls:
            print(f"使用 STARTTLS 也失败了: {e_starttls}")


# --- 周报处理 (保持不变) ---
def generate_weekly_report_image(data_by_employee):
    width, height = 1200, 1600
    bg_color, font_color, header_color, employee_header_color = "white", "black", "#4a5568", "#2c5282"
    try:
        font_path = "msyh.ttc" if os.name == 'nt' else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        title_font, employee_font, header_font, content_font = [ImageFont.truetype(font_path, size) for size in
                                                                [36, 22, 16, 15]]
    except IOError:
        print("警告: 未找到指定字体，使用默认字体。")
        title_font, employee_font, header_font, content_font = [ImageFont.load_default() for _ in range(4)]
    image = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image)
    draw.text((50, 20), "本周工作更新概览", font=title_font, fill=font_color)
    y = 80
    for employee, updates in data_by_employee.items():
        if y > height - 150: break
        draw.line([(40, y), (width - 40, y)], fill="#e2e8f0", width=2)
        y += 15
        draw.text((50, y), f"员工: {employee}", font=employee_font, fill=employee_header_color)
        y += 40
        headers, header_positions = ["项目", "子项目", "任务", "更新内容", "更新时间"], [50, 200, 350, 550, 1000]
        for i, header in enumerate(headers):
            draw.text((header_positions[i], y), header, font=header_font, fill=header_color)
        y += 30
        for item in updates:
            if y > height - 50: break
            values = [item.get(k, 'N/A') for k in
                      ['project_name', 'subproject_name', 'task_name', 'update_content', 'update_timestamp']]
            values[3] = (values[3][:35] + '...') if values[3] and len(values[3]) > 35 else values[3]
            values[4] = values[4].split('T')[0]
            for i, value in enumerate(values):
                draw.text((header_positions[i], y), value, font=content_font, fill=font_color)
            y += 25
        y += 20
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()


def send_weekly_update_email():
    print("任务开始：获取每周更新数据...")
    url = f"{API_CONFIG['BASE_URL']}/api/leader/weekly-updates"
    headers = {'Authorization': f"Bearer {API_CONFIG['AUTH_TOKEN']}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        weekly_updates = data.get('weekly_updates', [])
        if not weekly_updates:
            print("本周没有更新数据，不发送邮件。")
            return
        updates_by_employee = defaultdict(list)
        for update in weekly_updates:
            updates_by_employee[update.get('employee_name', '未知员工')].append(update)
        image_data = generate_weekly_report_image(updates_by_employee)
        image_filename = f"weekly_report_{datetime.now().strftime('%Y-%m-%d')}.png"
        subject = f"每周工作汇报 - {datetime.now().strftime('%Y年%m月%d日')}"
        html_content = "<html><body><h2>每周工作汇报</h2><p>您好,</p><p>本周的工作汇报概览请见附件图片。</p><p>祝好！</p><p>--<br>项目组自动化报告系统</p></body></html>"
        send_email(subject, html_content, MAIL_CONFIG['RECIPIENTS'], image_data, image_filename)
    except Exception as e:
        print(f"处理周报时发生错误: {e}")


# --- 月度考勤报告处理 (已重构) ---
def send_monthly_clockin_report():
    """
    获取月度考勤数据，并生成与前端格式完全一致的Excel文件后发送邮件。
    """
    print("任务开始：获取月度考勤数据...")
    month_str = datetime.now().strftime('%Y-%m')
    url = f"{API_CONFIG['BASE_URL']}/api/leader/report-clockin-data?month={month_str}"
    headers = {'Authorization': f"Bearer {API_CONFIG['AUTH_TOKEN']}"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        api_data = response.json().get('data', [])

        if not api_data:
            print(f"{month_str} 月没有考勤数据，不发送邮件。")
            return

        # 1. 按员工分组聚合数据
        employee_groups = {}
        for row in api_data:
            employee_id = row['employee_id']
            if employee_id not in employee_groups:
                employee_groups[employee_id] = {
                    'employee_name': row['employee_name'],
                    'report_date': row['report_date'],
                    'remarks_list': []
                }
            for detail in row.get('dates', []):
                # --- 关键修改：格式化备注中的日期 ---
                date_str = detail.get('date')
                try:
                    # 解析 'YYYY-MM-DD' 格式的日期字符串
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    # 格式化为 'M月d日'
                    formatted_date = f"{date_obj.month}月{date_obj.day}日"
                except (ValueError, TypeError):
                    # 如果日期格式不正确或为空，则使用原始字符串
                    formatted_date = date_str

                remark_str = f"{formatted_date}: {detail.get('remarks') or '暂无备注'}"
                employee_groups[employee_id]['remarks_list'].append(remark_str)

        # 2. 将分组数据转换为最终的导出格式
        export_data = [{
            '员工姓名': group['employee_name'],
            '提交时间': datetime.fromisoformat(group['report_date']).strftime('%Y-%m-%d %H:%M:%S'),
            '补卡天数': len(group['remarks_list']),
            '补卡备注': '\n'.join(group['remarks_list'])
        } for group in employee_groups.values()]

        # 3. 使用XlsxWriter创建格式化的Excel文件
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df = pd.DataFrame(export_data)
            df.to_excel(writer, sheet_name='补卡记录', startrow=3, index=False)

            workbook = writer.book
            worksheet = writer.sheets['补卡记录']

            title_format = workbook.add_format({'bold': True, 'font_size': 14})
            wrap_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})

            worksheet.write('A1', '补卡记录导出', title_format)
            worksheet.write('A2', f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            worksheet.set_column('A:A', 15)
            worksheet.set_column('B:B', 20)
            worksheet.set_column('C:C', 10)
            worksheet.set_column('D:D', 40, wrap_format)

        # 4. 准备邮件内容并发送
        excel_data = excel_buffer.getvalue()
        excel_filename = f"补卡记录_{datetime.now().strftime('%Y-%m')}.xlsx"
        subject = f"月度考勤报告 - {month_str}月"
        html_content = f"<html><body><h2>月度考勤报告</h2><p>您好,</p><p>附件为 {month_str} 月的考勤数据Excel表，请查收。</p><p>--<br>项目组自动化报告系统</p></body></html>"

        send_email(subject, html_content, MAIL_CONFIG['RECIPIENTS'], excel_data, excel_filename)

    except Exception as e:
        print(f"处理月度报告时发生错误: {e}")


# --- 任务调度 (保持不变) ---
def setup_scheduler():
    # 设置每周报告的定时任务
    weekly_cfg = SCHEDULE_CONFIG['weekly_report']
    schedule.every().friday.at(f"{weekly_cfg['hour']:02d}:{weekly_cfg['minute']:02d}").do(send_weekly_update_email)

    # 设置每月报告的定时任务
    monthly_cfg = SCHEDULE_CONFIG['monthly_report']
    schedule.every().day.at(f"{monthly_cfg['hour']:02d}:{monthly_cfg['minute']:02d}").do(
        lambda: send_monthly_clockin_report() if datetime.now().day == monthly_cfg['day'] else None
    )
    print("定时任务已设置:")
    # 打印已设置的定时任务
    for job in schedule.get_jobs():
        print(f"- {job}")


if __name__ == "__main__":
    print("邮件提醒服务启动...")
    setup_scheduler()

    # print("\n--- 正在执行立即测试 ---")
    # send_weekly_update_email()
    # send_monthly_clockin_report()
    # print("--- 测试完成 ---\n")

    print("服务已启动，等待定时任务触发...")
    while True:
        schedule.run_pending()
        time.sleep(1)
