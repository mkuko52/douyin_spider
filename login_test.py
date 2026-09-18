import requests

headers = {
    'Content-Type': 'application/json',
}

json_data = {
    'phone': '13800138000',
    'code': '123456',
}

response = requests.post('http://127.0.0.1:8000/api/auth/sms_login', headers=headers, json=json_data)
print(response.json())