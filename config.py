import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:

    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is missing. Add it to the .env file."
        )

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        BASE_DIR,
        "instance",
        "forge_and_hide.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(
        BASE_DIR,
        "static",
        "uploads"
    )

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024