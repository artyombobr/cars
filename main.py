import os
import time
import json
import logging
import asyncio
import telegram
import warnings
# import cloudscraper
from selenium import webdriver
from urllib.parse import urlencode
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, JSON
from selenium.webdriver.common.by import By
from telegram.error import RetryAfter, TimedOut
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
# from tenacity import retry, stop_after_attempt, wait_fixed

warnings.filterwarnings("ignore")


class CarAlert:
    def __init__(self):
        self.pg = self.init_postgresql()
        self.telegram = telegram.Bot(token=os.environ.get("TELEGRAM_BOT_TOKEN"))
        # self.scraper = cloudscraper.create_scraper(
        #     browser={"browser": "chrome", "platform": "windows", "mobile": False}
        # )
        self.filter_mapping = dict()
        self.selenium = self.init_selenium()

    @staticmethod
    def init_selenium():
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")  # Для работы в контейнере
        options.add_argument("--disable-dev-shm-usage")  # Исправляет ошибки в Docker

        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    def init_postgresql(self):
        dialect = "postgresql+psycopg2"
        user = "artyombobr_owner"
        password = os.environ.get("POSTGRESQL_DB_PASSWORD")
        host = "ep-solitary-snow-a2dew9oq-pooler.eu-central-1.aws.neon.tech"
        name = "artyombobr"
        sslmode = "require"

        engine = create_engine(
            f"{dialect}://{user}:{password}@{host}/{name}?sslmode={sslmode}",
            echo=False
        )

        self._init_models()
        return sessionmaker(bind=engine)()

    def _init_models(self) -> None:
        base = declarative_base()

        class Car(base):
            __tablename__ = "car"
            id = Column(String, primary_key=True)
            vin = Column(String)
            description = Column(String)
            url = Column(String)
            image_url = Column(String)
            data = Column(JSON)

        self.Car = Car

    # @retry(wait=wait_fixed(wait=5), stop=stop_after_attempt(50))
    # def fetch_data(self, *args, **kwargs):
    #     response = self.scraper.get(*args, **kwargs)
    #
    #     print(response.status_code)
    #     print(response.content)
    #     if response.status_code != 200:
    #         response.raise_for_status()
    #     return response

    def get_mobilede_cars(self, filter_params):
        print(filter_params)
        cars = dict()

        params_mapping = dict(
            brand="make",
            # model="model",
            # damage="loss-type",
            # year_from="year-from",
            # year_to="year-to",
            # engine_size_from="engine-size-from",
            # engine_size_to="engine-size-to",
            # km_from="odometer-from",
            # km_to="odometer-to",
        )

        filter_mapping = dict(
            brand=dict(
                BMW=dict(
                    value=3500,
                    model=dict(
                        X5="49",
                        X6="60",
                    )
                ),
                AUDI=dict(
                    value=1900,
                    model=dict(
                        Q8="46"
                    )
                )
            ),
        )

        year_from = filter_params["year_from"]
        year_to = filter_params["year_to"]
        brand = filter_mapping["brand"][filter_params["brand"]]["value"]
        model = filter_mapping["brand"][filter_params["brand"]]["model"][filter_params["model"]]

        pages = 1000
        current_page = 1
        while current_page <= pages:

            query_params = dict(
                dam=False,
                fr=f"{year_from}:{year_to}",
                ms=f"{brand};{model};;",
                ref="quickSearch",
                s="Car",
                sb="rel",
                vc="Car"
            )

            params = dict(
                page=str(current_page),
                url=f"/search.html?{urlencode(query_params)}"
            )
            base_url = "https://m.mobile.de/consumer/api/search/srp/items"

            self.selenium.get("https://www.mobile.de/")
            time.sleep(5)
            self.selenium.get(f"{base_url}?{urlencode(params)}")

            current_page += 1

            content = self.selenium.find_element(By.TAG_NAME, "body").text

            data = json.loads(content)
            # print(data)
            for car_info in data["items"]:
                image_url = car_info.get("previewImage", {}).get("srcSet", "").split(", ")[-1].split(" ")[0]
                if car_info.get("id") is None or image_url == "":
                    continue
                cars[car_info["id"]] = dict(
                    id=car_info["id"],
                    source="mobile.de",
                    description=car_info["title"],
                    url="https://suchen.mobile.de" + car_info["relativeUrl"],
                    currency=car_info["price"]["grossCurrency"],
                    price=car_info["price"].get("netAmount", car_info["price"]["grossAmount"]),
                    image_url=image_url
                )

            if not data["hasNextPage"] or len(data["items"]) == 0:
                break

        return cars

    def get_copart_and_iaai_cars(self, filter_params):
        cars = dict()

        params_mapping = dict(
            brand="make",
            model="model",
            damage="loss-type",
            year_from="year-from",
            year_to="year-to",
            engine_size_from="engine-size-from",
            engine_size_to="engine-size-to",
            km_from="odometer-from",
            km_to="odometer-to",
        )

        params = {"search-type": "filters", "status": "All", "type": "Automobile", "auction-type": "All"}

        for key in ["km_from", "km_to"]:
            if "km_from" in filter_params:
                filter_params[key] = int(filter_params[key] * 0.621371)

        for key in filter_params:
            params[params_mapping[key]] = filter_params[key]

        current_page = 1
        while True:
            params["page"] = current_page

            query_string = urlencode(params)

            self.selenium.get(f"https://bid.cars/app/search/request?{query_string}")
            time.sleep(3)
            content = self.selenium.find_element(By.TAG_NAME, "body").text

            data = json.loads(content)
            current_page += 1

            for car_info in data["data"]:
                if car_info["img_large"]["img_1"] == "":
                    continue
                cars[car_info["lot"] or car_info["vin"]] = dict(
                    id=car_info["lot"] or car_info["vin"],
                    vin=car_info["vin"],
                    source="bid.cars",
                    description=car_info["name"],
                    url=f"https://bid.cars/ru/lot/{car_info['lot']}",
                    image_url=car_info["img_large"]["img_1"],
                    price=None,
                    currency="USD",
                    damage=car_info["loss_type"],
                    primary_damage=car_info["primary_damage"],
                    odometer_km=int(car_info["odometer"] / 0.621371),
                    auction_start=(
                            datetime.now() + timedelta(seconds=int(car_info["time_left"]))
                    ).replace(minute=0, second=0, microsecond=0),

                )
            if data["next_page_url"] is None:
                break

        return cars

    def get_sent_cars(self):
        sent_cars = set()
        cars = self.pg.query(self.Car.id).all()
        for row in cars:
            sent_cars.add(row.id)

        return sent_cars

    def get_new_cars(self):
        filters = [
            # dict(
            #     brand="BMW", model="X5", year_from=2020, year_to=2023,
            #     engine_size_to=3.5, km_to=80000
            # ),
            dict(
                brand="BMW", model="X6",
                year_from=2020,
                year_to=2023,
                engine_size_to=3.5,
                km_to=80000
            ),
            # dict(
            #     brand="AUDI", model="Q8", year_from=2020, year_to=2023,
            #     engine_size_to=3.5, km_to=80000
            # ),
        ]

        cars = dict()
        for filter_params in filters:
            cars.update(self.get_copart_and_iaai_cars(filter_params))
            cars.update(self.get_mobilede_cars(filter_params))

        sent_cars = self.get_sent_cars()

        return {
            key: value for key, value in cars.items()
            if str(key) not in sent_cars
        }

    async def send_photo(self, chat_id, photo, caption, parse_mode=None, max_retries=5, timeout_delay=5):
        retries = 0

        while retries < max_retries:
            try:
                return await self.telegram.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=parse_mode
                )
            except RetryAfter as e:
                wait_time = int(e.retry_after) + 1
                time.sleep(wait_time)
            except TimedOut:
                time.sleep(timeout_delay)

            retries += 1

    async def send_alert(self, new_cars):

        for vin, car_info in new_cars.items():
            print(car_info)
            auction_start_value = car_info.get("auction_start")

            self.pg.add(self.Car(
                id=car_info["id"],
                vin=car_info.get("vin"),
                description=car_info["description"],
                url=car_info["url"],
                image_url=car_info["image_url"],
                data=dict(
                    price=car_info["price"],
                    currency=car_info["currency"],
                    damage=car_info.get("damage"),
                    primary_damage=car_info.get("primary_damage"),
                    odometer_km=car_info.get("odometer_km"),
                    auction_start=getattr(auction_start_value, "isoformat", lambda: None)(),
                )
            ))

            self.pg.commit()

            caption = "{source}<a href='{url}'>{description}</a>{price}{damage}{odometer_km}".format(
                source="source" in car_info and f"<b>Source:</b> <a href='{car_info['url']}'>{car_info['source']}</a>\n" or "",
                url=car_info["url"],
                description=car_info["description"],
                price=car_info.get(
                    "price") is not None and f"\n<b>Price:</b> {int(car_info['price'])} {car_info['currency']}" or "",
                damage="damage" in car_info and "\n<b>Damage:</b> " + car_info["primary_damage"] or "",
                odometer_km="odometer_km" in car_info and "\n<b>Odometer, km:</b> " + str(car_info["odometer_km"]) or ""
            )

            time.sleep(1)
            await self.send_photo(
                chat_id="-1002275433565",
                photo=car_info["image_url"],
                caption=caption,
                parse_mode="HTML"
            )


async def main():
    car_alert = CarAlert()

    new_cars = car_alert.get_new_cars()
    await car_alert.send_alert(new_cars)

    print("finish")


if __name__ == "__main__":
    logging.disable(logging.INFO)
    asyncio.run(main())
