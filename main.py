import os
import requests
import sqlalchemy as db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)




def main():
    print("TEST ENV: " + os.environ.get("CAR_ALERT_BOT_TOKEN"))


if __name__ == "__main__":
    main()
