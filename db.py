from pymongo import MongoClient

# MongoDB connection
client = MongoClient("mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client.meeff_tokens

# Insert or update token for a user with filters
def set_token(user_id, token, meeff_user_id, filters=None):
    update_data = {"user_id": user_id, "token": token, "name": meeff_user_id}
    if filters:
        update_data["filters"] = filters
    db.tokens.update_one(
        {"user_id": user_id, "token": token},
        {"$set": update_data},
        upsert=True
    )

# Get all tokens for a user
def get_tokens(user_id):
    return list(db.tokens.find({"user_id": user_id}, {"_id": 0, "token": 1, "name": 1, "filters": 1}))

# Get all tokens in the database
def list_tokens():
    return list(db.tokens.find({}, {"_id": 0}))

def set_current_account(user_id, token):
    db.current_account.update_one({"user_id": user_id}, {"$set": {"token": token}}, upsert=True)

def get_current_account(user_id):
    record = db.current_account.find_one({"user_id": user_id})
    return record["token"] if record else None

# Delete a token for a user
def delete_token(user_id, token):
    db.tokens.delete_one({"user_id": user_id, "token": token})

# Add or update filters for a specific token
def set_user_filters(user_id, token, filters):
    db.tokens.update_one(
        {"user_id": user_id, "token": token},
        {"$set": {"filters": filters}},
        upsert=True
    )

def get_user_filters(user_id, token):
    record = db.tokens.find_one({"user_id": user_id, "token": token}, {"filters": 1})
    return record["filters"] if record and "filters" in record else None
