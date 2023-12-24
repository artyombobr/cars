import os
import re
import requests
import logging
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
from telegram.request import HTTPXRequest

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
                    'Models': ['Q8'],
                },
                {
                    'Make': 'BMW',
                    'Models': ["X4", "X5"]
                }
            ],
            'FuelTypes': [
                'Diesel',
            ],
            'RegistrationYearRange': {
                'From': 2019,
                'To': None
            }
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
                car_id=car["ChassisNumber"],
                vin=car["ChassisNumber"],
                description=car["CarTitleList"]["en"],
                url=base_url + str(car["AuctionId"]),
                image_url=car["ThumbnailUrl"],
                price=car["BuyNowPrice"],
                estimated_price=car["RequestedSalesPrice"],
                currency=car["CurrencyCodeId"]
            )

    return new_cars


def outlet_cars():
    new_cars = dict()
    cars_html = requests.get(
        "https://www.caroutlet.eu/cars-async",
        params={
            "page": 1,
            "sort": "newly_added",
            "filter[search_id]": None,
            "filter[manufacturer_id][]": 2,
            "filter[model_id][]": 100,
            "filter[engine_type_id][]": 1,
        },
        cookies=dict(AUTUS=os.environ.get("CAR_OUTLET_COOKIE"))
    ).json()["carsHtml"]

    # print(cars_html)
    cars_html_data = BeautifulSoup(cars_html, "html.parser")
    car_elements = cars_html_data.find_all("a", class_="table-cell__group_with-figure")
    for car_element in car_elements:
        vin = None
        price = 0
        url = car_element.attrs["href"]
        car_id = url.split("/")[-1]
        car_html = requests.get(
            url,
            cookies=dict(AUTUS=os.environ.get("CAR_OUTLET_COOKIE"))
        ).content
        car_html_data = BeautifulSoup(car_html, "html.parser")

        description = car_html_data.find_all("span", class_="gallery__title-inner")[1].text
        print(description)
        image_url = car_html_data.find("div", class_="fotorama gallery-main").find("a").attrs["href"]

        if car_html_data.find("li", string=" VIN-код ") is not None:
            vin = (
                car_html_data
                .find("li", string=" VIN-код ")
                .parent.find_all("li")[5]
                .text
                .replace(" ", "")
            )

        if car_html_data.find("button", string=re.compile("Купить")):
            price = (
                car_html_data
                .find("button", string=re.compile("Купить"))
                .text
            )
            price = int(re.sub("[^0-9]", "", price))

        new_cars[vin or car_id] = dict(
            car_id=vin or car_id,
            vin=vin,
            description=description,
            url=url,
            image_url=image_url,
            price=price,
            estimated_price=0,
            currency="EUR"
        )
    return new_cars


bot = telegram.Bot(
    token=os.environ.get("CAR_ALERT_BOT_TOKEN"),
    request=HTTPXRequest(pool_timeout=20, connect_timeout=20, connection_pool_size=20)
)


def get_price(car_info):
    if car_info["price"] > 0:
        price = '{0:,}'.format(int(car_info["price"])).replace(',', ' ')
        return "\n\n<b>" + price + " " + car_info["currency"] + "</b>"
    elif car_info["estimated_price"] > 0:
        price = '{0:,}'.format(int(car_info["estimated_price"])).replace(',', ' ')
        return "\n\n<b>" + price + " " + car_info["currency"] + "</b>"
    return ""


async def send_message(car_info):
    print(car_info)
    session.add(Cars(
        id=car_info["car_id"],
        description=car_info["description"],
        url=car_info["url"],
        image_url=car_info["image_url"]
    ))

    price = get_price(car_info)

    await bot.send_photo(
        chat_id=chat_id,
        caption="<a href='" + car_info["url"] + "'>" + car_info["description"] + "</a>" + price,
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
    semaphore = asyncio.Semaphore(5)

    new_cars = openlane_cars() | outlet_cars()
    sent_cars = get_sent_cars()

    messages = list()

    for car_id in new_cars:
        if car_id in sent_cars:
            continue
        async with semaphore:
            messages.append(send_message(new_cars[car_id]))

    await asyncio.gather(*messages)

    session.close()


if __name__ == "__main__":
    logging.disable(logging.INFO)
    asyncio.run(main())
