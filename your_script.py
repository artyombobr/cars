import telegram
import asyncio


def main():
    bot = telegram.Bot(token="6720148798:AAGtKhsMhyyro-ZAlLOlAe6f-7PpN5tMVAU")

    async def send_message():
        await bot.send_photo(
            chat_id=170311207,
            caption="https://www.caroutlet.eu/auctions/car/31266535",
            photo="https://media.caroutlet.eu/3167/15/52bdc0955b2d5d2ce1a7c30670d0c716b579273f.jpeg"
        )

    asyncio.run(send_message())


if __name__ == "__main__":
    main()
