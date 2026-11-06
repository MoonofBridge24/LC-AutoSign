# -*- coding: UTF-8 -*-

import requests
import json
import sys
import time
import random
import os
import re
import requests
from requests.exceptions import RequestException
from collections import defaultdict

TOKEN_LIST = os.getenv('TOKEN_LIST', '')
SEND_KEY_LIST = os.getenv('SEND_KEY_LIST', '')

# 接口配置
url = 'https://m.jlc.com/api/activity/sign/signIn?source=3'
gold_bean_url = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
seventh_day_url = "https://m.jlc.com/api/activity/sign/receiveVoucher"


# ======== 工具函数 ========

def mask_account(account):
    """用于打印时隐藏部分账号信息"""
    if len(account) >= 4:
        return account[:2] + '****' + account[-2:]
    return '****'


def mask_json_customer_code(data):
    """递归地脱敏 JSON 中的 customerCode 字段"""
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "customerCode" and isinstance(v, str):
                new_data[k] = v[:1] + "xxxxx" + v[-2:]
            else:
                new_data[k] = mask_json_customer_code(v)
        return new_data
    elif isinstance(data, list):
        return [mask_json_customer_code(i) for i in data]
    else:
        return data


# ======== 推送通知 ========

def send_msg_by_server(send_key, title, content):
    # Server酱³：sctp{uid}t{token}
    if send_key.startswith('sctp'):
        match = re.match(r'^sctp(\d+)t', send_key)
        if not match:
            print("❌ Server酱³ SendKey 格式错误")
            return None
        uid = match.group(1)
        push_url = f'https://{uid}.push.ft07.com/send/{send_key}.send'
    else:
        # Server酱 Turbo
        push_url = f'https://sctapi.ftqq.com/{send_key}.send'
    data = {
        'title': title,
        'desp': content
    }
    try:
        response = requests.post(push_url, json=data, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get('code') != 0:
            print(f"❌ 推送失败: {result}")
        return result
    except RequestException as e:
        print(f"❌ 推送请求异常: {str(e)}")
        return None
    except Exception as e:
        print(f"❌ 推送未知异常: {str(e)}")
        return None


# ======== 单个账号签到逻辑 ========

def sign_in(access_token, retries=3, backoff=10):
    headers = {
        'X-JLC-AccessToken': access_token,
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/20) JlcMobileApp',
    }

    account = mask_account(access_token)

    def result(status, message):
        return {
            'status': status,
            'account': account,
            'message': message
        }

    for attempt in range(1, retries + 1):
        try:
            # 1. 获取金豆信息
            bean_response = requests.get(
                gold_bean_url, headers=headers, timeout=15
            )
            bean_response.raise_for_status()
            bean_result = bean_response.json()

            customer_code = bean_result['data']['customerCode']
            integral_voucher = bean_result['data']['integralVoucher']

            account = mask_account(customer_code)

            # 2. 执行签到
            sign_response = requests.get(
                url, headers=headers, timeout=15
            )
            sign_response.raise_for_status()
            sign_result = sign_response.json()

            if not sign_result.get('success'):
                message = sign_result.get('message', '未知错误')

                if '已经签到' in message:
                    print(f"ℹ️ [账号{account}] 今日已签到")
                    return result('already', '今日已签到')

                print(f"❌ [账号{account}] 签到失败：{message}")
                return result('failed', message)

            # 3. 解析签到结果
            data = sign_result.get('data') or {}
            gain_num = data.get('gainNum')
            status = data.get('status')

            if status and status > 0:
                if gain_num is not None and gain_num != 0:
                    message = (
                        f"获取{gain_num}个金豆，"
                        f"当前总数：{integral_voucher + gain_num}"
                    )
                    print(f"✅ [账号{account}] 今日签到成功")
                    return result('success', message)

                # 4. 第七天特殊处理
                seventh_response = requests.get(
                    seventh_day_url, headers=headers, timeout=15
                )
                seventh_response.raise_for_status()
                seventh_result = seventh_response.json()

                if seventh_result.get('success'):
                    message = (
                        f"第七天签到成功，"
                        f"当前金豆总数：{integral_voucher + 8}"
                    )
                    print(f"🎉 [账号{account}] 第七天签到成功")
                    return result('success', message)

                message = seventh_result.get('message', '第七天奖励领取失败')
                print(f"❌ [账号{account}] {message}")
                return result('failed', message)

            message = '签到接口返回成功，但签到状态异常'
            print(f"❌ [账号{account}] {message}")
            return result('failed', message)

        except RequestException as e:
            print(f"⚠️ [账号{account}] 第{attempt}次请求失败：{e}")

            if attempt < retries:
                wait = backoff * attempt
                print(f"⏳ {wait} 秒后重试...")
                time.sleep(wait)
            else:
                message = f"请求失败，已重试 {retries} 次：{e}"
                print(f"❌ [账号{account}] {message}")
                return result('failed', message)

        except Exception as e:
            message = f"程序异常：{type(e).__name__}: {e}"
            print(f"❌ [账号{account}] {message}")
            return result('failed', message)

    return result('failed', '未知错误')


