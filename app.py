from flask import Flask, request, render_template, redirect, url_for, flash, session, make_response, jsonify
from pymongo import MongoClient
import os
from flask_bcrypt import Bcrypt, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from bson.objectid import ObjectId
import jwt
from datetime import datetime, timedelta
import random
import logging
from authlib.integrations.flask_client import OAuth,OAuthError
from blueprints.seeker.routes import seeker_bp
from blueprints.admin.routes import admin_bp
from blueprints.recruiter.routes import recruiter_bp

app = Flask(__name__)
# Register the blueprint
app.register_blueprint(seeker_bp, url_prefix='/seeker')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(recruiter_bp, url_prefix='/recruiter')

app.secret_key = os.urandom(24)  # Required for flashing messages

# Configure logging
# logging.basicConfig(level=logging.DEBUG)

# MongoDB connection URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://AronJain:4E1zkxYGeaWZQCL8@cluster0.qy4jgjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

bcrypt = Bcrypt(app)
client = MongoClient(MONGO_URI)
db = client.job_portal

collection_seeker_registration = db.tbl_user_registration
collection_recruiter_registration = db.tbl_recruiter_registration
collection_login_credentials = db.tbl_login_credentials
collection_resume_details = db.tbl_resume_details
collection_industries = db.tbl_industries

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure Flask-Mail settings (replace placeholders with your actual SMTP server details)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'aronayikon10@gmail.com'
app.config['MAIL_PASSWORD'] = 'gbbn izcn iuxy sdne'
app.config['MAIL_DEFAULT_SENDER'] = 'aronayikon10@gmail.com'
# Initialize Flask-Mail
mail = Mail(app)

class User(UserMixin):
    def __init__(self, id, email, password, user_type, is_admin=False):
        self.id = id
        self.email = email
        self.password = password
        self.user_type = user_type
        self.is_admin = is_admin

    @staticmethod
    def get(user_id):
        user_data = collection_login_credentials.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(str(user_data['_id']), user_data['email'], user_data['password'], user_data['user_type'], user_data.get('is_admin', False))
        return None

    @staticmethod
    def get_by_email(email):
        user_data = collection_login_credentials.find_one({'email': email})
        if user_data:
            return User(str(user_data['_id']), user_data['email'], user_data['password'], user_data['user_type'], user_data.get('is_admin', False))
        return None

@app.route('/check_email', methods=['POST'])
def check_email():
    email = request.form.get('email')
    user = collection_login_credentials.find_one({'email': email})
    if user:
        return 'exists'
    else:
        return 'not exists'
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('fullname')
        user_type = request.form.get('user_type')
        email = request.form.get('email')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Attempt to send the verification email
        try:
            send_verification_email(email)
        except Exception as e:
            flash(f'An error occurred while sending the verification email: {e}', 'danger')
            return redirect(url_for('register'))
        
        # Insert login credentials with hashed password
        user_login_credentials = {
            "email": email,
            "password": hashed_password,
            "user_type": user_type
        }
        try:
            result = collection_login_credentials.insert_one(user_login_credentials)
            user_id = result.inserted_id
            
            if user_type == 'seeker':
                # Insert seeker registration data
                user_registration = {
                    "full_name": full_name,
                    "user_id": user_id
                }
                collection_seeker_registration.insert_one(user_registration)
                
                # Insert resume details for seeker
                user_resume = {
                    "full_name": full_name,
                    "email": email,
                    "user_id": user_id
                }
                collection_resume_details.insert_one(user_resume)
            elif user_type == 'recruiter':
                # Insert recruiter registration data
                company_name = request.form.get('company_name')
                company_email = request.form.get('company_email')
                company_website = request.form.get('company_website')
                industry_name = request.form.get('industry')
                
                # Find the industry ObjectId based on the name
                industry = collection_industries.find_one({'name': industry_name})
                if industry:
                    industry_id = industry['_id']
                else:
                    # Handle the case where the industry is not found
                    flash('Selected industry not found.', 'error')
                    return redirect(url_for('register'))
                
                recruiter_registration = {
                    "full_name": full_name,
                    "user_id": user_id,
                    "company_name": company_name,
                    "company_email": company_email,
                    "company_website": company_website,
                    "industry_id": industry_id,  # Store the ObjectId instead of the name
                }
                collection_recruiter_registration.insert_one(recruiter_registration)

            flash('Registration successful! Please check your email to verify your account.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')

    # Fetch industries from the database
    industries = list(collection_industries.find())
    return render_template('register.html', industries=industries)


def send_verification_email(email):
    token = generate_verification_token(email)
    verification_url = url_for('verify_email', token=token, _external=True)
    msg = Message('Verify Your Email', recipients=[email])
    msg.body = f'Please click the following link to verify your email: {verification_url}'
    mail.send(msg)

def generate_verification_token(email):
    expiration = datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
    payload = {"email": email, "exp": expiration}
    token = jwt.encode(payload, app.secret_key, algorithm="HS256")
    return token if isinstance(token, str) else token.decode('utf-8')

