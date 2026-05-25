import requests,base64,zlib,json,pickle,os,sys

SESS_FILE = r'c:\Users\30855\Desktop\AI-chachong\test_session.pkl'

# Step 1: Send code
s = requests.Session()
r = s.get('https://ai-chachong.onrender.com/auth/api/captcha', timeout=30)
c = s.cookies.get('session','')
p = c.split('.')[0]; p += '='*(4-len(p)%4) if len(p)%4 else ''
d = base64.urlsafe_b64decode(p); d = zlib.decompress(d) if d[0]==0x78 else d
ca = json.loads(d).get('captcha_answer')
r2 = s.post('https://ai-chachong.onrender.com/auth/api/send-code', json={
    'account': '3085512050@qq.com', 'captcha': ca}, timeout=30)
print(r2.text)

if r2.json().get('success'):
    with open(SESS_FILE, 'wb') as f:
        pickle.dump(s, f)
    print('Session saved. Give me the code from email.')
else:
    print('Send failed')

