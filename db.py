import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv()

MYSQLHOST = os.getenv("MYSQLHOST")
MYSQLUN = os.getenv("MYSQLUN")
MYSQLPW = os.getenv("MYSQLPW")
DATABASE = os.getenv("DATABASE")


def get_connection():
    try:
        conn = mysql.connector.connect(
            host=MYSQLHOST,
            user=MYSQLUN,
            password=MYSQLPW,
            database=DATABASE
        )
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None