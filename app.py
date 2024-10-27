from flask import Flask, render_template, make_response, request, redirect, url_for, flash
from utils.db import connect_db
from utils.login import extract_credentials, validate_password
from utils.posts import get_post, create_post, delete_post
import hashlib
import secrets
import bcrypt
from bson import ObjectId
from utils.posts import get_post, create_post

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

db = connect_db()
if db is not None:
    print('Database connected successfully')
else:
    print('Database not connected')
credential_collection = db["credential"]

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = credential_collection.find_one({"username": username})
        if user is None or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            flash("Invalid username/password", "error")
            return redirect(url_for('login'))

        response = make_response(redirect('/'))
        auth_token = secrets.token_hex(16)
        hash_auth_token = hashlib.sha256(auth_token.encode('utf-8')).hexdigest()
        credential_collection.update_one(
            {"username": username},
            {"$set": {"auth_token_hash": hash_auth_token}}
        )
        response.set_cookie('auth_token', auth_token, httponly=True, max_age=3600)
        return response
    
    if request.method == 'GET':
        response = make_response(render_template('login.html'))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template('register.html')

        # Check if password meets strength requirements
        if not validate_password(password):
            flash("Password does not meet the requirements:<br>- 8+ characters<br>- 1 lowercase letter<br>- 1 uppercase letter<br>- 1 special character: !,@,#,$,%,^,&,(,),-,_,=", "error")
            return render_template('register.html')

        # Check if the username is already taken
        if credential_collection.find_one({"username": username}):
            flash("Username already taken", "error")
            return render_template('register.html')

        # Hash the password with bcrypt and insert into database
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        credential_collection.insert_one({
            "username": username,
            "password_hash": hashed_password
        })
        return redirect(url_for('login'))

    # GET request
    return render_template('register.html')


@app.route('/logout', methods=['GET'])
def logout():
    response = make_response(redirect(url_for('home')))  # Redirect to home page after logout
    response.set_cookie('auth_token', '', expires=0)  # Invalidate the auth token
    flash("You have been logged out.", "success")
    return response


@app.route('/', methods=['GET'])
def home():
    if "auth_token" not in request.cookies:
        return redirect(url_for("login"), 302)
    #if not logged in redirect back to login

    auth_token = request.cookies.get("auth_token")
    user = credential_collection.find_one({"auth_token_hash":hashlib.sha256(auth_token.encode()).hexdigest()})
    if not user:
        response = make_response(redirect(url_for("login"), 302))
        response.set_cookie('auth_token', '', expires=0)
        return response
    #if using invalid auth_token, redirect back to login

    response = make_response(render_template('home_page.html'))
    response.mimetype = "text/html"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.route('/posts', methods=['GET','POST'])
def posts():
    if request.method == 'GET':
        posts = get_post(db)
        response = make_response()
        response.set_data(posts)
        response.mimetype = "application/json"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    if request.method == 'POST':
        code = create_post(db, request)
        if code == 403:
            response = make_response("Permission Denied", 403)
            response.mimetype = "text/plain"
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response  

        elif code == 200:
            response = make_response('', 200) 
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response  
        

@app.route('/posts/<string:post_id>', methods=['DELETE'])
def delete_posts(post_id):
    code = delete_post(db, request, post_id)

    if code == 403:
        response = make_response("Permission Denied", 403)
        response.mimetype = "text/plain"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response  

    elif code == 204:
        response = make_response('', 204) 
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response  
    
@app.route('/like/<string:post_id>', methods=['POST'])
def like_post(post_id):
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        return "Unauthorized HAHA", 403
    
    user = credential_collection.find_one({"auth_token_hash": hashlib.sha256(auth_token.encode()).hexdigest()})
    if not user:
        return "Unauthorized HAHAHAHAHAH", 403
    
    post_collection = db["posts"]
    post_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$inc": {"likes": 1}}
    )
    return '', 200

@app.route('/comment/<string:post_id>', methods=['POST'])
def add_comment(post_id):
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        return "Unauthorized", 403

    user = credential_collection.find_one({"auth_token_hash": hashlib.sha256(auth_token.encode()).hexdigest()})
    if not user:
        return "Unauthorized", 403

    body = request.json  # Assuming the comment is sent in JSON format
    comment_text = body.get('comment')
    
    if not comment_text:
        return "Comment cannot be empty", 400

    post_collection = db["posts"]
    post_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {"comments": {"username": user["username"], "text": comment_text}}}
    )
    return '', 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)

