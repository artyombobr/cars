import os
import re
import requests
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String
import telegram
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse

chat_id = "170311207"

Base = declarative_base()

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
    json_data = dict(
        query=dict(
            MakeModels=[
                dict(
                    Make="Audi",
                    Models=["Q8"],
                ),
                dict(
                    Make="BMW",
                    Models=[
                        # "X3",
                        "X4", "X5", "X6"
                    ]
                )
            ],
            FuelTypes=["Diesel"],
            RegistrationYearRange=dict(From=2019, To=2021)
        ),
        Sort=dict(
            Field="BatchStartDateForSorting",
            Direction="ascending",
            SortType="Field",
        ),
        Paging=dict(
            PageNumber=1,
            ItemsPerPage=1000,
        ),
        SavedSearchId=None,
    )
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
            "filter[manufacturer_id][]": [
                1,  # AUDI
                2   # BMW
            ],
            "filter[model_id][]": [
                # 99,   # X3
                100,  # X5
                325,  # X6
                738,  # X4
                829   # Q8
            ],
            "filter[engine_type_id][]": 1,  # Diesel,
            "filter[year][]:": [2019, 2020, 2021]
        },
        cookies=dict(AUTUS=os.environ.get("CAR_OUTLET_COOKIE"))
    ).json()["carsHtml"]

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


def bid_cars():
    new_cars = dict()
    vin = None
    base_url = "https://bidcar.eu"
    cars_html = requests.get(
        url="https://bidcar.eu/ru/cars",
        params={
            "cs[make][]": [2, 3],
            "cs[model_short][2][0]": "q8",
            "cs[model_short][3][]": [
                # "x3",
                "x4", "x5", "x6"
            ],
            "per-page": 60
        },
        verify=False
    ).content

    cars_html_data = BeautifulSoup(cars_html, "html.parser")
    car_elements = cars_html_data.find_all("div", class_="carslist-item-a")
    for car_element in car_elements:
        url = base_url + car_element.find("a").attrs["href"]
        car_id = url[25:url.find("-")]
        car_html = requests.get(
            url=url,
            cookies=dict(
                PHPSESSID=os.environ.get("BIDCAR_COOKIE")
            )
        ).content
        car_html_data = BeautifulSoup(car_html, "html.parser")
        image_url = car_html_data.find("div", class_="carview-img").attrs["data-src"]
        if car_html_data.find("th", string="VIN:") is not None:
            vin = list(car_html_data.find("th", string="VIN:").find_next("td").stripped_strings)[0]

        description = car_html_data.find("h1").text

        new_cars[vin or car_id] = dict(
            car_id=vin or car_id,
            vin=vin,
            description=description,
            url=url,
            image_url=image_url,
            estimated_price=0,
            price=0
        )

    return new_cars


def autobid_cars():
    new_cars = dict()
    vin = None
    pages = 1
    current_page = 1
    while current_page <= pages:
        cars_html = requests.get(
            url="https://autobid.de",
            params={
                "show": "get",
                "action": "search",
                "brand_id[0]": 1,
                "21_1": 2019,
                "21_2": 2021,
                "page": current_page,
                "L": 1
            }
        ).content

        current_page += 1

        cars_html_data = BeautifulSoup(cars_html, "html.parser")
        pages = int(cars_html_data.find_all("a", class_="dwarf_pager_link")[-1].text)
        car_elements = cars_html_data.find_all("tr", class_="carListRow")
        for car_element in car_elements:
            url = car_element.attrs["href"]
            car_id = car_element.attrs["autobid:carid"]
            url = urlparse(url).scheme + "://" + urlparse(url).netloc

            car_html = requests.get(
                url=url,
                params=dict(
                    action="car",
                    show="showCar",
                    id=car_id,
                    L=1
                )
            ).content

            car_html_data = BeautifulSoup(car_html, "html.parser")
            if car_html_data.find("p", class_="premium_detale_name_zaokraglenie_bottom_right_t1") is not None:
                description = car_html_data.find("p", class_="premium_detale_name_zaokraglenie_bottom_right_t1").text
            else:
                description = car_html_data.find("div", class_="d_s_det").find("b").text

            if car_html_data.find("td", class_="premium_detale_table_zdjecia_p") is not None:
                image_url = car_html_data.find("td", class_="premium_detale_table_zdjecia_p").find("img").attrs["src"]
                image_url = image_url[:-5] + "hd.jpg"
            else:
                image_url = car_html_data.find("a", class_="js_details_gallery_single").attrs["href"]

            if car_html_data.find("table", class_="premium_detale_table_opis_dane_cena") is not None:
                price = car_html_data.find("table", class_="premium_detale_table_opis_dane_cena").find_all("td")[1].text
                vat = car_html_data.find("table", class_="premium_detale_table_opis_dane_cena").find_all("td")[3].text
            else:
                price = car_html_data.find("tr", class_="price_font").find("td").text
                vat = car_html_data.find("tr", class_="pod_font").find("td").text
            price = int(re.sub("[^0-9]", "", price))
            if "Including" in vat:
                price = int(price * 0.81)

            for model in ["BMWX4", "BMWX5", "BMWX6", "BMW7", "BMW8"]:
                if model in description.replace(" ", "").upper():
                    new_cars[vin or car_id] = dict(
                        car_id=vin or car_id,
                        vin=vin,
                        description=description,
                        url=f"{url}/?action=car&show=showCar&id={car_id}",
                        image_url=image_url,
                        estimated_price=price,
                        price=0,
                        currency="EUR"
                    )
                    break

    return new_cars


def get_price(car_info):
    if car_info["price"] > 0:
        price = '{0:,}'.format(int(car_info["price"])).replace(',', ' ')
        return "\n\n<b>" + price + " " + car_info["currency"] + "</b>"
    elif car_info["estimated_price"] > 0:
        price = '{0:,}'.format(int(car_info["estimated_price"])).replace(',', ' ')
        return "\n\n<b>" + price + " " + car_info["currency"] + "</b>"
    return ""


async def send_message(bot, car_info):
    session.add(Cars(
        id=car_info["car_id"],
        description=car_info["description"],
        url=car_info["url"],
        image_url=car_info["image_url"]
    ))

    price = get_price(car_info)
    try:
        await bot.send_photo(
            chat_id=chat_id,
            caption="<a href='" + car_info["url"] + "'>" + car_info["description"] + "</a>" + price,
            photo=car_info["image_url"],
            parse_mode="HTML"
        )
        session.commit()
    except Exception as e:
        print(car_info)
        print(e)


def get_sent_cars():
    sent_cars = set()
    cars = session.query(Cars).all()
    for row in cars:
        sent_cars.add(row.id)

    return sent_cars


async def main():
    new_cars = autobid_cars() | bid_cars() | outlet_cars() | openlane_cars()  # priority sites at the end
    sent_cars = get_sent_cars()

    async with telegram.Bot(os.environ.get("CAR_ALERT_BOT_TOKEN")) as bot:
        for car_id in new_cars:
            if car_id in sent_cars:
                continue
            await send_message(bot, new_cars[car_id])

    session.close()


if __name__ == "__main__":
    logging.disable(logging.INFO)
    asyncio.run(main())
