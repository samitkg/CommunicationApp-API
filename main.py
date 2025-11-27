from fastapi import FastAPI, UploadFile, File, HTTPException,Form
from pydantic import BaseModel, EmailStr
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # or ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------------
# MongoDB Connection
# -------------------
MONGO_URL = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URL)
db = client["CommunicationDb"]
users_collection = db["users"]

#for documents larger than 16MB
fs_bucket = AsyncIOMotorGridFSBucket(db)

# -------------------
# Pydantic Models
# -------------------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    model_config={
        "from_attributes": True 
    }
  
        
class Logindata(BaseModel):
    username: str
    password: str

class LoginSucess(BaseModel):
    loginsuccess: bool
    
    model_config = {
        "from_attributes": True
    }
   


# -------------------
# API Endpoints
# -------------------
@app.get("/")
def home():
    return {"message": "Welcome to the communication API"}    
# Create User
@app.post("/user", response_model=UserResponse)
async def create_user(user: UserCreate):
    # Check duplicate user
    existing = await users_collection.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    # hashed = hash_password(user.password)

    user_doc = {
        "name": user.name,
        "email": user.email,
        "password": user.password
    }

    result = await users_collection.insert_one(user_doc)

    return UserResponse(
        id=str(result.inserted_id),
        name=user.name,
        email=user.email
    )


# Get All Users
@app.get("/users", response_model=List[UserResponse])
async def get_users():
    users = []
    usersResponse = users_collection.find({})
    async for doc in usersResponse:
        users.append(
            UserResponse(
                id=str(doc["_id"]),
                name=doc["name"],
                email=doc["email"]
            )
        )
    return users

# @app.get("/users/{id}")
# async def get_user(id: str,response_model=UserResponse):
#     user= users_collection.find_one({"_id":ObjectId(id)})
#     if user:
#         return UserResponse(
#             id=str(user["_id"]),
#             name=user["name"],
#             email=user["email"]
#         )   
        
#     else:
#         return {"message": "User not found"}
    
@app.get("/user/{id}")
async def get_user(id: str):
    user = await users_collection.find_one({"_id": ObjectId(id)})

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"]
    }


# Delete User by ID
@app.delete("/user/{user_id}")
async def delete_user(user_id: str):
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}


# # Login User
@app.post("/login")
async def login(form_data: Logindata):
    user = await users_collection.find_one({"email": form_data.username})

    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")

    if user["password"] != form_data.password:
        raise HTTPException(status_code=400, detail="Invalid email or password")

    return LoginSucess(loginsuccess=True)


@app.put("/user/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user: UserCreate):
    existing = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = {
        "name": user.name,
        "email": user.email,
        "password": user.password
    }

    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

    return UserResponse(
        id=user_id,
        name=user.name,
        email=user.email
    )       
    # Update user logic here
    # ...

@app.post("/upload")
async def upload_file(file: UploadFile = File(...),description: str = Form(...)):
    try:
        # Read file content
        file_data = await file.read()

        # Upload to GridFS
        file_id = await fs_bucket.upload_from_stream(
            file.filename,
            file_data,
            metadata={"content_type": file.content_type, "description": description},
        )

        return {
            "status": "success",
            "file_id": str(file_id),
            "filename": file.filename
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
async def list_all_files():
    try:
        cursor = db.fs.files.find()   # GridFS stores file metadata here
        files = []

        async for file in cursor:
            files.append({
                "file_id": str(file["_id"]),
                "filename": file["filename"],
                "length": file.get("length"),
                "uploadDate": file.get("uploadDate"),
                "contentType": file.get("metadata", {}).get("content_type"),
                "description": file.get("metadata", {}).get("description")
            })

        return {"count": len(files), "files": files}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.get("/file/{file_id}")
async def get_file(file_id: str):
    try:
        obj_id = ObjectId(file_id)
        stream = await fs_bucket.open_download_stream(obj_id)

        return {
            "filename": stream.filename,
            "content_type": stream.metadata.get("content_type")
        }

    except:
        raise HTTPException(status_code=404, detail="File not found")
    
@app.delete("/delete/{file_id}")
async def delete_file(file_id: str):
    try:
        fs_bucket.delete(ObjectId(file_id))
        return {"message": "File deleted successfully"}
    except:
        raise HTTPException(status_code=404, detail="File not found")
    
# @app.get("/download/{file_id}")
# async def download_file(file_id: str):
#     try:
#         file = fs.get(ObjectId(file_id))
#     except:
#         raise HTTPException(status_code=404, detail="File not found")

#     return StreamingResponse(
#         file,
#         media_type=file.content_type,
#         headers={
#             "Content-Disposition": f"attachment; filename={file.filename}"
#         }
#     )

# @app.post("/upload")
# async def upload_file(file: UploadFile = File(...)):
#     try:
#         file_id = fs.put(file.file, filename=file.filename, content_type=file.content_type)
#         return {"status": "success", "file_id": str(file_id), "filename": file.filename}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    
# @app.get("/file/{file_id}")
# def get_file(file_id: str):
#     try:
#         file_data = fs.get(file_id)
#         return {
#             "filename": file_data.filename,
#             "content_type": file_data.content_type,
#         }
#     except:
#         raise HTTPException(status_code=404, detail="File not found")
    
        
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
