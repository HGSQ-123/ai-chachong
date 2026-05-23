import requests, hashlib, time

# Read .env with proper encoding
try:
    with open(r'c:\Users\30855\Desktop\AI-chachong\.env', encoding='utf-8') as f:
        content = f.read()
except:
    with open(r'c:\Users\30855\Desktop\AI-chachong\.env', encoding='latin-1') as f:
        content = f.read()

secret = None
for line in content.split('\n'):
    if 'XORPAY_API_SECRET' in line and '=' in line:
        secret = line.split('=', 1)[1].strip().strip('"').strip("'")
        print(f'Secret found: {secret[:4]}***')
        break

if not secret:
    print('No XORPAY_API_SECRET found in .env')
    exit()

# Test xorpPay
order_id = f'XR{int(time.time())}test001'
payload = {
    'aid': '704741',
    'name': 'AI查重-测试支付',
    'pay_type': 'native',
    'price': '0.01',
    'order_id': order_id,
    'notify_url': 'https://ai-chachong.onrender.com/user/api/pay-callback/xorpay',
    'return_url': 'https://ai-chachong.onrender.com/user/center',
    'more': 'test',
}
sign_str = payload['name'] + payload['pay_type'] + payload['price'] + payload['order_id'] + payload['notify_url']
sign = hashlib.md5((sign_str + secret).encode()).hexdigest()
payload['sign'] = sign

print(f'Calling xorpPay...')
r = requests.post('https://xorpay.com/api/pay/native', json=payload, timeout=15)
print(f'HTTP {r.status_code}')
print(r.text[:800])
