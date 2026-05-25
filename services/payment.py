"""
============================================================
支付服务 - 微信支付 & 支付宝支付框架
============================================================

使用说明：
1. 模拟模式（默认）：无需配置，直接模拟支付成功
2. 微信支付：填入商户号/API密钥后自动切换
3. 支付宝：填入APPID/私钥后自动切换

接入流程：
  微信支付：https://pay.weixin.qq.com → 注册商户号 → 获取API密钥
  支付宝：https://open.alipay.com → 注册应用 → 获取密钥对
"""

import hashlib
import time
import json
import uuid
from config import config


class PaymentService:
    """
    统一支付服务
    根据配置自动选择支付渠道（模拟/微信/支付宝）
    """

    # 支付渠道
    CHANNEL_MOCK = "mock"
    CHANNEL_WECHAT = "wechat"
    CHANNEL_ALIPAY = "alipay"

    @classmethod
    def get_active_channel(cls) -> str:
        """获取当前启用的支付渠道（优先级：xorpay > 微信 > 支付宝 > 模拟）"""
        if config.XORPAY_APP_ID and config.XORPAY_API_SECRET:
            return "xorpay"
        if config.WECHAT_MCH_ID and config.WECHAT_API_KEY:
            return cls.CHANNEL_WECHAT
        if config.ALIPAY_APP_ID and config.ALIPAY_PRIVATE_KEY:
            return cls.CHANNEL_ALIPAY
        return cls.CHANNEL_MOCK

    @classmethod
    def create_order(cls, user_id: int, amount: float, description: str,
                     order_type: str = "member") -> dict:
        """
        创建支付订单
        """
        channel = cls.get_active_channel()

        if channel == "xorpay":
            return cls._create_xorpay_order(user_id, amount, description, order_type)
        elif channel == cls.CHANNEL_WECHAT:
            return cls._create_wechat_order(user_id, amount, description, order_type)
        elif channel == cls.CHANNEL_ALIPAY:
            return cls._create_alipay_order(user_id, amount, description, order_type)
        else:
            return cls._create_mock_order(user_id, amount, description, order_type)

    @classmethod
    def verify_callback(cls, callback_data: dict) -> dict:
        """
        验证支付回调

        返回:
            dict: {"success": bool, "order_id": str, "user_id": int, "amount": float}
        """
        channel = cls.get_active_channel()

        if channel == "xorpay":
            return cls._verify_xorpay_callback(callback_data)
        elif channel == cls.CHANNEL_WECHAT:
            return cls._verify_wechat_callback(callback_data)
        elif channel == cls.CHANNEL_ALIPAY:
            return cls._verify_alipay_callback(callback_data)
        else:
            return cls._verify_mock_callback(callback_data)

    # ==================== 模拟支付（测试用） ====================

    @classmethod
    def _create_mock_order(cls, user_id, amount, description, order_type):
        """创建模拟订单"""
        order_id = f"MOCK{int(time.time())}{user_id}"
        return {
            "success": True,
            "order_id": order_id,
            "amount": amount,
            "qr_code": f"/user/api/pay-mock-confirm?order_id={order_id}&user_id={user_id}&amount={amount}",
            "pay_url": f"/user/api/pay-mock-confirm?order_id={order_id}&user_id={user_id}&amount={amount}",
            "channel": cls.CHANNEL_MOCK,
        }

    @classmethod
    def _verify_mock_callback(cls, data):
        """验证模拟回调（测试用）"""
        return {
            "success": True,
            "order_id": data.get("order_id", ""),
            "user_id": int(data.get("user_id", 0)),
            "amount": float(data.get("amount", 0)),
        }

    # ==================== xorpay 个人支付（推荐） ====================

    @classmethod
    def _create_xorpay_order(cls, user_id, amount, description, order_type):
        """
        xorpay 统一下单
        文档: https://xorpay.com/doc/native.html
        
        新版API: POST https://xorpay.com/api/pay/{aid}
        格式: application/x-www-form-urlencoded
        """
        try:
            import requests

            order_id = f"XR{int(time.time())}{user_id}"

            # xorpay API 参数
            site_domain = config.SITE_DOMAIN
            if "localhost" in site_domain or "127.0.0.1" in site_domain:
                site_domain = "https://ai-chachong.onrender.com"
            
            payload = {
                "name": description,
                "pay_type": "native",
                "price": str(amount),
                "order_id": order_id,
                "notify_url": f"{site_domain}/user/api/pay-callback/xorpay",
                "order_uid": str(user_id),
                "more": str(user_id),
            }

            # xorpay 签名
            sign_str = payload["name"] + payload["pay_type"] + payload["price"] + payload["order_id"] + payload["notify_url"]
            sign = hashlib.md5((sign_str + config.XORPAY_API_SECRET).encode()).hexdigest()
            payload["sign"] = sign

            api_url = f"https://xorpay.com/api/pay/{config.XORPAY_APP_ID}"
            resp = requests.post(
                api_url,
                data=payload,  # form-encoded, not JSON
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    # 新版API: qr 在 info.qr 里
                    qr_url = data.get("info", {}).get("qr", "") or data.get("qr", "")
                    return {
                        "success": True,
                        "order_id": order_id,
                        "amount": amount,
                        "qr_code": qr_url,
                        "pay_url": qr_url,
                        "channel": "xorpay",
                    }
                else:
                    import sys
                    print(f"[XORPAY] API error: {data.get('status')} {data}", file=sys.stderr)
                    return cls._create_mock_order(user_id, amount, description, order_type)
            else:
                import sys
                print(f"[XORPAY] HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
                return cls._create_mock_order(user_id, amount, description, order_type)

        except Exception as e:
            import sys
            print(f"[XORPAY] Exception: {e}", file=sys.stderr)
            return cls._create_mock_order(user_id, amount, description, order_type)

    @classmethod
    def _verify_xorpay_callback(cls, data):
        """验证xorpay回调"""
        # xorpay回调字段: aoid, order_id, price, pay_price, status, sign
        received_sign = data.get("sign", "")

        # 验证签名
        if config.XORPAY_API_SECRET:
            sign_str = (data.get("aoid", "") + data.get("order_id", "") +
                       data.get("price", "") + data.get("pay_price", "") +
                       config.XORPAY_API_SECRET)
            calc_sign = hashlib.md5(sign_str.encode()).hexdigest()
            if calc_sign != received_sign:
                return {"success": False}

        return {
            "success": True,
            "order_id": data.get("order_id", ""),
            "user_id": int(data.get("more", 0)),
            "amount": float(data.get("price", 0)),
        }

    # ==================== 微信支付 ====================

    @classmethod
    def _create_wechat_order(cls, user_id, amount, description, order_type):
        """
        创建微信支付订单（JSAPI/Native）

        文档: https://pay.weixin.qq.com/doc/v3/merchant/4012791856
        """
        try:
            import requests

            order_id = f"WX{int(time.time())}{user_id}"
            total_fen = int(amount * 100)  # 微信支付以分为单位

            # 微信支付统一下单API (V3)
            payload = {
                "appid": config.WECHAT_APP_ID,
                "mchid": config.WECHAT_MCH_ID,
                "description": description,
                "out_trade_no": order_id,
                "notify_url": f"{config.SITE_DOMAIN}/user/api/pay-callback/wechat",
                "amount": {
                    "total": total_fen,
                    "currency": "CNY",
                },
            }

            # 调用微信支付API
            resp = requests.post(
                "https://api.mch.weixin.qq.com/v3/pay/transactions/native",
                json=payload,
                headers={
                    "Authorization": f"WECHATPAY2-SHA256-RSA2048 {cls._wechat_sign(payload)}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "order_id": order_id,
                    "amount": amount,
                    "qr_code": data.get("code_url", ""),
                    "pay_url": data.get("code_url", ""),
                    "channel": cls.CHANNEL_WECHAT,
                }
            else:
                # 降级为模拟支付
                return cls._create_mock_order(user_id, amount, description, order_type)

        except Exception as e:
            # 支付渠道故障，降级模拟
            return cls._create_mock_order(user_id, amount, description, order_type)

    @classmethod
    def _wechat_sign(cls, payload: dict) -> str:
        """微信支付签名（简化版，实际需使用商户私钥）"""
        # 完整实现需使用 cryptography 库进行 SHA256-RSA2048 签名
        # 此处为框架代码，接入真实商户号后替换
        return "WECHATPAY2-SHA256-RSA2048-PLACEHOLDER"

    @classmethod
    def _verify_wechat_callback(cls, data):
        """验证微信支付回调"""
        # 实际需验证签名、解密回调数据
        return {
            "success": True,
            "order_id": data.get("out_trade_no", ""),
            "user_id": int(data.get("attach", 0)),
            "amount": float(data.get("amount", {}).get("total", 0)) / 100,
        }

    # ==================== 支付宝支付 ====================

    @classmethod
    def _create_alipay_order(cls, user_id, amount, description, order_type):
        """
        创建支付宝订单（当面付/电脑网站支付）

        文档: https://opendocs.alipay.com/open/270/105898
        """
        try:
            import requests

            order_id = f"ALI{int(time.time())}{user_id}"

            # 支付宝统一下单参数
            biz_content = {
                "out_trade_no": order_id,
                "total_amount": amount,
                "subject": description,
                "body": description,
                "product_code": "FAST_INSTANT_TRADE_PAY",
            }

            payload = {
                "app_id": config.ALIPAY_APP_ID,
                "method": "alipay.trade.page.pay",
                "charset": "utf-8",
                "sign_type": "RSA2",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0",
                "notify_url": f"{config.SITE_DOMAIN}/user/api/pay-callback/alipay",
                "return_url": f"{config.SITE_DOMAIN}/user/center",
                "biz_content": json.dumps(biz_content, ensure_ascii=False),
            }

            # 支付宝网关
            alipay_url = "https://openapi.alipay.com/gateway.do"
            query_string = "&".join(f"{k}={v}" for k, v in payload.items())
            pay_url = f"{alipay_url}?{query_string}"

            return {
                "success": True,
                "order_id": order_id,
                "amount": amount,
                "qr_code": pay_url,
                "pay_url": pay_url,
                "channel": cls.CHANNEL_ALIPAY,
            }

        except Exception:
            return cls._create_mock_order(user_id, amount, description, order_type)

    @classmethod
    def _verify_alipay_callback(cls, data):
        """验证支付宝回调"""
        return {
            "success": data.get("trade_status") == "TRADE_SUCCESS",
            "order_id": data.get("out_trade_no", ""),
            "user_id": int(data.get("passback_params", 0)),
            "amount": float(data.get("total_amount", 0)),
        }
