from fastapi import FastAPI, HTTPException, status, Depends, Query, Body
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from auth import verify_password, create_access_token, get_password_hash, get_current_user, check_login
from database import user_collection, session_collection, account_collection
from models import UserInDB, UserLogin
from datetime import timedelta, datetime
from bson.objectid import ObjectId
import requests
from pydantic import BaseModel
import urllib.parse
import json
import time

class QrcodeToken(BaseModel):
    qrcode_token: str

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await user_collection.find_one({"username": form_data.username})
    if not user:
        raise HTTPException(status_code=400, detail="User không tồn tại")
    
    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Sai mật khẩu")
    
    token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=timedelta(minutes=30)
    )

    # Lưu session vào MongoDB
    await session_collection.insert_one({
        "username": user["username"],
        "access_token": token,
        "created_at": datetime.utcnow()
    })

    return {"access_token": token, "token_type": "bearer"}

# Tạo thêm API đăng ký để thêm user mới
@app.post("/register")
async def register(user: UserLogin):
    existing_user = await user_collection.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="User đã tồn tại")

    hashed_pw = get_password_hash(user.password)
    new_user = {"username": user.username, "hashed_password": hashed_pw}
    await user_collection.insert_one(new_user)
    return {"message": "Đăng ký thành công"}

@app.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
	"name": current_user["name"],
        # Bạn có thể trả thêm bất kỳ thông tin nào cần thiết
    }

@app.get("/get_accounts")
async def get_accounts(current_user: dict = Depends(check_login)):
    if current_user:
        accounts = await account_collection.find({"username": current_user["username"]}, {"_id": 0, "cookies": 0, "ip": 0, "username": 0}).to_list(None)
        # Convert ObjectId to string for JSON serialization
        return accounts
    else:
        return {"message": "Đăng nhập thất bại"}

@app.post("/update_status_nexday")
async def update_status_nexday(data: dict = Body(...), current_user: dict = Depends(check_login)):
    if current_user:
        account_collection.update_one({"userid": data["userid"]}, {"$set": {"status_nexday": data["status_nexday"]}})
        return {"message": "Cập nhật trạng thái thành công"}
    else:
        return {"message": "Đăng nhập thất bại"}

@app.get("/gen_qrcode")
async def add_account(current_user: dict = Depends(check_login)):
    if current_user:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        }
        return requests.get("https://shopee.vn/api/v2/authentication/gen_qrcode", headers=headers).json()
    else:
        return {"message": "Đăng nhập thất bại"}

@app.get("/qrcode_status")
async def add_account(qrcode_id: str = Query(...)):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    qrcode_id = urllib.parse.quote(qrcode_id)
    return requests.get(f"https://shopee.vn/api/v2/authentication/qrcode_status?qrcode_id={qrcode_id}", headers=headers).json()

@app.post("/qrcode_login")
async def create_item(qrcode_token: QrcodeToken = Body(...), current_user: dict = Depends(check_login)):
    if current_user:
        ip = requests.get('https://checkip.amazonaws.com').text.strip()
        session = requests.Session()
        data = {
            "qrcode_token":qrcode_token.qrcode_token,
            "device_sz_fingerprint":"",
            "client_identifier":{
                "security_device_fingerprint":""
                }
            }
        data["username"] = current_user["username"]
        headers = {'Content-type': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'}
        session.post("https://shopee.vn/api/v2/authentication/qrcode_login", data=json.dumps(data), headers=headers)
        info = session.get("https://shopee.vn/api/v4/account/get_profile").json()
        existing_account = await account_collection.find_one({"userid": info["data"]["user_profile"]["userid"]})
        if existing_account:
            account_collection.update_one({"userid": info["data"]["user_profile"]["userid"]}, {"$set": 
            {
                "avata": info["data"]["user_profile"]["portrait"],
                "cookies": session.cookies.get_dict(),
                "login_time": int(time.time()),
                "ip": ip
            }})
            return {"message": "Cập nhật tài khoản thành công"}
        else:
            account_collection.insert_one({
                "username": current_user["username"],
                "shopee_username": info["data"]["user_profile"]["username"],
                "avata": info["data"]["user_profile"]["portrait"],
                "userid": info["data"]["user_profile"]["userid"],
                "cookies": session.cookies.get_dict(),
                "fist": True,
                "login_time": int(time.time()),
                "status_nexday": False,
                "status_today": False,
                "coin_today": 0,
                "ip": ip
            })
            return {"message": "Đăng nhập thành công"}
    else:
        return {"message": "Đăng nhập thất bại"}


