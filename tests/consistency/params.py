import os
import json
from tempfile import gettempdir

# Temporary folder for logs
TMP_FOLDER_PATH = os.path.join(gettempdir(), "wdm_consistency_test")

# Stress test parameter
NUMBER_OF_ORDERS = 1000

# Database population parameters
NUMBER_OF_ITEMS = 1
ITEM_STARTING_STOCK = 100
ITEM_PRICE = 1
NUMBER_OF_USERS = 1000
USER_STARTING_CREDIT = 1

CORRECT_USER_STATE = (NUMBER_OF_USERS * USER_STARTING_CREDIT) - (
    NUMBER_OF_ITEMS * ITEM_STARTING_STOCK * ITEM_PRICE
)

ORDER_URL = "http://localhost:8000/orders"
PAYMENT_URL = "http://localhost:8000/payment"
STOCK_URL = "http://localhost:8000/stock"
