from flask import Flask, render_template, request
from pymysql import connections
import os
import random
import argparse
from botocore.exceptions import ClientError
import boto3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# DB config
DBHOST = os.environ.get("DBHOST") or "localhost"
DBUSER = os.environ.get("DBUSER") or "root"
DBPWD = os.environ.get("DBPWD") or "password123"
DATABASE = os.environ.get("DATABASE") or "employees"
COLOR_FROM_ENV = os.environ.get('APP_COLOR') or "lime"
DBPORT = int(os.environ.get("DBPORT") or 3306)

# Team info
TEAM_NAME = os.environ.get('TEAM_NAME') or "DataWarriors"
TEAM_SLOGAN = os.environ.get('TEAM_SLOGAN') or "Conquering Data, One Query at a Time!"

# Background/S3
BACKGROUND_IMAGE_URL = os.environ.get('BACKGROUND_IMAGE_URL') or ""
S3_BUCKET = os.environ.get('S3_BUCKET') or ""
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

# AWS creds (temp creds include session token)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_SESSION_TOKEN = os.environ.get('AWS_SESSION_TOKEN')

# MySQL connection
db_conn = connections.Connection(
    host=DBHOST, port=DBPORT, user=DBUSER, password=DBPWD, db=DATABASE
)
output = {}
table = 'employee'

# Colors
color_codes = {
    "red": "#e74c3c", "green": "#16a085", "blue": "#89CFF0", "blue2": "#30336b",
    "pink": "#f4c2c2", "darkblue": "#130f40", "lime": "#C1FF9C",
}
SUPPORTED_COLORS = ",".join(color_codes.keys())
COLOR = random.choice(list(color_codes.keys()))

# S3 client setup (include session token!)
s3_client = None
try:
    # Prefer explicit temp creds if present
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_SESSION_TOKEN:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            aws_session_token=AWS_SESSION_TOKEN,
            region_name=AWS_REGION,
        )
    else:
        # Fallback to default chain (env/instance role)
        s3_client = boto3.client("s3", region_name=AWS_REGION)

    logger.info("S3 client initialized successfully")

    # Diagnostics to confirm what the container is actually using
    sts = boto3.client("sts", region_name=AWS_REGION)
    ident = sts.get_caller_identity()
    logger.info(f"AWS caller identity: {ident}")
    logger.info(f"S3 endpoint: {getattr(s3_client.meta, 'endpoint_url', None)} | region: {s3_client.meta.region_name}")
except Exception as e:
    s3_client = None
    logger.error(f"Failed to initialize S3 client: {e}")

def download_background_image():
    try:
        if BACKGROUND_IMAGE_URL and S3_BUCKET and s3_client:
            logger.info(f"Background image URL from ConfigMap: {BACKGROUND_IMAGE_URL}")
            filename = BACKGROUND_IMAGE_URL.rsplit('/', 1)[-1]
            os.makedirs("static", exist_ok=True)
            # Head + download
            s3_client.head_object(Bucket=S3_BUCKET, Key=filename)
            local_path = f"static/{filename}"
            s3_client.download_file(S3_BUCKET, filename, local_path)
            logger.info(f"Successfully downloaded background image from private S3 bucket: {filename}")
            return f"/static/{filename}"
        else:
            logger.warning("Background image download skipped - missing configuration")
            return None
    except Exception as e:
        logger.error(f"Failed to download background image from S3: {e}")
        return None

BACKGROUND_IMAGE_PATH = download_background_image()
# --- end S3 block ---

@app.route("/", methods=['GET', 'POST'])
def home():
    return render_template('addemp.html',
                           color=color_codes[COLOR],
                           team_name=TEAM_NAME,
                           team_slogan=TEAM_SLOGAN,
                           background_image=BACKGROUND_IMAGE_PATH)

@app.route("/about", methods=['GET','POST'])
def about():
    return render_template('about.html',
                           color=color_codes[COLOR],
                           team_name=TEAM_NAME,
                           team_slogan=TEAM_SLOGAN,
                           background_image=BACKGROUND_IMAGE_PATH)

@app.route("/addemp", methods=['POST'])
def AddEmp():
    emp_id = request.form['emp_id']
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    primary_skill = request.form['primary_skill']
    location = request.form['location']

    insert_sql = "INSERT INTO employee VALUES (%s, %s, %s, %s, %s)"
    cursor = db_conn.cursor()
    try:
        cursor.execute(insert_sql, (emp_id, first_name, last_name, primary_skill, location))
        db_conn.commit()
        emp_name = f"{first_name} {last_name}"
    finally:
        cursor.close()

    return render_template('addempoutput.html',
                           name=emp_name,
                           color=color_codes[COLOR],
                           team_name=TEAM_NAME,
                           team_slogan=TEAM_SLOGAN,
                           background_image=BACKGROUND_IMAGE_PATH)

@app.route("/getemp", methods=['GET', 'POST'])
def GetEmp():
    return render_template("getemp.html",
                           color=color_codes[COLOR],
                           team_name=TEAM_NAME,
                           team_slogan=TEAM_SLOGAN,
                           background_image=BACKGROUND_IMAGE_PATH)

@app.route("/fetchdata", methods=['GET','POST'])
def FetchData():
    emp_id = request.form['emp_id']
    output = {}
    select_sql = "SELECT emp_id, first_name, last_name, primary_skill, location from employee where emp_id=%s"
    cursor = db_conn.cursor()
    try:
        cursor.execute(select_sql, (emp_id,))  # 1-tuple
        result = cursor.fetchone()
        if not result:
            return "No employee found", 404
        output["emp_id"], output["first_name"], output["last_name"], output["primary_skills"], output["location"] = result
    except Exception as e:
        print(e)
    finally:
        cursor.close()

    return render_template("getempoutput.html",
                           id=output["emp_id"],
                           fname=output["first_name"],
                           lname=output["last_name"],
                           interest=output["primary_skills"],
                           location=output["location"],
                           color=color_codes[COLOR],
                           team_name=TEAM_NAME,
                           team_slogan=TEAM_SLOGAN,
                           background_image=BACKGROUND_IMAGE_PATH)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--color', required=False)
    args = parser.parse_args()

    if args.color:
        print("Color from command line argument =" + args.color)
        COLOR = args.color
        if COLOR_FROM_ENV:
            print("A color was set through environment variable -" + COLOR_FROM_ENV + ". However, color from command line argument takes precendence.")
    elif COLOR_FROM_ENV:
        print("No Command line argument. Color from environment variable =" + COLOR_FROM_ENV)
        COLOR = COLOR_FROM_ENV
    else:
        print("No command line argument or environment variable. Picking a Random Color =" + COLOR)

    if COLOR not in color_codes:
        print("Color not supported. Received '" + COLOR + "' expected one of " + SUPPORTED_COLORS)
        exit(1)

    app.run(host='0.0.0.0', port=81, debug=True)
PY