@app.route('/verify-email/<token>')
def verify_email(token):
    try:
        payload = jwt.decode(token, app.secret_key, algorithms=["HS256"])
        email = payload['email']
        # Perform the email verification logic here, such as updating the user's status in the database
        flash('Email verified successfully.', 'success')
        return redirect(url_for('login'))
    except jwt.ExpiredSignatureError:
        flash('The verification link has expired.', 'error')
        return redirect(url_for('register'))
    except jwt.InvalidTokenError:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('register'))
    
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route("/", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = collection_login_credentials.find_one({'email': email})

        if user:
            if email == 'admin' and password == 'admin':
                # Special case for admin user
                login_user(User(str(user['_id']), user['email'], user['password'], user['user_type'], True))
                return redirect(url_for('admin.dashboard'))
            elif check_password_hash(user['password'], password):
                login_user(User(str(user['_id']), user['email'], user['password'], user['user_type'], user.get('is_admin', False)))
                
                if user['user_type'] == 'seeker':
                    return redirect(url_for('index'))
                elif user['user_type'] == 'recruiter':
                    return redirect(url_for('recruiter.recruiter_index'))
                elif user['user_type'] == 'admin':
                    return redirect(url_for('admin.admin_dashboard'))
            else:
                flash('Invalid email or password. Try Again', 'warning')
        else:
            flash('Invalid email or password. Try Again', 'warning')

    return render_template("login.html")

@app.route('/index')
@login_required
def index():
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    print(current_user.id)
    return response

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()  # Clear the session
    response = make_response(redirect(url_for('login')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Mock function to send email
def send_otp_email(email, otp):
    msg = Message('Password Reset', recipients=[email])
    msg.body = f'Your OTP code is {otp}. Please do not share it with anyone'
    mail.send(msg)

# Endpoint to generate and send OTP
# Endpoint to generate and send OTP
@app.route('/generate_otp', methods=['POST'])
def generate_otp():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400

    otp = random.randint(100000, 999999)
    session['otp'] = str(otp)  # Ensure OTP is stored as a string
    session['email'] = email
    send_otp_email(email, otp)
    logging.debug(f"Generated OTP: {otp} for email: {email}")
    return jsonify({'status': 'success', 'message': 'OTP sent to email'})

# Endpoint to verify OTP
@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')

    logging.debug(f"Received OTP: {otp} for email: {email}")
    logging.debug(f"Session OTP: {session.get('otp')} for email: {session.get('email')}")

    # Check if email and OTP are in session and if they match
    if 'otp' in session and 'email' in session:
        if email == session['email'] and otp == session['otp']:
            logging.debug("OTP verified successfully")
            session.pop('otp', None)
            return jsonify({'status': 'success', 'message': 'OTP verified successfully'})
        else:
            logging.debug("Invalid OTP or email")
            return jsonify({'status': 'error', 'message': 'Invalid OTP or email'}), 400
    else:
        logging.debug("OTP not found or expired")
        return jsonify({'status': 'error', 'message': 'OTP not found or expired'}), 400


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        # Filter to match the document where email matches session['email']
        filter = {"email": session['email']}

        # Update operation to set the new hashed password
        update = {"$set": {"password": hashed_password}}

        # Perform the update operation
        result = collection_login_credentials.update_one(filter, update)
        
        if result.modified_count > 0:
            flash('Password updated successfully.', 'success')
        else:
            flash('Error updating password.', 'error')

        return redirect(url_for('login'))

    return render_template('forgot_password.html')

appConf = {
    "OAUTH2_CLIENT_ID": "354675704618-6952kjcntdu1p47nilp7a56fhe113og0.apps.googleusercontent.com",
    "OAUTH2_CLIENT_SECRET": "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",
    "OAUTH2_META_URL": "https://accounts.google.com/.well-known/openid-configuration",
    "FLASK_SECRET": "ALongRandomlyGeneratedString",
    "FLASK_PORT": 5000
    
}

app.secret_key = appConf.get("FLASK_SECRET")

oauth = OAuth(app)
oauth.register(
    "myApp",
    client_id=appConf.get("OAUTH2_CLIENT_ID"),
    client_secret=appConf.get("OAUTH2_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid profile email ",
        # 'code_challenge_method': 'S256'  # enable PKCE
    },
    server_metadata_url=f'{appConf.get("OAUTH2_META_URL")}',
)

@app.route("/google_login")
def  google_login():
    return oauth.myApp.authorize_redirect(redirect_uri=url_for("auth_receiver",_external=True))

@app.route("/auth-receiver")
def auth_receiver():
    try:
        token = oauth.myApp.authorize_access_token()
    except OAuthError as error:
        error_description = error.description if hasattr(error, 'description') else 'Unknown error'
        flash(f'Authentication failed: {error_description}', 'error')
        return redirect(url_for("login"))
    
    if token is None:
        flash('Google authentication failed: no token received.', 'error')
        return redirect(url_for("login"))
   
    session["user"] = token
    user_info = token.get("userinfo")
    user_email = user_info.get('email')

    # Check if the email exists in your database
    user = collection_login_credentials.find_one({'email': user_email})
    if user:
        login_user(User(str(user['_id']), user['email'], user['password'], user['user_type'], user.get('is_admin', False)))
        session['user_id'] = str(user['_id'])
        session['email'] = user['email']
        user_details = collection_seeker_registration.find_one({'_id': user['registration_id']})
        if user_details:
            session['full_name'] = user_details['full_name']
        return redirect(url_for("index"))
    else:
        flash('Email not registered with this application. Please register first.', 'warning')
        return redirect(url_for("register"))

@app.route("/blog")
def blog():
    return render_template("blog.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# @app.route('/job_postings')
# def job_postings():
#     # Fetch jobs from your database or data source
#     jobs = get_jobs()  # This function should return a list of job objects
    
#     return render_template('seeker/job_postings.html', collection_jobs=jobs)

# Add a new route to fetch industries
@app.route('/get_industries', methods=['GET'])
def get_industries():
    industries = list(collection_industries.find({}, {'_id': 0, 'name': 1}))
    return jsonify(industries)

if __name__ == '__main__':
    app.run(debug=True)