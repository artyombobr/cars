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

Base = declarative_base()
from html.parser import HTMLParser
import telegram
import asyncio
from bs4 import BeautifulSoup

chat_id = "170311207"


engine = create_engine(
    "{dialect}://{user}:{password}@{host}:5432/{db}?sslmode=require".format(
        dialect="postgresql+psycopg2",
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        host="flora.db.elephantsql.com",
        db="pblpfbsi"
    ),
    echo=True
)

Session = sessionmaker(bind=engine)
session = Session()


class Cars(Base):
    __tablename__ = "cars"
    id = Column(String, primary_key=True)
    description = Column(String)
    url = Column(String)
    image_url = Column(String)


def openlane_cars():
    new_cars = dict()
    json_data = {
        'query': {
            'MakeModels': [
                {
                    'Make': 'Audi',
                    'Models': [
                        'Q8',
                    ],
                },
            ],
            'FuelTypes': [
                'Diesel',
            ],
        },
        'Sort': {
            'Field': 'BatchStartDateForSorting',
            'Direction': 'ascending',
            'SortType': 'Field',
        },
        'Paging': {
            'PageNumber': 1,
            'ItemsPerPage': 1000,
        },
        'SavedSearchId': None,
        'PageUrl': 'https://www.openlane.eu/en/findcar?makesModels=Audi%2CQ8&fuelTypes=Diesel',
    }
    response = requests.post(
        "https://www.openlane.eu/en/findcarv6/search",
        json=json_data
    )

    base_url = "https://www.openlane.eu/en/car/info?auctionId="

    if response.status_code == 200:
        cars_data = response.json()
        for car in cars_data["Auctions"]:
            new_cars[car["ChassisNumber"]] = dict(
                vin=car["ChassisNumber"],
                description=car["CarTitleList"]["en"],
                url=base_url + str(car["AuctionId"]),
                image_url=car["ThumbnailUrl"]
            )

    return new_cars


bot = telegram.Bot(token=os.environ.get("CAR_ALERT_BOT_TOKEN"))


async def send_message(car_info):
    print(car_info)
    session.add(Cars(
        id=car_info["vin"],
        description=car_info["description"],
        url=car_info["url"],
        image_url=car_info["image_url"]
    ))
    await bot.send_photo(
        chat_id=chat_id,
        caption="<a href='" + car_info["url"] + "'>" + car_info["description"] + "</a>",
        photo=car_info["image_url"],
        parse_mode="HTML"
    )
    session.commit()


def get_sent_cars():
    sent_cars = set()
    cars = session.query(Cars).all()
    for row in cars:
        sent_cars.add(row.id)

    return sent_cars


async def main():
    new_cars = openlane_cars()
    sent_cars = get_sent_cars()

    messages = list()
    for vin in new_cars:
        if vin in sent_cars:
            continue
        messages.append(send_message(new_cars[vin]))

    await asyncio.gather(*messages)

    session.close()


if __name__ == "__main__":
    asyncio.run(main())
