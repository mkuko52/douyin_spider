import requests

headers = {
    'Content-Type': 'application/json',
}

json_data = {
    'phone': '13800138000',
}

response = requests.post('http://127.0.0.1:8000/api/auth/send_code', headers=headers, json=json_data)
print(response.json())