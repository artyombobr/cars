from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Настройка Chrome
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Запуск без графического интерфейса
# options.add_argument("--no-sandbox")  # Для работы в контейнере
# options.add_argument("--disable-dev-shm-usage")  # Исправляет ошибки в Docker

# Запуск браузера
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# Открываем Google и печатаем заголовок страницы
driver.get("https://www.google.com")
print("Page title:", driver.title)

# Закрываем браузер
driver.quit()
