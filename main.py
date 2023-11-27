import os


def main():
    if os.environ.get("CAR_ALERT_BOT_TOKEN") == "ARTYOMBOBR":
        print("GOOD")
    else: 
        print("ERROR")


if __name__ == "__main__":
    main()