# ======== 主函数 ========

def main():
    AccessTokenList = [token.strip() for token in TOKEN_LIST.split(',') if token.strip()]
    SendKeyList = [key.strip() for key in SEND_KEY_LIST.split(',') if key.strip()]

    if not AccessTokenList:
        print("❌ 请设置 TOKEN_LIST")
        return 1

    if not SendKeyList:
        print("❌ 请设置 SEND_KEY_LIST")
        return 1

    # 不再静默截断账号，避免账号与推送密钥错位
    if len(AccessTokenList) != len(SendKeyList):
        print(
            f"❌ 配置数量不一致："
            f"{len(AccessTokenList)} 个账号，"
            f"{len(SendKeyList)} 个 SendKey"
        )
        return 1

    print(f"🔧 共发现 {len(AccessTokenList)} 个账号需要签到")

    # 按 SendKey 分组
    task_groups = defaultdict(list)

    for access_token, send_key in zip(AccessTokenList, SendKeyList):
        task_groups[send_key].append(access_token)

    print(f"📊 共分为 {len(task_groups)} 个通知组")

    group_results = {}

    # 全局失败标记
    has_failure = False

    # 顺序执行所有账号
    for send_key, tokens in task_groups.items():
        print(f"\n🚀 开始处理 SendKey: {send_key[:5]}...")

        results = []

        for i, token in enumerate(tokens):
            print(f"📝 处理第 {i+1}/{len(tokens)} 个账号...")

            # 单账号独立执行
            try:
                account_result = sign_in(token)
            except Exception as e:
                account_result = {
                    'status': 'failed',
                    'account': mask_account(token),
                    'message': f'执行异常：{e}'
                }

            results.append(account_result)

            if account_result['status'] == 'failed':
                has_failure = True

            # 随机等待
            if i < len(tokens) - 1:
                wait_time = random.randint(5, 15)
                print(f"⏳ 等待 {wait_time} 秒...")
                time.sleep(wait_time)

        group_results[send_key] = results

    # 汇总统计
    print("\n📊 签到任务统计")

    success_count = 0
    already_count = 0
    failed_count = 0

    for results in group_results.values():
        for item in results:
            if item['status'] == 'success':
                success_count += 1
            elif item['status'] == 'already':
                already_count += 1
            else:
                failed_count += 1

    print(f"✅ 签到成功：{success_count}")
    print(f"ℹ️ 今日已签到：{already_count}")
    print(f"❌ 签到失败：{failed_count}")

    # 推送通知
    print("\n📬 开始发送通知...")

    notification_failed = False

    for send_key, results in group_results.items():

        # 只要有成功或失败，就发送通知
        report_results = [item for item in results if item['status'] in ('success', 'failed')]

        if not report_results:
            print(f"⏭️ SendKey {send_key[:5]}... 无需通知")
            continue

        success_messages = []
        failed_messages = []

        for item in report_results:
            line = f"账号({item['account']})：{item['message']}"

            if item['status'] == 'success':
                success_messages.append(f"✅ {line}")
            else:
                failed_messages.append(f"❌ {line}")

        content = (
            f"签到统计\n"
            f"成功：{success_count}\n"
            f"已签到：{already_count}\n"
            f"失败：{failed_count}\n\n"
        )

        if success_messages:
            content += "【签到成功】\n"
            content += "\n".join(success_messages) + "\n\n"

        if failed_messages:
            content += "【签到失败】\n"
            content += "\n".join(failed_messages)

        title = ("嘉立创签到失败" if failed_messages else "嘉立创签到成功")

        print(f"📤 正在推送至 {send_key[:5]}...")

        response = send_msg_by_server(send_key, title, content)

        if response and response.get('code') == 0:
            print("✅ 通知发送成功")
        else:
            print(f"❌ 通知发送失败：{response}")
            notification_failed = True

    # 最终退出状态
    if has_failure or notification_failed:
        print("\n❌ 任务执行完成，但存在失败项目")
        return 1

    print("\n🎉 所有账号执行正常")
    return 0


# ======== 程序入口 ========

if __name__ == '__main__':
    print("🏁 嘉立创自动签到任务开始")
    exit_code = main()
    print("🏁 任务执行完毕")
    sys.exit(exit_code)
